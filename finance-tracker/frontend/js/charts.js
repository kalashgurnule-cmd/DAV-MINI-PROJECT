/* =========================================================================
   Chart layer — one library (Plotly), one theme, one wrapper.

   Every chart goes through renderChart(), which provides:
   loading skeleton -> data -> 300ms fade (first load only, respects
   prefers-reduced-motion), "Not enough data yet" empty states with the
   minimum threshold explained, error state with ↻ Retry, a "View as
   table" fallback (wire via .chip[data-table]) and an aria/note summary.

   Colors come from CSS theme variables, so switching --* values in
   style.css re-themes every chart automatically.
   ========================================================================= */

/* ------------------------------------------------------------ theme ----- */
const THEME = { loaded: false };
function ensureTheme() {
  if (THEME.loaded) return;
  const cs = getComputedStyle(document.documentElement);
  ["text", "muted", "violet", "pink", "cyan", "orange", "lime",
   "yellow", "red", "green", "gold"].forEach(k => THEME[k] = cs.getPropertyValue("--" + k).trim());
  THEME.grid = "rgba(255,255,255,0.08)";
  THEME.loaded = true;
}

/* ------------------------------------------------- money (Intl-based) --- */
/* AGENTS.md rule: rupee formatting via Intl. Compact suffixes (K/L/Cr) are
   applied to an Intl-formatted numeric core, never hand-formatted digits. */
const nfFull = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nfInt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

function inrFull(x) { return "₹" + nfFull.format(Number(x) || 0); }
function inrInt(x) { return "₹" + nfInt.format(Number(x) || 0); }

/** Compact Indian currency: ₹1.2K, ₹45K, ₹1.5L, ₹2Cr (axes & labels). */
function inrCompact(x) {
  const a = Math.abs(Number(x) || 0);
  let v, s;
  if (a >= 1e7) { v = x / 1e7; s = "Cr"; }
  else if (a >= 1e5) { v = x / 1e5; s = "L"; }
  else if (a >= 1e3) { v = x / 1e3; s = "K"; }
  else return "₹" + nfInt.format(Math.round(Number(x) || 0));
  const txt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 1 }).format(Math.abs(v));
  return (x < 0 ? "-₹" : "₹") + txt + s;
}

/* ----------------------------------------------------- axis factories --- */
/** Nice 1-2-2.5-5-10 ticks, 4-5 gridlines max, compact ticktext. */
function niceTicks(minVal, maxVal) {
  const lo = Math.min(0, minVal), hi = Math.max(Math.abs(maxVal), 1);
  const span = Math.max(hi, Math.abs(lo));
  const rawStep = span / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const start = Math.floor(lo / step) * step;
  const vals = [];
  for (let v = start; v <= hi + step * 0.01; v += step) vals.push(Number(v.toFixed(6)));
  return { tickvals: vals, ticktext: vals.map(inrCompact) };
}

/** Y axis: dashed light gridlines, 12px muted text, no border, no zeroline. */
function yAxis(values, extra = {}) {
  ensureTheme();
  const t = niceTicks(Math.min(...values, 0), Math.max(...values, 1));
  return {
    gridcolor: THEME.grid, griddash: "dash", showgrid: true,
    zeroline: false, showline: false, outlinewidth: 0,
    tickfont: { size: 12, color: THEME.muted },
    tickvals: t.tickvals, ticktext: t.ticktext.map(x => x), // compact ₹ on axes
    ...extra,
  };
}

/** X axis (category/time): no vertical gridlines, vertical crosshair spikes. */
function xAxis(extra = {}) {
  ensureTheme();
  return {
    showgrid: false, outlinewidth: 0, showline: false,
    tickfont: { size: 12, color: THEME.muted },
    showspikes: true, spikemode: "across", spikesnap: "cursor",
    spikethickness: 1, spikedash: "dot", spikecolor: THEME.muted,
    ...extra,
  };
}

function baseLayout() {
  ensureTheme();
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: THEME.muted, family: "Segoe UI, sans-serif", size: 12 },
    showlegend: false,
    hoverlabel: { bgcolor: "rgba(20,16,48,0.95)", bordercolor: THEME.grid, font: { size: 12.5, color: THEME.text } },
  };
}

const CONFIG = { responsive: true, displayModeBar: false };

const LEGEND_STYLE = () => ({
  itemclick: "toggle", itemdoubleclick: "toggleothers",
  font: { size: 12, color: THEME.muted },
});

/* --------------------------------------------------- the one wrapper ---- */
const REGISTRY = {};                 // chart id -> thunk (for Retry)
const REGISTRY_NOTE = {};            // chart id -> note element id (for Retry)
const CHART_TABLE = {};              // chart id -> {headers, rows}

function setNote(id, text) {
  const n = document.getElementById(id);
  if (n) { n.textContent = text || ""; n.setAttribute("aria-label", text || ""); }
}

function renderChart(id, thunk, opts = {}) {
  ensureTheme();
  REGISTRY[id] = thunk;
  REGISTRY_NOTE[id] = opts.note || "";
  const box = document.getElementById(id);
  if (!box) return;
  box.classList.remove("skeleton", "chart-fade");   // restart fade cleanly
  try {
    const spec = thunk();
    // If a non-Plotly view (e.g. the calendar heatmap) rebuilt this div's DOM
    // beneath us, Plotly still thinks it "owns" it (_fullLayout survives
    // innerHTML="") and Plotly.react then quietly updates nothing — the old
    // view sticks. Purge the ghost graph AND clear its leftover DOM, then
    // re-plot; Plotly.react alone would only append on top of the heatmap.
    if ((box._fullLayout || box.classList.contains("js-plotly-plot")) &&
        !box.querySelector("svg")) {
      Plotly.purge(box);
      box.innerHTML = "";
    }
    if (!spec || spec.insufficient) {
      box.innerHTML = "";
      box.appendChild(emptyState(spec ? spec.why : "No data."));
      CHART_TABLE[id] = null;
      setNote(opts.note, spec && spec.why);
      return;
    }
    Plotly.react(box, spec.traces, spec.layout, CONFIG).then(() => {
      box.classList.add("chart-fade");          // 300ms ease-out, CSS-gated
      if (spec.onClick) {
        box.removeAllListeners("plotly_click");
        box.on("plotly_click", spec.onClick);
      }
    });
    CHART_TABLE[id] = spec.table || null;
    setNote(opts.note, spec.aria || "");
  } catch (err) {
    box.classList.remove("chart-fade");
    box.innerHTML = "";
    const errBox = document.createElement("div");
    errBox.className = "chart-error";
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.dataset.retry = id;
    btn.textContent = "↻ Retry";
    errBox.append("Chart failed to render — ", btn);
    box.appendChild(errBox);
    setNote(opts.note, "");
    console.error("chart", id, err);
  }
}

function emptyState(why) {
  const d = document.createElement("div");
  d.className = "chart-empty";
  const h = document.createElement("b"); h.textContent = "Not enough data yet";
  const p = document.createElement("p"); p.textContent = why;
  d.append(h, p);
  return d;
}

/** Toggle rendered by .chip[data-table] — also the accessible fallback. */
function toggleChartTable(id) {
  const box = document.getElementById(id);
  const tbl = document.getElementById("tbl-" + id);
  if (!box || !tbl) return;
  const show = tbl.classList.contains("hidden");
  tbl.classList.toggle("hidden", !show);
  box.style.display = show ? "none" : "";
  if (show) {
    const t = CHART_TABLE[id];
    if (t) {
      /* rows may be prebuilt "<td>…" markup (legacy tables) or plain cells
         (chart tables) — normalize so plain cells get wrapped */
      const rows = t.rows.map(r =>
        r.map(c => String(c).startsWith("<td") ? c : `<td>${c}</td>`).join(""));
      tbl.innerHTML = tableHTML(t.headers, rows);
    } else {
      tbl.innerHTML = "<p class='muted'>No table data (chart is empty).</p>";
    }
  } else if (REGISTRY[id]) {
    Plotly.Plots.resize(box);
  }
}

/* ---------------------------------------------------- series helpers ---- */
function movingAverage(values, w = 3) {
  return values.map((_, i) =>
    i < w - 1 ? null
      : Math.round(values.slice(i - w + 1, i + 1).reduce((s, v) => s + v, 0) / w * 100) / 100);
}

function rgbaOf(hex, alpha) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map(c => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

function pctChange(cur, prev) {
  if (prev === null || prev === undefined || prev === 0) return null;
  return Math.round((cur - prev) / prev * 1000) / 10;
}

function fmtChange(p) {
  return p === null ? "no previous period" :
    (p >= 0 ? `▲ +${p}%` : `▼ ${p}% vs previous`);
}

/* =========================================================================
   BUILDERS — each returns { traces, layout, table, aria, onClick?, … }
   ========================================================================= */

/* ------------------------------------ Income vs Expenses (grouped bars) -- */
function specMonthlyIncomeExpense(ov) {
  if (ov.months.length < 2) return { insufficient: true, why: "Need at least 2 months of transactions to compare income and expenses. Ingest more of your SMS history." };
  const labels = ov.months;
  const tick = niceTicks(0, Math.max(...ov.income, ...ov.spend));

  const bar = (name, ys, color) => ({
    x: labels, y: ys, name, type: "bar",
    marker: { color, cornerradius: 4 },
    hovertemplate: "<b>%{x}</b><br>" + name + " %{customdata[0]}<br>%{customdata[1]}<extra></extra>",
    customdata: ys.map((v, i) => [
      inrFull(v),
      fmtChange(pctChange(v, i > 0 ? ys[i - 1] : null)),
    ]),
  });

  const traces = [
    bar("Income", ov.income, THEME.pink),
    bar("Expenses", ov.spend, THEME.cyan),
    {
      x: labels, y: ov.net, name: "Net", type: "scatter", mode: "lines",
      line: { color: THEME.gold, width: 2.5 },
      hovertemplate: "<b>%{x}</b><br>Net %{customdata[0]}<extra></extra>",
      customdata: ov.net.map(inrFull),
    },
  ];

  const netIdx = ov.net.length - 1;
  const lastNet = ov.net[netIdx];
  const prevNet = ov.net.length > 1 ? ov.net[netIdx - 1] : null;
  const pc = pctChange(lastNet, prevNet);

  return {
    traces,
    layout: {
      ...baseLayout(),
      barmode: "group", bargap: 0.3,
      xaxis: xAxis({ tickangle: -45, automargin: true }),
      yaxis: yAxis([...ov.income, ...ov.spend, ...ov.net]),
      legend: { ...LEGEND_STYLE(), orientation: "h", y: -0.28 },
      margin: { l: 60, r: 16, t: 14, b: 62 },
    },
    // drill-down: month bar -> ledger filtered to that month
    onClick: ev => {
      const label = ev && ev.points && ev.points[0] && ev.points[0].x;
      if (label) gotoLedger({ monthLabel: label });
    },
    table: { headers: ["Month", "Income", "Expenses", "Net"], rows: labels.map((m, i) => [m, inrFull(ov.income[i]), inrFull(ov.spend[i]), inrFull(ov.net[i])]) },
    aria: `Income and expenses over ${labels.length} months. Net this month ${inrFull(lastNet)}, ${fmtChange(pc)}.`,
  };
}

/* ---------------------------------------- Spending trend (area + MA) ---- */
function specSpendingTrend(ov) {
  if (ov.months.length < 3) return { insufficient: true, why: "A trend line needs at least 3 months of data — currently " + ov.months.length + ". Ingest more months of SMS to unlock it." };
  const labels = ov.months, ys = ov.spend;
  const ma = movingAverage(ys, 3);
  const maxI = ys.indexOf(Math.max(...ys));
  const minI = ys.indexOf(Math.min(...ys));

  const traces = [
    { // solid spend line + 10% area fill
      x: labels, y: ys, name: "Spend", type: "scatter", mode: "lines",
      line: { color: THEME.cyan, width: 3, shape: "spline", smoothing: 0.25 },
      fill: "tozeroy", fillcolor: rgbaOf(THEME.cyan, 0.10),
      hovertemplate: "<b>%{x}</b><br>Spent %{customdata[0]}<br>%{customdata[1]}<extra></extra>",
      customdata: ys.map((v, i) => [inrFull(v), fmtChange(pctChange(v, i > 0 ? ys[i - 1] : null))]),
    },
    { // dashed comparison: same month one year earlier
      x: labels.map((m, i) => (i >= 12 ? m : null)),
      y: ys.map((v, i) => (i >= 12 ? ys[i - 12] : null)),
      name: "One year earlier", type: "scatter", mode: "lines",
      line: { color: THEME.muted, width: 2, dash: "dash" },
      connectgaps: false,
      hovertemplate: "<b>%{x}</b><br>A year earlier %{customdata}<extra></extra>",
      customdata: ys.map((v, i) => (i >= 12 ? inrFull(ys[i - 12]) : "")),
    },
    { // 3-month moving average
      x: labels, y: ma, name: "3-mo average", type: "scatter", mode: "lines",
      line: { color: THEME.pink, width: 2, shape: "spline", smoothing: 0.25 },
      connectgaps: false,
      hovertemplate: "<b>%{x}</b><br>3-mo avg %{customdata}<extra></extra>",
      customdata: ma.map(v => (v === null ? "" : inrFull(v))),
    },
    { // highest + lowest labelled markers
      x: [labels[maxI], labels[minI]],
      y: [ys[maxI], ys[minI]],
      type: "scatter", mode: "markers+text", name: "Extremes",
      marker: { color: [THEME.gold, THEME.cyan], size: 10, line: { width: 2, color: THEME.text } },
      text: ["Peak " + inrCompact(ys[maxI]), "Low " + inrCompact(ys[minI])],
      textposition: ["top center", "bottom center"],
      textfont: { size: 11, color: THEME.text },
      hoverinfo: "skip",
    },
  ];

  const last = ys[ys.length - 1], prev = ys[ys.length - 2];
  const pc = pctChange(last, prev);
  return {
    traces,
    layout: {
      ...baseLayout(),
      xaxis: xAxis({ tickangle: -45, automargin: true }),
      yaxis: yAxis(ys),
      legend: { ...LEGEND_STYLE(), orientation: "h", y: -0.28 },
      margin: { l: 60, r: 16, t: 18, b: 62 },
      hovermode: "x unified",
    },
    onClick: ev => {
      const label = ev && ev.points && ev.points[0] && ev.points[0].x;
      if (label) gotoLedger({ monthLabel: label });
    },
    table: { headers: ["Month", "Spend", "3-mo avg"], rows: labels.map((m, i) => [m, inrFull(ys[i]), ma[i] === null ? "–" : inrFull(ma[i])]) },
    aria: `Spending trend over ${labels.length} months: ${fmtChange(pc)} — this month ${inrFull(last)}, peak ${inrFull(ys[maxI])} in ${labels[maxI]}.`,
  };
}

/* ------------------------------------- Expense breakdown (doughnut) ----- */
const DONUT_STATE = { hidden: new Set() };

function specExpenseDonut(ov, totalSpend) {
  const cats = (ov.categories_current || []).filter(c => !DONUT_STATE.hidden.has(c.name));
  if (cats.length < 2) return { insufficient: true, why: "A breakdown needs at least 2 spending categories this month. Add more varied transactions." };

  // top 6 + Other slice, largest first (server already sorts desc)
  let slices = cats.slice(0, 6);
  if (cats.length > 6) {
    slices = slices.concat([{ name: "Other", amount: cats.slice(6).reduce((s, c) => s + c.amount, 0) }]);
  }
  const colors = donutColors(slices.length);
  const total = totalSpend || slices.reduce((s, c) => s + c.amount, 0);

  return {
    traces: [{
      labels: slices.map(c => c.name),
      values: slices.map(c => c.amount),
      type: "pie", hole: 0.68, sort: false, direction: "clockwise",
      marker: { colors, line: { color: "rgba(0,0,0,0.4)", width: 1 } },
      textinfo: "percent", insidetextorientation: "horizontal",
      textfont: { size: 12, color: THEME.text },
      hovertemplate: "<b>%{label}</b><br>%{customdata[0]} · %{customdata[1]}<extra></extra>",
      customdata: slices.map(c => [inrFull(c.amount), (c.amount / total * 100).toFixed(1) + "%"]),
    }],
    layout: {
      ...baseLayout(),
      margin: { l: 4, r: 4, t: 4, b: 4 },
      annotations: [{
        text: inrCompact(total) + "<br><span style='font-size:11px;color:" + THEME.muted + "'>this month</span>",
        showarrow: false, font: { size: 20, color: THEME.text }, x: 0.5, y: 0.5,
      }],
    },
    // slice click -> drill into the ledger for that category
    onClick: ev => {
      const cat = ev && ev.points && ev.points[0] && ev.points[0].label;
      if (cat) gotoLedger({ category: cat });
    },
    table: { headers: ["Category", "Amount", "Share"], rows: slices.map(c => [c.name, inrFull(c.amount), (c.amount / total * 100).toFixed(1) + "%"]) },
    aria: `Expense breakdown: ${slices[0].name} is the largest at ${inrFull(slices[0].amount)} (${(slices[0].amount / total * 100).toFixed(0)}% of ${inrFull(total)}).`,
    legendData: { slices, colors, total },
  };
}

function donutColors(n) {
  const keys = ["violet", "pink", "cyan", "orange", "lime", "yellow", "gold", "red"];
  return Array.from({ length: n }, (_, i) => THEME[keys[i % keys.length]]);
}

/* --------------------------------------- Category × Month (stacked) ----- */
function specCategoryStack(cm) {
  if (!cm || cm.months.length < 2) return { insufficient: true, why: "Need at least 2 months of data to show category trends over time." };
  const traces = cm.categories.map((c, i) => ({
    x: cm.months, y: cm.series[c], name: c, type: "bar",
    marker: { color: donutColors(cm.categories.length)[i], cornerradius: 0 },
    hovertemplate: "<b>%{x}</b><br>" + c + " %{customdata}<extra></extra>",
    customdata: cm.series[c].map(inrFull),
  }));
  const all = Object.values(cm.series).flat();
  return {
    traces,
    layout: {
      ...baseLayout(),
      barmode: "stack", bargap: 0.25,
      xaxis: xAxis({ tickangle: -45, automargin: true }),
      yaxis: yAxis(all),
      legend: { ...LEGEND_STYLE(), orientation: "h", y: -0.34, font: { size: 11, color: THEME.muted } },
      margin: { l: 60, r: 16, t: 12, b: 78 },
      hovermode: "x unified",
    },
    // segment click -> ledger filtered to that category & month
    onClick: ev => {
      const p = ev && ev.points && ev.points[0];
      if (p) gotoLedger({ category: p.data && p.data.name, monthLabel: p.x });
    },
    table: { headers: ["Month", ...cm.categories], rows: cm.months.map((m, i) => [m, ...cm.categories.map(c => inrFull(cm.series[c][i]))]) },
    aria: `Category spending by month across ${cm.categories.length} categories and ${cm.months.length} months.`,
  };
}

/* ------------------------------------------- Merchants (horizontal) ----- */
function specMerchants(list) {
  if (!list || !list.length) return { insufficient: true, why: "No merchant spending detected yet." };
  const top = list.slice(0, 10);
  const rows = top.slice().reverse();          // largest at top
  const trunc = s => s.length > 22 ? s.slice(0, 21) + "…" : s;
  return {
    traces: [{
      y: rows.map(m => trunc(m.merchant)),
      x: rows.map(m => m.amount),
      type: "bar", orientation: "h",
      marker: { color: donutColors(top.length), cornerradius: 4 },
      hovertemplate: "<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]} txns<extra></extra>",
      customdata: rows.map(m => [m.merchant, inrFull(m.amount), m.txns]),
      text: rows.map(m => inrCompact(m.amount)),
      textposition: "outside", textfont: { size: 11.5, color: THEME.muted },
      cliponaxis: false,
    }],
    layout: {
      ...baseLayout(),
      xaxis: { ...xAxis(), tickvals: niceTicks(0, rows[0].amount).tickvals, ticktext: niceTicks(0, rows[0].amount).ticktext, gridcolor: THEME.grid, griddash: "dash", zeroline: false, tickfont: { size: 12, color: THEME.muted }, rangemode: "tozero" },
      yaxis: { showgrid: false, outlinewidth: 0, tickfont: { size: 12, color: THEME.muted } },
      margin: { l: 170, r: 44, t: 8, b: 40 },
      hovermode: "y",
      bargap: 0.35,
    },
    // merchant click -> ledger search filter (full name from customdata)
    onClick: ev => {
      const p = ev && ev.points && ev.points[0];
      if (p && p.customdata && p.customdata[0]) gotoLedger({ search: p.customdata[0] });
    },
    table: { headers: ["Merchant", "Total spend", "Txns"], rows: top.map(m => [m.merchant, inrFull(m.amount), m.txns]) },
    aria: `Top merchant is ${top[0].merchant} with ${inrFull(top[0].amount)} across ${top[0].txns} transactions.`,
  };
}

/* -------------------------------------- Daily bars + avg + 2x spikes ---- */
function specDaily(points, mode, label) {
  if (points.length < 3) return { insufficient: true, why: "Need at least 3 days of spending to show the daily pattern." };
  const amounts = points.map(p => p.amount);
  const avg = amounts.reduce((s, v) => s + v, 0) / amounts.length;
  const hi = avg * 2;
  const colors = amounts.map(v => v > hi ? THEME.gold : "rgba(34,211,238,0.85)");
  const spikeDays = points.filter(p => p.amount > hi);
  const t = niceTicks(0, Math.max(...amounts, 1));

  return {
    traces: [
      {
        x: points.map(p => p.date), y: amounts, type: "bar",
        marker: { color: colors, cornerradius: 4 },
        hovertemplate: "<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]} txns<br>%{customdata[3]}<extra></extra>",
        customdata: points.map(p => [
          prettyDay(p.date), inrFull(p.amount), p.txns,
          p.amount > avg ? ("▲ " + Math.round((p.amount / avg - 1) * 100) + "% vs daily avg") : "below daily avg",
        ]),
      },
      {
        x: [points[0].date, points[points.length - 1].date],
        y: [avg, avg], type: "scatter", mode: "lines",
        line: { color: THEME.muted, width: 1.5, dash: "dash" },
        name: "Daily avg " + inrCompact(avg),
        hoverinfo: "skip", showlegend: false,
      },
    ],
    layout: {
      ...baseLayout(),
      xaxis: xAxis({ tickfont: { size: 12, color: THEME.muted }, type: "date" }),
      yaxis: yAxis(amounts),
      margin: { l: 60, r: 16, t: 12, b: 36 },
      bargap: 0.2,
      annotations: spikeDays.slice(0, 4).map(p => ({
        x: p.date, y: p.amount, text: "▲ " + inrCompact(p.amount), ay: -14,
        showarrow: false, font: { size: 10.5, color: THEME.gold },
      })),
    },
    table: { headers: ["Date", "Spend", "Txns"], rows: points.map(p => [prettyDay(p.date), inrFull(p.amount), p.txns]) },
    aria: `Daily spending ${label}: average ${inrCompact(avg)}/day` +
      (spikeDays.length ? `, ${spikeDays.length} day(s) above 2× the average` : ", no days above 2× the average") + ".",
  };
}

function prettyDay(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/* --------------------------------- Calendar heatmap (GitHub-style) ------ */
/* 5 intensity steps, last 26 weeks, DOM-built (accessible title tooltips). */
function buildCalendarHeatmap(container, daily, weeks = 26) {
  ensureTheme();
  const last = daily.length ? daily[daily.length - 1] : null;
  container.innerHTML = "";
  if (!last) { container.appendChild(emptyState("No daily data yet.")); return; }

  const end = new Date(last.date + "T00:00:00");
  const start = new Date(end); start.setDate(start.getDate() - (weeks * 7 - 1));
  const slice = daily.filter(d => { const t = new Date(d.date + "T00:00:00"); return t >= start; });
  const nonzero = slice.filter(d => d.amount > 0).map(d => d.amount).sort((a, b) => a - b);
  const quintile = f => nonzero[Math.max(0, Math.floor(f * (nonzero.length - 1)))] || 0;
  const levels = [quintile(0.2), quintile(0.4), quintile(0.6), quintile(0.8), Infinity];

  const level = v => v <= 0 ? 0 : levels.findIndex(l => v <= l) + 1;

  const wrap = document.createElement("div");
  wrap.className = "heatmap";
  const maxAmt = Math.max(...slice.map(d => d.amount), 1);
  let cellCount = 0, sum = 0;
  const isoOf = d => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  // start grid aligned to weekday column
  let cur = new Date(start);
  while (cur <= end) {
    const col = document.createElement("div"); col.className = "hm-col";
    for (let dow = 0; dow < 7 && cur <= end; dow++) {
      const iso = isoOf(cur);
      const d = slice.find(x => x.date === iso);
      const v = d ? d.amount : 0;
      sum += v; cellCount++;
      const cell = document.createElement("div");
      cell.className = "hm-cell lv" + (v > 0 ? level(v) : 0);
      cell.title = d ? `${prettyDay(iso)} — ${inrFull(v)} (${d.txns} txn)` : prettyDay(iso) + " — no spend";
      cell.setAttribute("aria-label", cell.title);
      col.appendChild(cell);
      cur.setDate(cur.getDate() + 1);
    }
    wrap.appendChild(col);
  }
  container.appendChild(wrap);

  const legend = document.createElement("div");
  legend.className = "hm-legend";
  legend.innerHTML = "<span>Less</span>" +
    [0, 1, 2, 3, 4, 5].map(l => `<span class="hm-cell lv${l}"></span>`).join("") +
    `<span>More · max ${inrCompact(maxAmt)} · avg ${inrCompact(sum / Math.max(cellCount, 1))}/day</span>`;
  container.appendChild(legend);
}

/* ------------------------------------------ Budget vs Actual (bullet) --- */
function specBudgets(list) {
  const rows = (list || []).filter(b => b.budget > 0 || b.actual > 0).slice(0, 8);
  if (!rows.length) return { insufficient: true, why: "Auto-budgets need at least one previous month: the bar is what you spent this month, the marker is the median of your previous 3 months." };
  if (rows.every(b => b.budget === 0)) return { insufficient: true, why: "Budgets come from your previous months. Ingest one more month of SMS to unlock this." };

  const stateColor = { within: THEME.green, approaching: THEME.gold, exceeded: THEME.red };
  const trunc = s => s.length > 18 ? s.slice(0, 17) + "…" : s;
  const rws = rows.slice().reverse();
  const shapes = [], labels = [];
  rws.forEach((b, i) => {
    shapes.push({ type: "line", x0: b.budget, x1: b.budget, y0: i - 0.32, y1: i + 0.32, line: { color: THEME.text, width: 2.5 } });
    labels.push(`${b.icon} ${b.state}`);
  });
  return {
    traces: [{
      y: rws.map(b => trunc(b.category)),
      x: rws.map(b => b.actual),
      type: "bar", orientation: "h",
      marker: { color: rws.map(b => stateColor[b.state]), cornerradius: 4 },
      text: labels, textposition: "outside", cliponaxis: false,
      textfont: { size: 11, color: THEME.muted },
      hovertemplate: "<b>%{customdata[0]}</b><br>Actual %{customdata[1]} / budget %{customdata[2]} (%{customdata[3]})<extra></extra>",
      customdata: rws.map(b => [b.category, inrFull(b.actual), inrFull(b.budget), Math.round(b.actual / Math.max(b.budget, 1) * 100) + "% of budget"]),
    }],
    layout: {
      ...baseLayout(),
      xaxis: { ...xAxis(), gridcolor: THEME.grid, griddash: "dash", zeroline: false, tickvals: niceTicks(0, Math.max(...rws.map(b => Math.max(b.actual, b.budget)))).tickvals, ticktext: niceTicks(0, Math.max(...rws.map(b => Math.max(b.actual, b.budget)))).ticktext, tickfont: { size: 12, color: THEME.muted }, rangemode: "tozero" },
      yaxis: { showgrid: false, outlinewidth: 0, tickfont: { size: 12, color: THEME.muted }, automargin: true },
      shapes,
      margin: { l: 150, r: 110, t: 8, b: 40 },
      bargap: 0.4,
    },
    table: { headers: ["Category", "Budget (3-mo median)", "Actual", "State"], rows: rows.map(b => [b.category, inrFull(b.budget), inrFull(b.actual), b.icon + " " + b.state]) },
    aria: `${rows.filter(b => b.state === "exceeded").length} of ${rows.length} categories exceeded their auto-budget this month.`,
  };
}

/* --------------------------------------- Cash-flow waterfall ------------ */
function specWaterfall(w) {
  if (!w || (w.income === 0 && w.expenses === 0)) return { insufficient: true, why: "The waterfall needs a few months of income and expenses. Ingest more data." };
  const items = [w.opening, w.income, -w.expenses, w.net];
  return {
    traces: [{
      type: "waterfall",
      measure: ["absolute", "relative", "relative", "total"],
      x: ["Opening", "Income", "Expenses", "Net"],
      y: items,
      textposition: "outside",
      cliponaxis: false,
      connector: { line: { color: THEME.muted, width: 1, dash: "dot" } },
      increasing: { marker: { color: THEME.pink } },
      decreasing: { marker: { color: THEME.red } },
      totals: { marker: { color: THEME.gold } },
      hovertemplate: "<b>%{x}</b><br>%{customdata}<extra></extra>",
      customdata: [
        "opening balance " + inrFull(w.opening),
        "income + " + inrFull(w.income),
        "expenses − " + inrFull(w.expenses),
        "ends at " + inrFull(w.net),
      ],
    }],
    layout: {
      ...baseLayout(),
      yaxis: yAxis([Math.min(...items, 0), Math.max(...items, 0)]),
      xaxis: xAxis(),
      margin: { l: 60, r: 16, t: 14, b: 34 },
      waterfallgap: 0.3,
    },
    table: { headers: ["Step", "Amount"], rows: [["Opening", inrFull(w.opening)], ["Income", inrFull(w.income)], ["Expenses", "-" + inrFull(w.expenses)], ["Net", inrFull(w.net)]] },
    aria: `Cash flow ${w.window}: opened at ${inrFull(w.opening)}, earned ${inrFull(w.income)}, spent ${inrFull(w.expenses)}, now at ${inrFull(w.net)}.`,
  };
}

/* --------------------------------------- Month-end forecast ------------- */
function specForecast(f) {
  if (!f || !f.dates || f.dates.length < 3) return { insufficient: true, why: "The forecast needs a few days of activity in the current month." };
  const lastElapsed = f.dates[f.days_elapsed - 1];
  const remDates = f.dates.slice(f.days_elapsed).map(d => d);
  const startCum = f.cumulative[f.days_elapsed - 1];
  const projected = remDates.map((_, i) => Math.round((startCum + f.avg_daily * (i + 1)) * 100) / 100);

  const traces = [
    { // actual cumulative line
      x: f.dates.slice(0, f.days_elapsed), y: f.cumulative.slice(0, f.days_elapsed),
      type: "scatter", mode: "lines", name: "Spent so far",
      line: { color: THEME.cyan, width: 3, shape: "spline", smoothing: 0.25 },
      fill: "tozeroy", fillcolor: rgbaOf(THEME.cyan, 0.10),
      hovertemplate: "<b>%{x|%d %b}</b><br>Cumulative %{customdata}<extra></extra>",
      customdata: f.cumulative.slice(0, f.days_elapsed).map(inrFull),
    },
    { // dashed projection, clearly labelled Estimated
      x: [lastElapsed, ...remDates], y: [startCum, ...projected],
      type: "scatter", mode: "lines", name: "Estimated",
      line: { color: THEME.orange, width: 2.5, dash: "dash", shape: "spline", smoothing: 0.25 },
      hovertemplate: "<b>%{x|%d %b} (estimated)</b><br>%{customdata}<extra></extra>",
      customdata: [inrFull(startCum), ...projected.map(inrFull)],
    },
  ];
  return {
    traces,
    layout: {
      ...baseLayout(),
      xaxis: xAxis({ type: "date", range: [f.dates[0], f.dates[f.dates.length - 1]] }),
      yaxis: yAxis([Math.max(...f.cumulative), f.projected_end]),
      legend: { ...LEGEND_STYLE(), orientation: "h", y: -0.2 },
      margin: { l: 60, r: 16, t: 14, b: 42 },
      annotations: [{
        x: f.dates[f.dates.length - 1], y: f.projected_end,
        text: "Estimated " + inrCompact(f.projected_end) + " by " + f.month_label.split(" ")[0] + " end",
        showarrow: true, arrowhead: 0, ax: -70, ay: -18,
        font: { size: 11.5, color: THEME.orange },
      }],
    },
    table: { headers: ["Date", "Cumulative", "Note"], rows: f.dates.map((d, i) => [prettyDay(d), inrFull(i >= f.days_elapsed ? startCum + f.avg_daily * (i - f.days_elapsed + 1) : f.cumulative[i]), i >= f.days_elapsed ? "estimated" : ""]) },
    aria: `${f.month_label}: spent ${inrFull(f.spent_so_far)} in ${f.days_elapsed} days (avg ${inrCompact(f.avg_daily)}/day) — projected month-end ${inrFull(f.projected_end)}.`,
  };
}

/* ------------------------------------ Zombies + gauge + inflation ------- */
function specZombieChart(z) {
  const items = (z && z.items) || [];
  if (!items.length) {
    const rec = z && z.other_recurring && z.other_recurring.length
      ? ` Deliberate recurring payments stay out of the alarm list: ${z.other_recurring.slice(0, 6).join(", ")}.`
      : "";
    return { insufficient: true, why: "No forgotten-subscription charges detected in your history." + rec };
  }
  const top = items.slice(0, 8).reverse();
  return {
    traces: [{
      y: top.map(i => i.merchant.length > 24 ? i.merchant.slice(0, 23) + "…" : i.merchant),
      x: top.map(i => i.annualized), type: "bar", orientation: "h",
      marker: { color: top.map(i => i.status === "active" ? THEME.red : THEME.muted), cornerradius: 4 },
      text: top.map(i => inrCompact(i.annualized)), textposition: "outside", cliponaxis: false,
      hovertemplate: "<b>%{customdata[0]}</b><br>%{customdata[1]} · gap≈%{customdata[2]}d<extra></extra>",
      customdata: top.map(i => [i.merchant, i.frequency, i.interval_days]),
    }],
    layout: {
      ...baseLayout(),
      xaxis: { ...xAxis(), gridcolor: THEME.grid, griddash: "dash", zeroline: false, tickvals: niceTicks(0, top[top.length - 1].annualized).tickvals, ticktext: niceTicks(0, top[top.length - 1].annualized).ticktext, tickfont: { size: 12, color: THEME.muted }, rangemode: "tozero" },
      yaxis: { showgrid: false, outlinewidth: 0, tickfont: { size: 12, color: THEME.muted }, automargin: true },
      margin: { l: 165, r: 52, t: 8, b: 40 },
      bargap: 0.35,
    },
    table: { headers: ["Merchant", "Annualized"], rows: top.map(i => [i.merchant, inrFull(i.annualized)]) },
    aria: `${items.length} recurring payments; the largest costs ${inrFull(items[0] && items[0].annualized || 0)} per year.`,
  };
}

function specInflationChart(d) {
  if (!d || d.empty) return { insufficient: true, why: "Inflation tracking needs a few recurring spending categories spread over several months." };
  const a = { x: d.months, y: d.personal_index, name: "You", type: "scatter", mode: "lines", line: { color: THEME.orange, width: 3 }, customdata: d.months.map(() => "") };
  const c = { x: d.months, y: d.cpi_index, name: "Govt CPI", type: "scatter", mode: "lines", line: { color: THEME.cyan, width: 2, dash: "dash" } };
  const all = [...d.personal_index, ...d.cpi_index];
  return {
    traces: [c, a],
    layout: {
      ...baseLayout(),
      xaxis: xAxis({ tickangle: -45, automargin: true }),
      yaxis: { gridcolor: THEME.grid, griddash: "dash", zeroline: false, outlinewidth: 0, tickfont: { size: 12, color: THEME.muted }, tickformat: ",.0f", title: { text: "Price index (start=100)", font: { size: 12, color: THEME.muted } } },
      legend: { ...LEGEND_STYLE(), orientation: "h", y: -0.28 },
      margin: { l: 55, r: 16, t: 14, b: 62 },
      hovermode: "x unified",
    },
    table: { headers: ["Month", "You", "CPI"], rows: d.months.map((m, i) => [m, d.personal_index[i], d.cpi_index[i]]) },
    aria: `Your basket index ends at ${d.personal_index[d.personal_index.length - 1]} vs CPI ${d.cpi_index[d.cpi_index.length - 1]}.`,
  };
}

function specGauge(d) {
  if (!d || d.empty) return { insufficient: true, why: "The health score needs your ingested data." };
  const gradeColors = { "Excellent": THEME.green, "Good": THEME.lime, "Fair": THEME.gold, "Needs Attention": THEME.red };
  return {
    traces: [{
      type: "indicator", mode: "gauge+number", value: d.score,
      number: { suffix: "/100", font: { size: 44, color: gradeColors[d.grade] || THEME.text } },
      gauge: {
        axis: { range: [0, 100], tickwidth: 1, tickcolor: THEME.muted },
        bar: { color: gradeColors[d.grade] || THEME.violet, thickness: 0.32 },
        bgcolor: "rgba(0,0,0,0)", borderwidth: 0,
        steps: [
          { range: [0, 40], color: "rgba(244,63,94,0.16)" },
          { range: [40, 60], color: "rgba(251,191,36,0.16)" },
          { range: [60, 80], color: "rgba(163,230,53,0.14)" },
          { range: [80, 100], color: "rgba(52,211,153,0.18)" },
        ],
      },
      hoverinfo: "skip",
    }],
    layout: { ...baseLayout(), height: 300, margin: { l: 30, r: 30, t: 30, b: 10 } },
    table: { headers: ["Score", "Grade"], rows: [[d.score, d.grade]] },
    aria: `Financial health score ${d.score} out of 100 — ${d.grade}.`,
  };
}

/* =========================================================================
   TABLE ⇄ VIZ builders — the table-centric views (Ledger filters, zombie
   detail, inflation detail, health components, ingest report) get the same
   visual voice as the overview charts: renderChart() wrapper, THEME colors,
   compact ₹ axes, drill-down clicks, aria note and a per-spec table set.
   ========================================================================= */

function _monthLbl(key) {                     /* "2025-10" -> "Oct 25" (ui.js) */
  try { return monthLabel(key); } catch (_) { return key; }
}

function zombieEmptyWhy(z) {
  const rec = z && z.other_recurring && z.other_recurring.length
    ? " Deliberate recurring payments stay out of the alarm list: " +
      z.other_recurring.slice(0, 6).join(", ") + "."
    : "";
  return "No forgotten-subscription charges detected in your history." + rec;
}

/* ------------------------------------------------ Ledger visual modes ---- */
function specLedgerViz(rows, mode) {
  if (!rows || !rows.length)
    return { insufficient: true, why: "No transactions match the current filters — loosen them or ingest more data." };
  const debits = rows.filter(r => r.direction === "debit");

  if (mode === "pie") {
    if (!debits.length)
      return { insufficient: true, why: "The current filter has no debit rows — a spend-share pie needs spending." };
    const sums = {};
    debits.forEach(r => sums[r.category] = (sums[r.category] || 0) + r.amount);
    let cats = Object.entries(sums).sort((a, b) => b[1] - a[1]);
    if (cats.length > 7)
      cats = cats.slice(0, 7).concat([["Other", cats.slice(7).reduce((s, c) => s + c[1], 0)]]);
    const total = debits.reduce((s, r) => s + r.amount, 0);
    return {
      traces: [{
        labels: cats.map(c => c[0] === "Other" ? "Other" : c[0]),
        values: cats.map(c => c[1]),
        type: "pie", hole: 0.45, sort: false, direction: "clockwise",
        marker: { colors: donutColors(cats.length), line: { color: "rgba(0,0,0,0.4)", width: 1 } },
        textinfo: "percent", insidetextorientation: "horizontal",
        textfont: { size: 12, color: THEME.text },
        hovertemplate: "<b>%{label}</b><br>%{customdata[0]} · %{customdata[1]}<extra></extra>",
        customdata: cats.map(c => [inrFull(c[1]), (c[1] / total * 100).toFixed(1) + "%"]),
      }],
      layout: {
        ...baseLayout(),
        margin: { l: 4, r: 4, t: 4, b: 4 },
        annotations: [{
          text: inrCompact(total) + "<br><span style='font-size:11px;color:" + THEME.muted + "'>debits in view</span>",
          showarrow: false, font: { size: 18, color: THEME.text }, x: 0.5, y: 0.5,
        }],
      },
      onClick: ev => {
        const cat = ev && ev.points && ev.points[0] && ev.points[0].label;
        if (cat && cat !== "Other") gotoLedger({ category: cat });
      },
      table: { headers: ["Category", "Spend", "Share"], rows: cats.map(c => [c[0], inrFull(c[1]), (c[1] / total * 100).toFixed(1) + "%"]) },
      aria: `Spend share across ${cats.length} categories in the current filter; ${cats[0][0]} leads at ${inrFull(cats[0][1])}.`,
    };
  }

  if (mode === "scatter") {
    const sorted = rows.slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    const mk = (name, dir, color) => {
      const pts = sorted.filter(r => r.direction === dir);
      return {
        x: pts.map(r => r.date), y: pts.map(r => r.amount),
        name, type: "scatter", mode: "markers",
        marker: { color, size: 7, opacity: 0.75, line: { width: 0 } },
        hovertemplate: "<b>%{customdata[1]}</b><br>%{x}<br>%{customdata[0]}<extra>" + name + "</extra>",
        customdata: pts.map(r => [inrFull(r.amount), r.merchant]),
      };
    };
    return {
      traces: [mk("Debits", "debit", THEME.red), mk("Credits", "credit", THEME.green)],
      layout: {
        ...baseLayout(),
        xaxis: xAxis({ type: "date" }),
        yaxis: yAxis(sorted.map(r => r.amount)),
        legend: { ...LEGEND_STYLE(), orientation: "h", y: -0.2 },
        margin: { l: 60, r: 16, t: 10, b: 56 },
      },
      table: {
        headers: ["Date", "Merchant", "Category", "Amount"],
        rows: sorted.slice(0, 200).map(r => [r.date, r.merchant, r.category, inrFull(r.amount)]),
      },
      aria: `Timeline of ${sorted.length} transactions in the current filter (${debits.length} debits, ${sorted.length - debits.length} credits).`,
    };
  }

  // default: "bar" — monthly debit totals stacked by the top 6 categories
  if (!debits.length)
    return { insufficient: true, why: "The current filter has no debit rows — switch to Table or loosen the filters." };
  const catSum = {};
  debits.forEach(r => catSum[r.category] = (catSum[r.category] || 0) + r.amount);
  const top = Object.entries(catSum).sort((a, b) => b[1] - a[1]).slice(0, 6).map(c => c[0]);
  const monthSet = [...new Set(debits.map(r => (r.date || "").slice(0, 7)).filter(Boolean))].sort();
  const months = monthSet.slice(-12);
  const totalBy = {};
  debits.forEach(r => totalBy[r.date && r.date.slice(0, 7)] = (totalBy[r.date.slice(0, 7)] || 0) + r.amount);
  const traces = top.map((c, i) => ({
    x: months.map(_monthLbl),
    y: months.map(m => debits.filter(r => r.category === c && r.date.slice(0, 7) === m)
                              .reduce((s, r) => s + r.amount, 0)),
    name: c, type: "bar",
    marker: { color: donutColors(top.length)[i], cornerradius: 0 },
    hovertemplate: "<b>%{x}</b><br>" + c + " %{customdata}<extra></extra>",
    customdata: months.map(m => inrFull(debits.filter(r => r.category === c && r.date.slice(0, 7) === m)
                                              .reduce((s, r) => s + r.amount, 0))),
  }));
  return {
    traces,
    layout: {
      ...baseLayout(),
      barmode: "stack", bargap: 0.3,
      xaxis: xAxis({ tickangle: -45, automargin: true }),
      yaxis: yAxis(traces.map(t => Math.max(...t.y, 1))),
      legend: { ...LEGEND_STYLE(), orientation: "h", y: -0.3, font: { size: 11, color: THEME.muted } },
      margin: { l: 60, r: 16, t: 12, b: 74 },
      hovermode: "x unified",
    },
    onClick: ev => {
      const p = ev && ev.points && ev.points[0];
      if (p) gotoLedger({ monthLabel: p.x, category: (p.data && p.data.name !== "Other") ? p.data.name : null });
    },
    table: {
      headers: ["Month", ...top, "Total"],
      rows: months.map(m => [_monthLbl(m),
        ...top.map(c => inrFull(debits.filter(r => r.category === c && r.date.slice(0, 7) === m).reduce((s, r) => s + r.amount, 0))),
        inrFull(totalBy[m] || 0)]),
    },
    aria: `Monthly debit totals for the last ${months.length} month(s) in the current filter, stacked by top ${top.length} categories; peak month ${_monthLbl(months[traces.reduce((best, t, i) => (t.y.reduce((a, b) => a + b, 0) > best.s ? { i, s: t.y.reduce((a, b) => a + b, 0) } : best), { i: 0, s: 0 }).i])}.`,
  };
}

/* ------------------------------------------------ Zombie visual modes ---- */
function specZombieViz(z, mode) {
  if (mode === "bar") return specZombieChart(z);
  const items = (z && z.items) || [];
  if (!items.length) return { insufficient: true, why: zombieEmptyWhy(z) };

  if (mode === "scatter") {
    const s = items.slice().sort((a, b) => a.interval_days - b.interval_days);
    return {
      traces: [{
        x: s.map(i => i.interval_days), y: s.map(i => i.annualized),
        type: "scatter", mode: "markers", name: "Recurring payments",
        marker: {
          color: s.map(i => i.status === "active" ? THEME.red : THEME.muted),
          size: s.map(i => Math.min(26, 8 + i.txn_count * 2)),
          opacity: 0.8, line: { width: 1, color: THEME.text },
        },
        hovertemplate: "<b>%{customdata[0]}</b><br>≈%{x}d gap · %{customdata[1]} txns · %{customdata[2]}/yr<extra></extra>",
        customdata: s.map(i => [i.merchant, i.txn_count, inrFull(i.annualized)]),
      }],
      layout: {
        ...baseLayout(),
        xaxis: xAxis({ title: { text: "median gap days (26–37 = monthly)", font: { size: 11.5, color: THEME.muted } } }),
        yaxis: yAxis(items.map(i => i.annualized)),
        margin: { l: 60, r: 16, t: 10, b: 52 },
        showlegend: false,
      },
      // point click -> open that merchant in the Ledger
      onClick: ev => {
        const p = ev && ev.points && ev.points[0];
        if (p) gotoLedger({ search: p.customdata[0] });
      },
      table: {
        headers: ["Merchant", "Gap days", "Txns", "Annualized"],
        rows: s.map(i => [i.merchant, i.interval_days, i.txn_count, inrFull(i.annualized)]),
      },
      aria: `Recurring pattern scatter across ${items.length} payments; marker size = how many charges seen.`,
    };
  }

  // "pie" — lifetime cost share
  const top = items.slice().sort((a, b) => b.lifetime_spend - a.lifetime_spend).slice(0, 8);
  const total = top.reduce((s, i) => s + i.lifetime_spend, 0);
  return {
    traces: [{
      labels: top.map(i => i.merchant.length > 24 ? i.merchant.slice(0, 23) + "…" : i.merchant),
      values: top.map(i => i.lifetime_spend),
      type: "pie", hole: 0.45, sort: false, direction: "clockwise",
      marker: { colors: donutColors(top.length), line: { color: "rgba(0,0,0,0.4)", width: 1 } },
      textinfo: "percent", insidetextorientation: "horizontal",
      textfont: { size: 12, color: THEME.text },
      hovertemplate: "<b>%{label}</b><br>%{customdata[0]} lifetime · %{customdata[1]}<extra></extra>",
      customdata: top.map(i => [inrFull(i.lifetime_spend), (i.lifetime_spend / total * 100).toFixed(1) + "%"]),
    }],
    layout: {
      ...baseLayout(),
      margin: { l: 4, r: 4, t: 4, b: 4 },
      annotations: [{
        text: inrCompact(total) + "<br><span style='font-size:11px;color:" + THEME.muted + "'>lifetime spend</span>",
        showarrow: false, font: { size: 18, color: THEME.text }, x: 0.5, y: 0.5,
      }],
    },
    table: {
      headers: ["Merchant", "Lifetime", "Share"],
      rows: top.map(i => [i.merchant, inrFull(i.lifetime_spend), (i.lifetime_spend / total * 100).toFixed(1) + "%"]),
    },
    aria: `${items.length} recurring payments; ${top[0].merchant} owns ${(top[0].lifetime_spend / total * 100).toFixed(0)}% of lifetime cost.`,
  };
}

/* ---------------------------------------------- Inflation visual modes --- */
function specInflationViz(d, mode) {
  if (!d || d.empty)
    return { insufficient: true, why: "Inflation tracking needs a few recurring spending categories spread over several months." };
  if (mode === "lines") return specInflationChart(d);
  const cats = d.categories || [];
  if (!cats.length)
    return { insufficient: true, why: "No basket category met the eligibility threshold yet — keep ingesting months of data." };

  if (mode === "pie") {
    const total = cats.reduce((s, c) => s + c.weight, 0) || 1;
    return {
      traces: [{
        labels: cats.map(c => c.name), values: cats.map(c => c.weight),
        type: "pie", hole: 0.45, sort: false, direction: "clockwise",
        marker: { colors: donutColors(cats.length), line: { color: "rgba(0,0,0,0.4)", width: 1 } },
        textinfo: "percent", insidetextorientation: "horizontal",
        textfont: { size: 12, color: THEME.text },
        hovertemplate: "<b>%{label}</b><br>%{customdata[0]} of basket · avg %{customdata[1]}/mo<extra></extra>",
        customdata: cats.map(c => [c.weight + "%", inrFull(c.monthly_avg)]),
      }],
      layout: {
        ...baseLayout(),
        margin: { l: 4, r: 4, t: 4, b: 4 },
        annotations: [{
          text: "basket<br><span style='font-size:11px;color:" + THEME.muted + "'>weights</span>",
          showarrow: false, font: { size: 17, color: THEME.text }, x: 0.5, y: 0.5,
        }],
      },
      table: {
        headers: ["Basket Category", "Weight", "Avg / Month"],
        rows: cats.map(c => [c.name, c.weight + "%", inrFull(c.monthly_avg)]),
      },
      aria: `Personal basket weight share: ${cats[0].name} dominates at ${cats[0].weight}% of tracked spend.`,
    };
  }

  // "trendbar" — annualized per-category moves, green below / red above CPI
  const rows = cats.slice().sort((a, b) => a.yoy - b.yoy);
  return {
    traces: [{
      y: rows.map(c => c.name), x: rows.map(c => c.yoy),
      type: "bar", orientation: "h",
      marker: {
        color: rows.map(c => c.yoy > d.cpi_yoy ? THEME.red : c.yoy >= 0 ? THEME.gold : THEME.green),
        cornerradius: 4,
      },
      text: rows.map(c => (c.yoy >= 0 ? "+" : "") + c.yoy + "%"),
      textposition: "outside", cliponaxis: false,
      textfont: { size: 11.5, color: THEME.muted },
      hovertemplate: "<b>%{customdata[0]}</b><br>%{x}% per year · weight %{customdata[1]}% · avg %{customdata[2]}/mo<extra></extra>",
      customdata: rows.map(c => [c.name, c.weight, inrFull(c.monthly_avg)]),
    }],
    layout: {
      ...baseLayout(),
      xaxis: { ...xAxis(), range: [Math.min(0, ...rows.map(c => c.yoy)), Math.max(5, d.cpi_yoy + 2)],
               zeroline: true, zerolinecolor: THEME.grid,
               ticksuffix: "%", tickfont: { size: 12, color: THEME.muted } },
      yaxis: { showgrid: false, outlinewidth: 0, tickfont: { size: 12, color: THEME.muted }, automargin: true },
      shapes: [{ type: "line", x0: d.cpi_yoy, x1: d.cpi_yoy, y0: -0.5, y1: rows.length - 0.5,
                 line: { color: THEME.cyan, width: 2, dash: "dash" } }],
      margin: { l: 150, r: 64, t: 8, b: 40 },
      bargap: 0.35,
    },
    table: {
      headers: ["Basket Category", "Trend / Year", "Weight", "Avg / Month"],
      rows: rows.map(c => [c.name, (c.yoy >= 0 ? "+" : "") + c.yoy + "%", c.weight + "%", inrFull(c.monthly_avg)]),
    },
    aria: `Per-category annual trends; CPI ${d.cpi_yoy}% shown as the cyan dashed line. Categories right of it are rising faster than the country.`,
  };
}

/* --------------------------------------- Health components (from table) -- */
function specHealthViz(h, mode) {
  const comps = (h && h.components) || [];
  if (!comps.length)
    return { insufficient: true, why: "The health score needs your ingested data." };
  if (mode === "table") return null;                       // handled by renderViz
  const rows = comps.slice().sort((a, b) => a.score - b.score);
  const col = v => v >= 70 ? THEME.green : v >= 40 ? THEME.gold : THEME.red;
  return {
    traces: [{
      y: rows.map(c => c.name), x: rows.map(c => c.score),
      type: "bar", orientation: "h",
      marker: { color: rows.map(c => col(c.score)), cornerradius: 4 },
      text: rows.map(c => String(c.score)), textposition: "outside", cliponaxis: false,
      textfont: { size: 11.5, color: THEME.muted },
      hovertemplate: "<b>%{customdata[0]}</b><br>weight %{customdata[1]}% · %{customdata[2]} · score %{x}<extra></extra>",
      customdata: rows.map(c => [c.name, c.weight, c.raw]),
    }],
    layout: {
      ...baseLayout(),
      xaxis: { ...xAxis(), range: [0, 108], gridcolor: THEME.grid, griddash: "dash",
               zeroline: false, tickfont: { size: 12, color: THEME.muted }, rangemode: "tozero" },
      yaxis: { showgrid: false, outlinewidth: 0, tickfont: { size: 12, color: THEME.muted }, automargin: true },
      margin: { l: 150, r: 44, t: 8, b: 38 },
      bargap: 0.4,
    },
    table: {
      headers: ["Component", "Weight", "Raw Metric", "Score"],
      rows: comps.map(c => [c.name, c.weight + "%", c.raw, c.score]),
    },
    aria: `Component scores: weakest ${rows[0].name} at ${rows[0].score}, strongest ${rows[rows.length - 1].name} at ${rows[rows.length - 1].score}.`,
  };
}

/* ------------------------------------------ Ingest report (parse funnel) -- */
function specIngestViz(r, mode) {
  if (!r)
    return { insufficient: true, why: "No ingest run yet — paste SMS, upload a dump, or load the demo dataset." };
  if (mode === "table") return null;                       // handled by renderViz
  const stats = [
    ["rows in", r.rows_in ?? r.messages_in_file ?? null, THEME.orange],
    ["messages in file", r.messages_in_file ?? null, THEME.orange],
    ["parsed", r.parsed ?? null, THEME.green],
    ["skipped (non-transactions)", r.failed ?? null, THEME.muted],
    ["duplicates removed", r.duplicates_removed ?? null, THEME.gold],
    ["already in database", r.already_stored ?? null, THEME.yellow],
    ["unknown merchants", r.unknown_merchants ?? null, THEME.pink],
    ["rows stored", r.rows_out ?? null, THEME.cyan],
    ["total in DB", r.stored_total ?? null, THEME.violet],
  ].filter(s => s[1] !== null && s[1] !== undefined);
  const rows = stats.slice().reverse();
  return {
    traces: [{
      y: rows.map(s => s[0]), x: rows.map(s => s[1]),
      type: "bar", orientation: "h",
      marker: { color: rows.map(s => s[2]), cornerradius: 4 },
      text: rows.map(s => String(s[1])), textposition: "outside", cliponaxis: false,
      textfont: { size: 11.5, color: THEME.muted },
      hovertemplate: "<b>%{y}</b><br>%{x}<extra></extra>",
    }],
    layout: {
      ...baseLayout(),
      xaxis: { ...xAxis(), gridcolor: THEME.grid, griddash: "dash", zeroline: false,
               rangemode: "tozero", tickfont: { size: 12, color: THEME.muted } },
      yaxis: { showgrid: false, outlinewidth: 0, tickfont: { size: 12, color: THEME.muted }, automargin: true },
      margin: { l: 200, r: 66, t: 8, b: 38 },
      bargap: 0.4,
    },
    table: { headers: ["Stage", "Count"], rows: stats.map(s => [s[0], s[1]]) },
    aria: `Parse funnel: ${r.parsed ?? 0} parsed from ${r.rows_in ?? r.messages_in_file ?? "?"} rows, ${r.duplicates_removed ?? 0} duplicates removed, ${r.rows_out ?? 0} stored.`,
  };
}

