/* DOM rendering: KPIs + sparklines, tables, filters, CSV export, formatting. */

const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

function inr(x, decimals = 0) {
  if (x === null || x === undefined) return "–";
  return "₹" + (decimals ? inr2 : inr0).format(x);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>\\"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* colorful category pills: stable color per category name */
const PILL_HUES = ["#f472b6", "#a78bfa", "#22d3ee", "#fb923c", "#a3e635",
                   "#facc15", "#60a5fa", "#f87171", "#2dd4bf", "#e879f9"];
function pill(name) {
  const h = String(name).split("").reduce((a, c) => a + c.charCodeAt(0), 0) % PILL_HUES.length;
  const c = PILL_HUES[h];
  return `<span class="pill" style="color:${c};border-color:${c}66">${esc(name)}</span>`;
}

/* ---------------- KPI sparklines: tiny axes-free SVG line ---------------- */
function sparklineSvg(values, color, w = 150, h = 30) {
  if (!values || values.length < 2) return "";
  const pts = values.slice(-12);                       // last 12 points
  const min = Math.min(...pts), max = Math.max(...pts);
  const span = (max - min) || 1;
  const step = w / (pts.length - 1);
  const coords = pts.map((v, i) =>
    [ (i * step).toFixed(1), (h - 3 - (v - min) / span * (h - 6)).toFixed(1) ]);
  const line = coords.map(c => c.join(",")).join(" ");
  const area = `0,${h} ` + line + ` ${w},${h}`;
  /* 300ms fade handled by CSS animation on .kpi-spark */
  return `<svg class="kpi-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <polygon points="${area}" fill="${color}" opacity="0.14"></polygon>
    <polyline points="${line}" fill="none" stroke="${color}" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round"></polyline>
  </svg>`;
}

/* ---------------- header KPI strip ---------------- */
function renderKpiStrip(d) {
  if (!d || d.empty) {
    el("kpi-strip").innerHTML = `
      <div class="kpi"><label>Net Balance</label><b>–</b><small>no data yet</small></div>
      <div class="kpi"><label>This Month</label><b>–</b><small>no data yet</small></div>
      <div class="kpi"><label>Savings Rate</label><b>–</b><small>no data yet</small></div>
      <div class="kpi"><label>Transactions</label><b>–</b><small>no data yet</small></div>`;
    return;
  }
  const change = d.month_spend - d.prev_month_spend;
  const pct = d.prev_month_spend ? (change / d.prev_month_spend * 100) : 0;

  /* spark series: cumulative net & monthly spend */
  let cum = 0;
  const cumNet = d.net.map(v => (cum += v));
  const rankColor = pct < 0 ? "var(--red)" : "var(--green)";

  el("kpi-strip").innerHTML = `
    <div class="kpi ${d.balance >= 0 ? "positive" : "negative"}">
      <label>Net Balance</label><b>${inr(d.balance)}</b>
      ${sparklineSvg(cumNet, d.balance >= 0 ? "#34d399" : "#f43f5e")}
      <small>${d.txn_count} transactions loaded</small>
    </div>
    <div class="kpi">
      <label>${esc(d.month_label)} Spend</label><b>${inr(d.month_spend)}</b>
      ${sparklineSvg(d.spend, "#fb923c")}
      <small>${change >= 0 ? "▲" : "▼"} ${Math.abs(pct).toFixed(1)}% vs ${esc(prevLabel(d))}</small>
    </div>
    <div class="kpi ${d.savings_rate >= 20 ? "positive" : "negative"}">
      <label>Savings Rate</label><b>${d.savings_rate}%</b>
      <small>of all-time income</small>
    </div>
    <div class="kpi">
      <label>Transactions</label><b>${d.txn_count}</b>
      <small>cleaned &amp; stored</small>
    </div>`;

  function prevLabel(dd) {
    const m = dd.months && dd.months.length >= 2 ? dd.months[dd.months.length - 2] : "last month";
    return m;
  }
}

/* ---------------- overview: category table (mine) ---------------- */
function renderCategoryTable(cats) {
  if (!cats || !cats.length) { el("category-table").innerHTML = "<p class='muted'>No categories yet.</p>"; return; }
  const total = cats.reduce((s, x) => s + x.amount, 0) || 1;
  el("category-table").innerHTML = tableHTML(
    ["Category", "This Month", "vs Prev", "Share"],
    cats.map(c => {
      const chg = c.change_pct === null ? "<span class='muted'>no previous period</span>" :
        `<span class="${c.change_pct >= 0 ? "up" : "down"}">${c.change_pct >= 0 ? "+" : ""}${c.change_pct}%</span>`;
      return [
        pill(c.name),
        `<td class="num debit">${inr(c.amount)}</td>`,
        `<td class="num">${chg}</td>`,
        `<td class="num">${(c.amount / total * 100).toFixed(1)}%</td>`,
      ].join("");
    })
  );
}

/* ---------------- donut HTML legend (click toggles a slice) -------------- */
function renderDonutLegend(legendData) {
  const box = el("donut-legend");
  if (!legendData) { box.innerHTML = ""; return; }
  const { slices, colors, total } = legendData;
  box.innerHTML = slices.map((c, i) => `
    <button class="dl-row ${DONUT_STATE.hidden.has(c.name) ? "dl-off" : ""}" data-dtoggle="${esc(c.name)}">
      <span class="dl-swatch" style="background:${colors[i]}"></span>
      <span class="dl-name">${esc(c.name)}</span>
      <span class="dl-amt">${inr(c.amount)}</span>
      <span class="dl-pct">${(c.amount / total * 100).toFixed(1)}%</span>
    </button>`).join("");
}

/* ---------------- zombies ---------------- */
function renderZombieKpis(z) {
  el("zombie-kpis").innerHTML = `
    <div class="kpi-mini"><label>Active Monthly Drain</label><b class="warn">${inr(z.active_monthly_drain)}</b></div>
    <div class="kpi-mini"><label>Annualized</label><b>${inr(z.active_annual_drain)}</b></div>
    <div class="kpi-mini"><label>Recurring Detected</label><b>${z.count}</b></div>
    <div class="kpi-mini"><label>Dormant (stopped)</label><b>${z.dormant_names.length}</b></div>`;
}

function renderZombieTable(items) {
  el("zombie-table").innerHTML = tableHTML(
    ["Merchant", "Category", "Pattern", "Gap", "Seen", "Monthly", "Annualized", "Lifetime", "Status"],
    items.map(i => [
      `<td class="merchant-cell">${esc(i.merchant)}</td>`,
      `<td>${pill(i.category)}</td>`,
      `<td>${i.frequency}</td>`,
      `<td>≈${i.interval_days}d · ${i.txn_count}x</td>`,
      `<td>${i.last_seen} <span class="muted">(${i.last_seen_days}d ago)</span></td>`,
      `<td class="num debit">${inr(i.monthly_cost)}</td>`,
      `<td class="num">${inr(i.annualized)}</td>`,
      `<td class="num muted">${inr(i.lifetime_spend)}</td>`,
      `<td><span class="pill ${i.status}">${i.status}</span></td>`,
    ].join(""))
  );
}

/* ---------------- inflation ---------------- */
function renderInflationKpis(d) {
  el("yoy-personal").textContent = d.personal_yoy + "%";
  el("yoy-personal").style.color = d.personal_yoy > d.cpi_yoy ? "#f87171" : "#34d399";
  el("yoy-cpi").textContent = d.cpi_yoy + "%";
  el("yoy-cpi").style.color = "#22d3ee";
  el("yoy-verdict").textContent = d.personal_yoy > d.cpi_yoy
    ? `Your basket's fitted trend is ${(d.personal_yoy - d.cpi_yoy).toFixed(1)} points ABOVE national CPI — your personal basket is getting costlier faster than the country's.`
    : `Good news: your personal basket's trend is running below national CPI.`;
}

function renderInflationTable(cats) {
  el("inflation-table").innerHTML = tableHTML(
    ["Basket Category", "Trend / Year", "Weight", "Avg / Month"],
    cats.map(c => [
      `<td>${pill(c.name)}</td>`,
      `<td class="num ${c.yoy >= 0 ? "up" : "down"}">${c.yoy >= 0 ? "+" : ""}${c.yoy}%</td>`,
      `<td class="num">${c.weight}%</td>`,
      `<td class="num">${inr(c.monthly_avg)}</td>`,
    ].join(""))
  );
}

/* ---------------- health ---------------- */
function renderHealthTable(components) {
  el("health-table").innerHTML = tableHTML(
    ["Component", "Weight", "Raw Metric", "Score"],
    components.map(c => [
      `<td>${esc(c.name)}</td>`,
      `<td class="num">${c.weight}%</td>`,
      `<td class="muted">${esc(c.raw)}</td>`,
      `<td class="num"><span class="pill" style="color:${c.score >= 70 ? "#34d399" : "#f87171"};border-color:${c.score >= 70 ? "rgba(52,211,153,.6)" : "rgba(248,113,113,.6)"}">${c.score}</span></td>`,
    ].join(""))
  );
}

function renderSuggestions(list) {
  el("health-suggestions").innerHTML = list.map(s => `<li>${esc(s)}</li>`).join("");
}

/* ---------------- ledger ---------------- */
function renderLedger(rows, filters) {
  const q = (filters.search || "").toLowerCase();
  const cat = filters.category;
  const dir = filters.direction;
  const mon = filters.month;                    // "YYYY-MM" key

  const filtered = rows.filter(r =>
    (!cat || r.category === cat) &&
    (!dir || r.direction === dir) &&
    (!mon || (r.date || "").slice(0, 7) === mon) &&
    (!q || (r.merchant + " " + r.raw_text).toLowerCase().includes(q))
  );

  el("ledger-count").textContent = `${filtered.length} / ${rows.length} rows`;
  el("ledger-table").innerHTML = tableHTML(
    ["Date", "Dir", "Merchant", "Category", "Amount", "Balance", "Src", "Raw SMS"],
    filtered.slice(0, 400).map(r => [
      `<td>${r.date}</td>`,
      r.direction === "credit" ? `<td class="credit">CR</td>` : `<td class="debit">DR</td>`,
      `<td class="merchant-cell">${esc(r.merchant)}</td>`,
      `<td>${pill(r.category)}</td>`,
      `<td class="num ${r.direction === "credit" ? "credit" : "debit"}">${inr(r.amount, 2)}</td>`,
      `<td class="num muted">${r.balance === null ? "–" : inr(r.balance, 2)}</td>`,
      `<td>${r.source}</td>`,
      `<td><span class="muted" title="${esc(r.raw_text)}">${esc((r.raw_text || "").slice(0, 46))}${(r.raw_text || "").length > 46 ? "…" : ""}</span></td>`,
    ].join(""))
  );
  return filtered;
}

function fillCategorySelect(rows) {
  const cats = [...new Set(rows.map(r => r.category))].sort();
  el("ledger-category").innerHTML = `<option value="">All categories</option>` +
    cats.map(c => `<option>${esc(c)}</option>`).join("");

  /* month options: "YYYY-MM" -> label */
  const months = [...new Set(rows.map(r => (r.date || "").slice(0, 7)))].filter(Boolean).sort().reverse();
  el("ledger-month").innerHTML = `<option value="">All months</option>` +
    months.map(m => `<option value="${m}">${monthLabel(m)}</option>`).join("");
}

function monthLabel(key) {                    /* "2025-10" -> "Oct 25" */
  const [y, m] = key.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[+m - 1]} ${y.slice(2)}`;
}

function exportCsv(rows) {
  if (!rows.length) return;
  const head = "date,direction,amount,merchant,category,balance,raw_text";
  const body = rows.map(r => [
    r.date, r.direction, r.amount,
    `"${(r.merchant || "").replace(/\\"/g, '""')}"`,
    `"${r.category}"`, r.balance ?? "",
    `"${(r.raw_text || "").replace(/\\"/g, '""')}"`,
  ].join(",")).join("\n");
  const blob = new Blob([head + "\n" + body], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "transactions_cleaned.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------------- ingest report (table view of the parse funnel) --------- */
function renderIngestVizTable(r) {
  const box = el("ingest-viz-table");
  if (!box) return;
  if (!r) {
    box.innerHTML = "<p class='muted'>No ingest run yet — parse SMS text, " +
      "upload a dump file, or load the demo dataset. The funnel counts update here.</p>";
    return;
  }
  const stats = [
    ["rows in", r.rows_in ?? r.messages_in_file ?? null],
    ["messages in file", r.messages_in_file ?? null],
    ["parsed", r.parsed ?? null],
    ["skipped (not transactions)", r.failed ?? null],
    ["duplicates removed", r.duplicates_removed ?? null],
    ["already in database", r.already_stored ?? null],
    ["unknown merchants", r.unknown_merchants ?? null],
    ["rows stored", r.rows_out ?? null],
    ["total in DB", r.stored_total ?? null],
  ].filter(s => s[1] !== null && s[1] !== undefined);
  box.innerHTML = tableHTML(
    ["Stage", "Count"],
    stats.map(s => [`<td>${esc(s[0])}</td>`, `<td class="num">${s[1]}</td>`].join(""))
  );
}

/* ---------------- helpers ---------------- */
function el(id) { return document.getElementById(id); }

function tableHTML(headers, rowsHtml) {
  const numSet = new Set(["Amount", "Share", "Monthly", "Annualized", "Lifetime", "Weight", "Score",
    "This Month", "vs Prev", "Avg / Month", "Trend / Year", "Gap", "Count", "Spend",
    "Income", "Expenses", "Net", "Spend", "3-mo avg", "Total spend", "Txns",
    "Budget (3-mo median)", "Actual", "You", "CPI", "Step", "Date", "Note"]);
  return `<div class="table-wrap"><table>
    <thead><tr>${headers.map(h =>
      `<th class="${numSet.has(h) ? "num" : ""}">${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${rowsHtml.map(r => `<tr>${r}</tr>`).join("")}</tbody>
  </table></div>`;
}

function showError(title, err) {
  console.error(title, err);
}
