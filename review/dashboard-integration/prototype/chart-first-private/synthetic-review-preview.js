(() => {
  "use strict";

  const EVIDENCE_URL = "/chart-first-private/synthetic-review-evidence.json";
  const PAGE_SIZE = 12;
  const DAY_MS = 24 * 60 * 60 * 1000;
  const INTERVAL_MS = { "1m": 60_000, "5m": 300_000, "15m": 900_000, "1D": DAY_MS };
  const VIEW_MS = { "1D": DAY_MS, "1W": 7 * DAY_MS, "1M": 30 * DAY_MS };
  const DEFAULT_VIEW = { "1m": "1D", "5m": "1W", "15m": "1M", "1D": "full" };
  const DEFAULT_PRICE_HEIGHT = 520;
  const DEFAULT_REPORT_HEIGHT = 320;
  const root = document.getElementById("qf-chart-first");
  const priceChart = document.getElementById("price-chart");
  const performanceChart = document.getElementById("performance-chart");
  const errorBox = document.getElementById("preview-error");
  const dock = document.getElementById("results-dock");
  const dockBody = document.getElementById("dock-body");
  const state = {
    evidence: null,
    prices: [],
    trades: [],
    seriesByInterval: {},
    barIndexByInterval: {},
    selectedTrade: null,
    selectedLeg: null,
    tradePage: 0,
    mode: "metrics",
    dockCollapsed: false,
    interval: "1m",
    view: "1D",
    priceHeight: DEFAULT_PRICE_HEIGHT,
    reportMinHeight: DEFAULT_REPORT_HEIGHT,
  };

  const css = (name) => {
    const probe = document.createElement("span");
    probe.style.color = `var(${name})`;
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    document.body.appendChild(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    return color;
  };
  const money = (value) => new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(Number(value));
  const percent = (value, digits = 2) => `${(Number(value) * 100).toFixed(digits)}%`;
  const signedMoney = (value) => `${Number(value) >= 0 ? "+" : ""}${money(value)}`;
  const utc = (value) => new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "UTC", hour12: false,
  }).format(new Date(value)).replace(", 24:", ", 00:") + " UTC";

  function bucketTimestamp(timestamp, interval) {
    const size = INTERVAL_MS[interval];
    return new Date(Math.floor(new Date(timestamp).getTime() / size) * size).toISOString();
  }

  function aggregatePrices(interval) {
    if (state.seriesByInterval[interval]) return state.seriesByInterval[interval];
    const rows = [];
    let current = null;
    state.prices.forEach((source) => {
      const timestamp = bucketTimestamp(source.timestamp, interval);
      if (!current || current.timestamp !== timestamp) {
        current = { timestamp, open: source.open, high: source.high, low: source.low, close: source.close };
        rows.push(current);
      } else {
        current.high = Math.max(current.high, source.high);
        current.low = Math.min(current.low, source.low);
        current.close = source.close;
      }
    });
    state.seriesByInterval[interval] = rows;
    state.barIndexByInterval[interval] = new Map(rows.map((row, index) => [row.timestamp, index]));
    return rows;
  }

  function decodeRows(document) {
    const tradeFields = document.trade_fields;
    state.prices = document.price_series.map((row) => ({
      timestamp: row[0], open: Number(row[1]), high: Number(row[2]), low: Number(row[3]), close: Number(row[4]),
    }));
    state.trades = document.trades.map((row, index) => {
      const trade = { number: index + 1 };
      tradeFields.forEach((field, fieldIndex) => { trade[field] = row[fieldIndex]; });
      return trade;
    });
    Object.keys(INTERVAL_MS).forEach(aggregatePrices);
  }

  function chartColors() {
    return {
      background: css("--qf-chart"), text: css("--qf-text"), muted: css("--qf-muted"),
      border: css("--qf-border"), green: css("--qf-green"), red: css("--qf-red"),
      yellow: css("--qf-yellow"), primary: css("--qf-primary"),
    };
  }

  function visibleWindow(centerTimestamp) {
    const series = aggregatePrices(state.interval);
    if (state.view === "full") return { rows: series, start: 0, end: series.length };
    const duration = VIEW_MS[state.view];
    const datasetStart = new Date(series[0].timestamp).getTime();
    const datasetEnd = new Date(series[series.length - 1].timestamp).getTime() + INTERVAL_MS[state.interval];
    let startMs = new Date(centerTimestamp).getTime() - duration / 2;
    let endMs = startMs + duration;
    if (startMs < datasetStart) { startMs = datasetStart; endMs = Math.min(datasetEnd, datasetStart + duration); }
    if (endMs > datasetEnd) { endMs = datasetEnd; startMs = Math.max(datasetStart, datasetEnd - duration); }
    const startBucket = Math.floor(startMs / INTERVAL_MS[state.interval]) * INTERVAL_MS[state.interval];
    const endBucket = Math.ceil(endMs / INTERVAL_MS[state.interval]) * INTERVAL_MS[state.interval];
    const rows = series.filter((row) => {
      const time = new Date(row.timestamp).getTime();
      return time >= startBucket && time < endBucket;
    });
    const first = state.barIndexByInterval[state.interval].get(rows[0].timestamp);
    return { rows, start: first, end: first + rows.length };
  }

  function visibleMarkers(windowRows, leg) {
    const timestampField = leg === "entry" ? "Entry Index" : "Exit Index";
    const priceField = leg === "entry" ? "Avg Entry Price" : "Avg Exit Price";
    const visible = new Set(windowRows.map((row) => row.timestamp));
    const points = [];
    state.trades.forEach((trade, index) => {
      const exactTimestamp = trade[timestampField];
      const barTimestamp = bucketTimestamp(exactTimestamp, state.interval);
      if (visible.has(barTimestamp)) {
        points.push({
          timestamp: barTimestamp, exactTimestamp, price: Number(trade[priceField]), index, trade,
          selected: index === state.selectedTrade && leg === state.selectedLeg,
        });
      }
    });
    return points;
  }

  function priceTrace(rows, colors) {
    return {
      type: "candlestick", name: `Invented SYNTHETIC · ${state.interval}`,
      x: rows.map((row) => row.timestamp), open: rows.map((row) => row.open), high: rows.map((row) => row.high),
      low: rows.map((row) => row.low), close: rows.map((row) => row.close),
      increasing: { line: { color: colors.green, width: 1 }, fillcolor: colors.green },
      decreasing: { line: { color: colors.red, width: 1 }, fillcolor: colors.red },
      hoverlabel: { namelength: 0 },
      hovertemplate: `${state.interval} UTC bar %{x}<br>Open %{open:$,.2f}<br>High %{high:$,.2f}<br>Low %{low:$,.2f}<br>Close %{close:$,.2f}<extra></extra>`,
    };
  }

  function markerTrace(points, leg, colors) {
    const entry = leg === "entry";
    return {
      type: "scatter", mode: "markers", name: entry ? "Entries" : "Exits",
      x: points.map((point) => point.timestamp), y: points.map((point) => point.price),
      customdata: points.map((point) => [point.index, point.index + 1, leg, point.trade.Direction, point.trade.PnL, point.exactTimestamp, point.timestamp]),
      marker: {
        symbol: entry ? "triangle-up" : "triangle-down",
        size: points.map((point) => point.selected ? 17 : 10),
        color: points.map((point) => point.selected ? colors.yellow : (entry ? colors.green : colors.red)),
        line: { color: points.map((point) => point.selected ? colors.text : colors.background), width: points.map((point) => point.selected ? 2.5 : 1) },
      },
      hovertemplate: `${entry ? "Entry" : "Exit"} · Trade %{customdata[1]}<br>Exact event %{customdata[5]}<br>Containing ${state.interval} bar %{customdata[6]}<br>Price %{y:$,.2f}<br>Direction %{customdata[3]}<extra></extra>`,
    };
  }

  function updateChartControls() {
    document.querySelectorAll(".qf-interval-button").forEach((button) => {
      const active = button.dataset.interval === state.interval;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll(".qf-view-button").forEach((button) => {
      const active = button.dataset.view === state.view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  async function renderPriceChart() {
    const trade = state.trades[state.selectedTrade];
    const timestampField = state.selectedLeg === "entry" ? "Entry Index" : "Exit Index";
    const exactTimestamp = trade[timestampField];
    const windowData = visibleWindow(exactTimestamp);
    const colors = chartColors();
    const entries = visibleMarkers(windowData.rows, "entry");
    const exits = visibleMarkers(windowData.rows, "exit");
    const traces = [priceTrace(windowData.rows, colors), markerTrace(entries, "entry", colors), markerTrace(exits, "exit", colors)];
    const start = windowData.rows[0].timestamp;
    const end = new Date(new Date(windowData.rows[windowData.rows.length - 1].timestamp).getTime() + INTERVAL_MS[state.interval]).toISOString();
    await Plotly.react(priceChart, traces, {
      autosize: true, paper_bgcolor: colors.background, plot_bgcolor: colors.background,
      font: { color: colors.text, family: "Inter, system-ui, sans-serif", size: 11 },
      margin: { l: 10, r: 78, t: 5, b: 36 }, showlegend: false, hovermode: "closest", dragmode: "pan",
      xaxis: {
        type: "date", range: [start, end], rangeslider: { visible: false }, showgrid: true,
        gridcolor: colors.border, zeroline: false, tickfont: { color: colors.muted }, fixedrange: false,
      },
      yaxis: {
        title: { text: "USD", font: { size: 11, color: colors.muted } }, side: "right", tickprefix: "$", tickformat: ",.2f",
        showgrid: true, gridcolor: colors.border, zeroline: false, tickfont: { color: colors.muted }, fixedrange: false,
      },
    }, {
      responsive: true, displaylogo: false, scrollZoom: true,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
    });
    if (typeof priceChart.removeAllListeners === "function") priceChart.removeAllListeners("plotly_click");
    priceChart.on("plotly_click", (event) => {
      const point = event.points && event.points[0];
      if (!point || !Array.isArray(point.customdata)) return;
      const [index, , leg] = point.customdata;
      selectTrade(Number(index), String(leg), { switchToTrades: true, scroll: true });
    });
    const legLabel = state.selectedLeg === "entry" ? "entry" : "exit";
    const viewLabel = state.view === "full" ? "Full run" : state.view;
    root.dataset.interval = state.interval;
    root.dataset.view = state.view;
    root.dataset.aggregatedCount = String(aggregatePrices(state.interval).length);
    root.dataset.visibleBarCount = String(windowData.rows.length);
    root.dataset.visibleMarkerCount = String(entries.length + exits.length);
    document.getElementById("chart-counts").textContent = `${aggregatePrices(state.interval).length.toLocaleString()} invented ${state.interval} bars · ${entries.length + exits.length} visible trade markers`;
    document.getElementById("chart-context").textContent = `Trade ${trade.number} ${legLabel} · exact ${utc(exactTimestamp)} · mapped to ${state.interval} bar ${utc(bucketTimestamp(exactTimestamp, state.interval))}`;
    document.getElementById("chart-live").textContent = `Focused on Trade ${trade.number} ${legLabel} at ${utc(exactTimestamp)}. ${viewLabel} view shows ${windowData.rows.length.toLocaleString()} ${state.interval} bars and ${entries.length + exits.length} trade markers.`;
    updateChartControls();
  }

  async function renderPerformanceChart() {
    const colors = chartColors();
    let cumulative = 0;
    const values = state.trades.map((trade) => { cumulative += Number(trade.PnL); return cumulative; });
    await Plotly.react(performanceChart, [{
      type: "scatter", mode: "lines", name: "Cumulative P&L", x: state.trades.map((trade) => trade.number), y: values,
      line: { color: colors.primary, width: 2 }, fill: "tozeroy",
      fillcolor: colors.primary.replace("rgb", "rgba").replace(")", ", 0.09)"),
      customdata: state.trades.map((trade) => [trade.number, trade["Exit Index"], trade.PnL]),
      hovertemplate: "Trade %{customdata[0]}<br>Exit %{customdata[1]}<br>Trade P&L %{customdata[2]:$,.2f}<br>Cumulative %{y:$,.2f}<extra></extra>",
    }], {
      autosize: true, paper_bgcolor: colors.background, plot_bgcolor: colors.background,
      font: { color: colors.text, family: "Inter, system-ui, sans-serif", size: 10 }, margin: { l: 48, r: 12, t: 6, b: 30 },
      showlegend: false, hovermode: "closest",
      xaxis: { title: { text: "Closed trade", font: { size: 10, color: colors.muted } }, showgrid: false, zeroline: false, tickfont: { color: colors.muted } },
      yaxis: { tickprefix: "$", tickformat: ",.2f", showgrid: true, gridcolor: colors.border, zerolinecolor: colors.border, tickfont: { color: colors.muted } },
    }, { responsive: true, displaylogo: false, displayModeBar: false });
  }

  function renderMetrics() {
    const metrics = state.evidence.metrics;
    const winners = state.trades.filter((trade) => Number(trade.PnL) > 0).length;
    document.getElementById("metric-return").textContent = percent(metrics.total_return, 3);
    document.getElementById("metric-drawdown").textContent = percent(metrics.max_drawdown, 3);
    document.getElementById("metric-profitable").textContent = percent(metrics.win_rate, 2);
    document.getElementById("metric-profitable-count").textContent = `${winners} of ${state.trades.length} closed trades`;
    document.getElementById("metric-trades").textContent = Number(metrics.number_of_trades).toLocaleString();
  }

  function tradeMarkup(trade, index) {
    const selected = index === state.selectedTrade;
    const pnlClass = Number(trade.PnL) >= 0 ? "is-profit" : "is-loss";
    const returnText = `${Number(trade.Return) >= 0 ? "+" : ""}${percent(trade.Return, 2)}`;
    const leg = (name, timestampField, priceField) => {
      const lower = name.toLowerCase();
      const pressed = selected && state.selectedLeg === lower;
      return `<div class="qf-trade-leg"><span>${name}</span><span>${utc(trade[timestampField])}</span><span class="qf-leg-price">${money(trade[priceField])}</span><button class="qf-button qf-show-button" type="button" data-trade-index="${index}" data-leg="${lower}" aria-pressed="${pressed}">Show ${lower}</button></div>`;
    };
    return `<article id="trade-${trade.number}" class="qf-trade-group${selected ? " is-selected" : ""}" data-trade-index="${index}"${selected ? " aria-current=\"true\"" : ""}><div class="qf-trade-summary"><strong>Trade ${trade.number} · ${trade.Direction}</strong><span class="${pnlClass}">${signedMoney(trade.PnL)} · ${returnText}</span></div>${leg("Entry", "Entry Index", "Avg Entry Price")}${leg("Exit", "Exit Index", "Avg Exit Price")}</article>`;
  }

  function renderTrades() {
    const pages = Math.ceil(state.trades.length / PAGE_SIZE);
    state.tradePage = Math.max(0, Math.min(state.tradePage, pages - 1));
    const start = state.tradePage * PAGE_SIZE;
    const end = Math.min(state.trades.length, start + PAGE_SIZE);
    document.getElementById("trade-page-label").textContent = `Trades ${start + 1}–${end} of ${state.trades.length}`;
    document.getElementById("previous-trades").disabled = state.tradePage === 0;
    document.getElementById("next-trades").disabled = state.tradePage === pages - 1;
    const container = document.getElementById("trade-groups");
    container.innerHTML = state.trades.slice(start, end).map((trade, offset) => tradeMarkup(trade, start + offset)).join("");
    container.querySelectorAll(".qf-show-button").forEach((button) => button.addEventListener("click", () => {
      selectTrade(Number(button.dataset.tradeIndex), button.dataset.leg, { switchToTrades: false, scroll: false });
    }));
  }

  function switchMode(mode) {
    state.mode = mode;
    const metrics = mode === "metrics";
    document.getElementById("metrics-tab").classList.toggle("is-active", metrics);
    document.getElementById("metrics-tab").setAttribute("aria-selected", String(metrics));
    document.getElementById("trades-tab").classList.toggle("is-active", !metrics);
    document.getElementById("trades-tab").setAttribute("aria-selected", String(!metrics));
    document.getElementById("metrics-panel").hidden = !metrics;
    document.getElementById("trades-panel").hidden = metrics;
    if (metrics) requestAnimationFrame(() => Plotly.Plots.resize(performanceChart)); else renderTrades();
  }

  async function selectTrade(index, leg, options = {}) {
    state.selectedTrade = index;
    state.selectedLeg = leg;
    state.tradePage = Math.floor(index / PAGE_SIZE);
    if (options.switchToTrades) switchMode("trades"); else if (state.mode === "trades") renderTrades();
    document.getElementById("dock-selection").textContent = `Trade ${index + 1} ${leg} selected`;
    await renderPriceChart();
    if (options.scroll) requestAnimationFrame(() => document.getElementById(`trade-${index + 1}`)?.scrollIntoView({ block: "nearest" }));
  }

  function setDockCollapsed(collapsed) {
    state.dockCollapsed = collapsed;
    dock.classList.toggle("is-collapsed", collapsed);
    dockBody.hidden = collapsed;
    const button = document.getElementById("collapse-dock");
    button.textContent = collapsed ? "Expand" : "Collapse";
    button.setAttribute("aria-expanded", String(!collapsed));
    requestAnimationFrame(() => Plotly.Plots.resize(priceChart));
  }

  function setPanelHeight(kind, next) {
    if (kind === "price") {
      state.priceHeight = Math.max(300, Math.min(900, next));
      document.documentElement.style.setProperty("--qf-price-height", `${state.priceHeight}px`);
      document.querySelectorAll("#chart-resizer-top, #dock-resizer").forEach((handle) => handle.setAttribute("aria-valuenow", String(Math.round(state.priceHeight))));
      Plotly.Plots.resize(priceChart);
    } else {
      state.reportMinHeight = Math.max(240, Math.min(760, next));
      document.documentElement.style.setProperty("--qf-report-min-height", `${state.reportMinHeight}px`);
      document.getElementById("dock-resizer-bottom").setAttribute("aria-valuenow", String(Math.round(state.reportMinHeight)));
      if (state.mode === "metrics") Plotly.Plots.resize(performanceChart);
    }
  }

  function bindResizer(element, kind, edge) {
    let drag = null;
    element.addEventListener("pointerdown", (event) => {
      if (window.innerWidth <= 900 || (kind === "report" && state.dockCollapsed)) return;
      drag = { y: event.clientY, height: kind === "price" ? priceChart.getBoundingClientRect().height : state.reportMinHeight };
      element.setPointerCapture(event.pointerId);
    });
    element.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const delta = edge === "top" ? drag.y - event.clientY : event.clientY - drag.y;
      setPanelHeight(kind, drag.height + delta);
    });
    const stop = () => { drag = null; };
    element.addEventListener("pointerup", stop);
    element.addEventListener("pointercancel", stop);
    element.addEventListener("keydown", (event) => {
      if (!["ArrowUp", "ArrowDown"].includes(event.key) || window.innerWidth <= 900) return;
      event.preventDefault();
      const direction = event.key === "ArrowUp" ? -1 : 1;
      const delta = edge === "top" ? -direction * 20 : direction * 20;
      setPanelHeight(kind, (kind === "price" ? state.priceHeight : state.reportMinHeight) + delta);
    });
  }

  function bindSharedResizer(element) {
    let drag = null;
    element.addEventListener("pointerdown", (event) => {
      if (window.innerWidth <= 900 || state.dockCollapsed) return;
      drag = { y: event.clientY, priceHeight: state.priceHeight, reportHeight: state.reportMinHeight };
      element.setPointerCapture(event.pointerId);
    });
    element.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const delta = event.clientY - drag.y;
      setPanelHeight("price", drag.priceHeight + delta);
      setPanelHeight("report", drag.reportHeight - delta);
    });
    const stop = () => { drag = null; };
    element.addEventListener("pointerup", stop);
    element.addEventListener("pointercancel", stop);
    element.addEventListener("keydown", (event) => {
      if (!["ArrowUp", "ArrowDown"].includes(event.key) || window.innerWidth <= 900 || state.dockCollapsed) return;
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 20 : -20;
      setPanelHeight("price", state.priceHeight + delta);
      setPanelHeight("report", state.reportMinHeight - delta);
    });
  }

  function resetWorkspace() {
    state.interval = "1m";
    state.view = "1D";
    state.tradePage = 0;
    document.documentElement.style.removeProperty("--qf-price-height");
    document.documentElement.style.removeProperty("--qf-report-min-height");
    state.priceHeight = DEFAULT_PRICE_HEIGHT;
    state.reportMinHeight = DEFAULT_REPORT_HEIGHT;
    setDockCollapsed(false);
    switchMode("metrics");
    document.querySelectorAll("#chart-resizer-top, #dock-resizer").forEach((handle) => handle.setAttribute("aria-valuenow", String(DEFAULT_PRICE_HEIGHT)));
    document.getElementById("dock-resizer-bottom").setAttribute("aria-valuenow", String(DEFAULT_REPORT_HEIGHT));
    selectTrade(state.trades.length - 1, "exit", { switchToTrades: false, scroll: false });
  }

  function bindControls() {
    document.getElementById("metrics-tab").addEventListener("click", () => switchMode("metrics"));
    document.getElementById("trades-tab").addEventListener("click", () => switchMode("trades"));
    document.getElementById("previous-trades").addEventListener("click", () => { state.tradePage -= 1; renderTrades(); });
    document.getElementById("next-trades").addEventListener("click", () => { state.tradePage += 1; renderTrades(); });
    document.getElementById("collapse-dock").addEventListener("click", () => setDockCollapsed(!state.dockCollapsed));
    document.getElementById("refresh-preview").addEventListener("click", resetWorkspace);
    document.getElementById("reset-chart-range").addEventListener("click", renderPriceChart);
    document.querySelectorAll(".qf-interval-button").forEach((button) => button.addEventListener("click", async () => {
      state.interval = button.dataset.interval;
      state.view = DEFAULT_VIEW[state.interval];
      await renderPriceChart();
    }));
    document.querySelectorAll(".qf-view-button").forEach((button) => button.addEventListener("click", async () => {
      state.view = button.dataset.view;
      await renderPriceChart();
    }));
    const changeRun = document.getElementById("change-run");
    const runMenu = document.getElementById("run-menu");
    changeRun.addEventListener("click", () => {
      const opening = runMenu.hidden;
      runMenu.hidden = !opening;
      changeRun.setAttribute("aria-expanded", String(opening));
    });
    document.addEventListener("click", (event) => {
      if (!runMenu.hidden && !event.target.closest(".qf-run-actions")) {
        runMenu.hidden = true;
        changeRun.setAttribute("aria-expanded", "false");
      }
    });
    bindResizer(document.getElementById("chart-resizer-top"), "price", "top");
    bindSharedResizer(document.getElementById("dock-resizer"));
    bindResizer(document.getElementById("dock-resizer-bottom"), "report", "bottom");
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", () => { renderPriceChart(); renderPerformanceChart(); });
  }

  async function load() {
    try {
      if (typeof Plotly === "undefined") throw new Error("The chart library did not load.");
      const response = await fetch(EVIDENCE_URL, { cache: "no-store", credentials: "same-origin" });
      if (!response.ok) throw new Error(`Evidence request failed (${response.status}).`);
      const evidence = await response.json();
      if (evidence.schema_version !== 1 || evidence.instrument !== "SYNTHETIC") throw new Error("Synthetic review schema is not recognized.");
      state.evidence = evidence;
      decodeRows(evidence);
      if (state.prices.length !== 53528 || state.trades.length !== 366) throw new Error("Synthetic row counts do not match the validated preview contract.");
      root.dataset.priceCount = String(state.prices.length);
      root.dataset.tradeCount = String(state.trades.length);
      state.selectedTrade = state.trades.length - 1;
      state.selectedLeg = "exit";
      renderMetrics();
      renderTrades();
      bindControls();
      await Promise.all([renderPriceChart(), renderPerformanceChart()]);
      root.setAttribute("aria-busy", "false");
      window.__qfPreviewState = state;
      window.__qfBucketTimestamp = bucketTimestamp;
    } catch (error) {
      errorBox.textContent = `The private preview could not load validated evidence: ${error.message}`;
      errorBox.hidden = false;
      root.setAttribute("aria-busy", "false");
      console.error(error);
    }
  }

  window.addEventListener("resize", () => {
    if (state.evidence) {
      Plotly.Plots.resize(priceChart);
      if (state.mode === "metrics") Plotly.Plots.resize(performanceChart);
    }
  });
  load();
})();
