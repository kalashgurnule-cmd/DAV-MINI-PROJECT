/* Boot + tab orchestration. Empty-state hero until data is ingested,
   then every tab renders through the shared chart wrapper in charts.js. */

const state = {
  overview: null,
  zombies: null,
  inflation: null,
  health: null,
  charts: null,
  ledgerRows: [],
  hasData: false,
  dailyRange: "30",        // 30 | 90 | all
  dailyMode: "bars",       // bars | heat
  viz: {                   // table ⇄ chart mode per card (data-viz chips)
    ledger: "table",       // table | bar | pie | scatter
    zombies: "bar",        // bar | scatter | pie
    inflation: "lines",    // lines | pie | trendbar
    health: "table",       // table | bar
    ingest: "table",       // table | bar
  },
  ledgerFiltered: [],      // rows after the ledger filters (feed the viz)
  lastIngestReport: null,  // latest parse funnel counts
};

/* ------------------------------------------------ data load ---------------- */
async function loadAll() {
  const [ov, z, inf, hs, ledger, charts] = await Promise.all([
    API.overview(), API.zombies(), API.inflation(), API.healthScore(),
    API.transactions(), API.charts(),
  ]);
  state.overview = ov; state.zombies = z; state.inflation = inf;
  state.health = hs; state.charts = charts; state.ledgerRows = ledger;
  state.hasData = ledger.length > 0;

  renderKpiStrip(state.hasData ? ov : null);
  el("zombie-badge").textContent = state.hasData ? (z.count ?? 0) : 0;
  fillCategorySelect(ledger);
  applyLedgerFilters();
  switchTab(currentTab);
}

/* ------------------------------------------------ per-tab routing ---------- */
function activate(tab) {
  document.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.tab === tab));

  if (!state.hasData && tab !== "ingest") {
    document.querySelectorAll(".panel").forEach(p =>
      p.classList.toggle("hidden", p.id !== "empty-hero"));
    return;
  }
  document.querySelectorAll(".panel").forEach(p =>
    p.classList.toggle("hidden", p.id !== "panel-" + tab));

  if (tab === "overview") renderOverview();
  if (tab === "zombies") renderZombiesTab();
  if (tab === "inflation") renderInflationTab();
  if (tab === "health") renderHealthTab();
  if (tab === "ingest") renderViz("ingest");   // keeps the parse funnel current
  applyDailyModeVisibility();
}

/* ------------------------------------------------ overview charts ---------- */
function renderOverview() {
  const ov = state.overview, c = state.charts;

  renderChart("chart-monthly", () => specMonthlyIncomeExpense(ov), { note: "note-monthly" });
  renderChart("chart-trend", () => specSpendingTrend(ov), { note: "note-trend" });

  const donutGet = () => specExpenseDonut(ov, ov.month_spend);
  renderChart("chart-donut", donutGet, { note: "note-donut" });
  renderDonutLegend(donutGet().legendData);

  renderChart("chart-stack",
    () => specCategoryStack(c && c.category_months), { note: "note-stack" });

  renderDaily();
  syncDailyChips();

  renderChart("chart-waterfall",
    () => specWaterfall(c && c.waterfall), { note: "note-waterfall" });
  renderChart("chart-forecast",
    () => specForecast(c && c.forecast), { note: "note-forecast" });
  renderChart("chart-budget",
    () => specBudgets(c && c.budgets), { note: "note-budget" });
  renderChart("chart-merchants",
    () => specMerchants(c && c.merchants), { note: "note-merchants" });
}

/* --------------------------------------------------- daily card ------------ */
function dailyPoints() {
  const c = state.charts;
  if (!c) return null;
  if (state.dailyRange === "all") {
    /* >500 points -> aggregate to weekly buckets (integrity rule) */
    return c.daily.length > 500
      ? { pts: c.weekly, label: "every week across full history" }
      : { pts: c.daily, label: "every day across full history" };
  }
  const n = +state.dailyRange;
  return { pts: c.daily.slice(-n), label: `last ${n} days` };
}

function renderDaily() {
  const c = state.charts;
  if (state.dailyMode === "heat") {
    const box = el("chart-daily");
    box.classList.remove("skeleton");
    box.innerHTML = "";
    buildCalendarHeatmap(box, c ? c.daily : []);
    CHART_TABLE["chart-daily"] = c
      ? { headers: ["Date", "Spend", "Txns"], rows: c.daily.slice(-182).map(p => [prettyDay(p.date), inrFull(p.amount), p.txns]) }
      : null;
    setNote("note-daily", "GitHub-style calendar: 5 intensity steps, hover a square for the exact amount");
    return;
  }
  const sel = dailyPoints();
  if (!sel) return;
  renderChart("chart-daily",
    () => specDaily(sel.pts, state.dailyRange, sel.label), { note: "note-daily" });
}

function syncDailyChips() {
  document.querySelectorAll(".chip[data-drange]").forEach(b =>
    b.classList.toggle("active", b.dataset.drange === state.dailyRange));
  document.querySelectorAll(".chip[data-dmode]").forEach(b =>
    b.classList.toggle("active", b.dataset.dmode === state.dailyMode));
}

function applyDailyModeVisibility() {
  /* nothing extra for now — both views live in the same body */
}

/* ------------------------------------------------ zombies / inflation ------ */
function renderZombiesTab() {
  const z = state.zombies;
  renderZombieKpis(z);
  renderZombieTable(z.items || []);
  renderViz("zombies");
}

function renderInflationTab() {
  const d = state.inflation;
  renderInflationKpis(d);
  renderInflationTable(d.categories || []);
  renderViz("inflation");
}

function renderHealthTab() {
  const h = state.health;
  renderChart("chart-gauge", () => specGauge(h), { note: "note-gauge" });
  renderHealthTable(h.components || []);        // fresh DOM for when table mode returns
  renderViz("health");
  renderSuggestions(h.suggestions || []);
}

/* --------------------------- table ⇄ viz switcher (data-viz chips) --------- */
const VIZ = {
  ledger: {
    canvas: "viz-ledger", tableBox: "ledger-table", note: "note-ledgerviz",
    tableNote: "Charts below follow the filters: ⎯ Bar = monthly spend by category · ◕ Pie = share of spend · ⁙ Scatter = every transaction over time.",
    build: m => specLedgerViz(state.ledgerFiltered, m),
  },
  zombies: {
    canvas: "chart-zombies", note: "note-zombiechart",
    build: m => specZombieViz(state.zombies, m),
  },
  inflation: {
    canvas: "chart-inflation", note: "note-inflation",
    build: m => specInflationViz(state.inflation, m),
  },
  health: {
    canvas: "viz-health", tableBox: "health-table", note: "note-healthviz",
    tableNote: "Bars show each component's contribution to the score (full scale is 0–100).",
    build: m => specHealthViz(state.health, m),
    renderTable: () => renderHealthTable((state.health && state.health.components) || []),
  },
  ingest: {
    canvas: "viz-ingest", tableBox: "ingest-viz-table", note: "note-ingestviz",
    tableNote: "Counts from the most recent ingest — where the dirty SMS ended up after parsing, dedup and storing.",
    build: m => specIngestViz(state.lastIngestReport, m),
    renderTable: () => renderIngestVizTable(state.lastIngestReport),
  },
};

function renderViz(key) {
  const cfg = VIZ[key]; if (!cfg) return;
  const mode = state.viz[key];
  const canvas = el(cfg.canvas);
  const tableBox = cfg.tableBox ? el(cfg.tableBox) : null;
  const chartMode = mode !== "table";
  if (canvas) canvas.classList.toggle("hidden", !chartMode);
  if (tableBox) tableBox.classList.toggle("hidden", chartMode);
  if (chartMode) {
    renderChart(cfg.canvas, () => cfg.build(mode), { note: cfg.note });
  } else {
    if (cfg.renderTable) cfg.renderTable();
    setNote(cfg.note, cfg.tableNote || "");
  }
}

function setViz(key, mode) {
  const cfg = VIZ[key]; if (!cfg || !mode || !cfg.build) return;
  state.viz[key] = mode;
  document.querySelectorAll(`.chip[data-vizfor="${key}"]`).forEach(c =>
    c.classList.toggle("active", c.dataset.viz === mode));
  renderViz(key);
}

/* ------------------------------------------------ ledger + drill-down ------ */
function applyLedgerFilters() {
  const filtered = renderLedger(state.ledgerRows, {
    search: el("ledger-search").value,
    category: el("ledger-category").value,
    direction: el("ledger-direction").value,
    month: el("ledger-month").value,
  });
  state.ledgerFiltered = filtered;      // feeds the ⇄ viz modes (bar/pie/scatter)
  renderViz("ledger");
}

/** Drill target from any chart: set ledger filters and jump there. */
function gotoLedger({ category, search, monthLabel }) {
  if (category) el("ledger-category").value = category;
  if (search) { el("ledger-search").value = search; }
  if (monthLabel) {
    const key = monthKeyFromLabel(monthLabel);
    if (key && [...el("ledger-month").options].some(o => o.value === key)) {
      el("ledger-month").value = key;
    }
  }
  switchTab("ledger");
  applyLedgerFilters();
}

function monthKeyFromLabel(label) {   /* "Oct 26" -> "2026-10" */
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const m = /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{2})$/.exec(label || "");
  if (!m) return null;
  const mm = names.indexOf(m[1]) + 1;
  return `20${m[2]}-${String(mm).padStart(2, "0")}`;
}

/* ------------------------------------------------ ingest handlers ---------- */
async function submitSms() {
  const text = el("sms-input").value.trim();
  if (!text) { el("sms-report").textContent = "Paste some SMS text first."; return; }
  el("sms-report").textContent = "Parsing…";
  try {
    const r = await API.ingestSms(text);
    state.lastIngestReport = r;
    el("sms-report").textContent = renderIngestReport(r);
    el("sms-input").value = "";
    await loadAll();
    switchTab("overview");
  } catch (e) { el("sms-report").textContent = "Error: " + e.message; }
}

async function submitSmsFile() {
  const file = el("sms-file").files[0];
  if (!file) { el("sms-report").textContent = "Choose an SMS dump file first (txt / xml / csv / tsv / json / zip / sqlite)."; return; }
  el("sms-report").textContent = "Uploading & parsing the whole dump…";
  try {
    const r = await API.ingestSmsFile(file);
    state.lastIngestReport = r;
    el("sms-report").textContent = renderIngestReport(r) + "\nfile: " + r.file + (r.file_format ? " (" + r.file_format + ")" : "");
    el("sms-file").value = "";
    await loadAll();
    switchTab("overview");
  } catch (e) { el("sms-report").textContent = "Error: " + e.message; }
}

function renderIngestReport(r) {
  return (
    `parsed: ${r.parsed}   skipped (non-transactions): ${r.failed}   messages in input: ${r.messages_in_file ?? r.parsed + r.failed}\n` +
    `duplicates removed: ${r.duplicates_removed}   already in database: ${r.already_stored ?? 0}   unknown merchants: ${r.unknown_merchants}   rows stored: ${r.rows_out}\n` +
    `total stored in DB: ${r.stored_total}` +
    (r.file_format ? `   format: ${r.file_format}` : "") +
    (r.failed_lines?.length ? `\nsample skipped SMS:\n  ${r.failed_lines.slice(0, 5).join("\n  ")}` : ""));
}

async function submitCsv() {
  const file = el("csv-file").files[0];
  if (!file) { el("csv-report").textContent = "Choose a CSV first."; return; }
  el("csv-report").textContent = "Uploading…";
  try {
    const r = await API.uploadCsv(file);
    state.lastIngestReport = r;
    el("csv-report").textContent =
      `file: ${r.file}\nrows in: ${r.rows_in}  duplicates: ${r.duplicates_removed}  out: ${r.rows_out}\nstored total: ${r.stored_total}`;
    el("csv-file").value = "";
    await loadAll();
    switchTab("overview");
  } catch (e) { el("csv-report").textContent = "Error: " + e.message; }
}

async function resetData() {
  el("reset-report").textContent = "Loading synthetic demo dataset…";
  try {
    const r = await API.reset();
    state.lastIngestReport = r;
    el("reset-report").textContent =
      `demo seed: ${r.seed}\nrows in: ${r.rows_in}  dup removed: ${r.duplicates_removed}  ` +
      `unknown merchant: ${r.unknown_merchants}  stored: ${r.rows_out}`;
    await loadAll();
    switchTab("overview");
  } catch (e) { el("reset-report").textContent = "Error: " + e.message; }
}

async function clearData() {
  el("reset-report").textContent = "Clearing stored data…";
  try {
    await API.clear();
    state.lastIngestReport = { parsed: 0, failed: 0, duplicates_removed: 0,
                               rows_out: 0, stored_total: 0 };
    el("reset-report").textContent = "All stored transactions removed. DB is empty.";
    DONUT_STATE.hidden.clear();
    state.ledgerRows = [];
    await loadAll();
    switchTab("overview");
  } catch (e) { el("reset-report").textContent = "Error: " + e.message; }
}

/* ------------------------------------------------ tabs ---------------------- */
let currentTab = "overview";
function switchTab(tab) {
  currentTab = tab;
  activate(tab);
}

/* ------------------------------------------------ global chip delegation ---- */
document.addEventListener("click", ev => {
  const chip = ev.target.closest(".chip");
  if (chip) {
    if (chip.dataset.vizfor) { setViz(chip.dataset.vizfor, chip.dataset.viz); return; }
    if (chip.dataset.table) { toggleChartTable(chip.dataset.table); return; }
    if (chip.dataset.retry && REGISTRY[chip.dataset.retry]) {
      renderChart(chip.dataset.retry, REGISTRY[chip.dataset.retry],
        { note: REGISTRY_NOTE[chip.dataset.retry] || undefined });
      return;
    }
    if (chip.dataset.drange) { state.dailyRange = chip.dataset.drange; syncDailyChips(); renderDaily(); return; }
    if (chip.dataset.dmode) { state.dailyMode = chip.dataset.dmode; syncDailyChips(); renderDaily(); return; }
  }
  /* donut legend row: toggle that slice on/off */
  const dl = ev.target.closest(".dl-row");
  if (dl && dl.dataset.dtoggle) {
    const cat = dl.dataset.dtoggle;
    DONUT_STATE.hidden.has(cat) ? DONUT_STATE.hidden.delete(cat) : DONUT_STATE.hidden.add(cat);
    const get = () => specExpenseDonut(state.overview, state.overview.month_spend);
    renderChart("chart-donut", get, { note: "note-donut" });
    renderDonutLegend(get().legendData);
  }
});

/* charts resize with their card, never overflow it */
const _ro = ("ResizeObserver" in window) &&
  new ResizeObserver(entries => {
    for (const en of entries) {
      const id = en.target.id;
      const tbl = id && document.getElementById("tbl-" + id);
      // resize drawn charts whose table fallback is NOT on screen, and the
      // viz-switcher canvases (they have no tbl- companion at all)
      if (id && (!tbl || tbl.classList.contains("hidden"))) {
        try { Plotly.Plots.resize(en.target); } catch (_) { /* not drawn yet */ }
      }
    }
  });

/* ------------------------------------------------ wire up ------------------- */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab").forEach(b =>
    b.addEventListener("click", () => switchTab(b.dataset.tab)));

  ["ledger-search", "ledger-category", "ledger-direction", "ledger-month"].forEach(id =>
    el(id).addEventListener("input", applyLedgerFilters));
  el("ledger-export").addEventListener("click", () => {
    const rows = renderLedger(state.ledgerRows, {
      search: el("ledger-search").value,
      category: el("ledger-category").value,
      direction: el("ledger-direction").value,
      month: el("ledger-month").value,
    });
    exportCsv(rows);
  });

  el("sms-submit").addEventListener("click", submitSms);
  el("sms-file-submit").addEventListener("click", submitSmsFile);
  el("csv-submit").addEventListener("click", submitCsv);
  el("reset-btn").addEventListener("click", resetData);
  el("clear-btn").addEventListener("click", clearData);

  document.querySelectorAll(".chart-body").forEach(b => { try { _ro.observe(b); } catch (_) {} });

  /* loading skeletons until each chart draws (shimmer in style.css) */
  document.querySelectorAll(".chart-body").forEach(b => b.classList.add("skeleton"));

  loadAll().catch(e => showError("boot", e));
});
