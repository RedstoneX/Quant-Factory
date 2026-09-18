(function () {
  "use strict";

  const DESKTOP_MIN = 901;
  const CHART_DEFAULT = 520;
  const REPORT_DEFAULT = 320;
  const CHART_MIN = 300;
  const CHART_MAX = 900;
  const REPORT_MIN = 240;
  const REPORT_MAX = 760;

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function workspaceFor(element) {
    return element && element.closest(".results-beta-workspace");
  }

  function dimensions(workspace) {
    const chart = workspace.querySelector(".results-chart-region");
    const report = workspace.querySelector(".results-report-region");
    return {
      chart: chart ? chart.getBoundingClientRect().height : CHART_DEFAULT,
      report: report ? report.getBoundingClientRect().height : REPORT_DEFAULT,
    };
  }

  function resizePlots(workspace) {
    if (!window.Plotly) return;
    workspace.querySelectorAll(".js-plotly-plot").forEach(function (plot) {
      window.Plotly.Plots.resize(plot);
    });
  }

  function applyDimensions(workspace, chartHeight, reportHeight) {
    if (chartHeight !== null) {
      workspace.style.setProperty(
        "--qf-results-chart-height",
        clamp(chartHeight, CHART_MIN, CHART_MAX) + "px"
      );
    }
    if (reportHeight !== null) {
      workspace.style.setProperty(
        "--qf-results-report-min-height",
        clamp(reportHeight, REPORT_MIN, REPORT_MAX) + "px"
      );
    }
    resizePlots(workspace);
  }

  function bind(handle) {
    if (handle.dataset.resultsResizeBound === "true") return;
    handle.dataset.resultsResizeBound = "true";
    const edge = handle.dataset.resultsResizer;
    const chartEdge = edge === "chart-top" || edge === "shared";
    handle.setAttribute("aria-valuemin", String(chartEdge ? CHART_MIN : REPORT_MIN));
    handle.setAttribute("aria-valuemax", String(chartEdge ? CHART_MAX : REPORT_MAX));

    let drag = null;
    handle.addEventListener("pointerdown", function (event) {
      if (window.innerWidth < DESKTOP_MIN) return;
      const workspace = workspaceFor(handle);
      if (!workspace) return;
      drag = { y: event.clientY, sizes: dimensions(workspace) };
      handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener("pointermove", function (event) {
      if (!drag) return;
      const workspace = workspaceFor(handle);
      const delta = event.clientY - drag.y;
      if (edge === "chart-top") {
        applyDimensions(workspace, drag.sizes.chart - delta, null);
      } else if (edge === "shared") {
        applyDimensions(workspace, drag.sizes.chart + delta, drag.sizes.report - delta);
      } else {
        applyDimensions(workspace, null, drag.sizes.report + delta);
      }
    });
    ["pointerup", "pointercancel"].forEach(function (name) {
      handle.addEventListener(name, function () { drag = null; });
    });
    handle.addEventListener("keydown", function (event) {
      if (window.innerWidth < DESKTOP_MIN || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const workspace = workspaceFor(handle);
      const sizes = dimensions(workspace);
      const delta = event.key === "ArrowDown" ? 20 : -20;
      if (edge === "chart-top") {
        applyDimensions(workspace, sizes.chart - delta, null);
      } else if (edge === "shared") {
        applyDimensions(workspace, sizes.chart + delta, sizes.report - delta);
      } else {
        applyDimensions(workspace, null, sizes.report + delta);
      }
    });
  }

  function bindAll() {
    document.querySelectorAll("[data-results-resizer]").forEach(bind);
  }

  document.addEventListener("click", function (event) {
    const reset = event.target.closest("#results-reset-layout");
    if (!reset) return;
    const workspace = workspaceFor(reset);
    if (!workspace) return;
    workspace.style.removeProperty("--qf-results-chart-height");
    workspace.style.removeProperty("--qf-results-report-min-height");
    resizePlots(workspace);
  });

  window.dash_clientside = window.dash_clientside || {};
  window.dash_clientside.qfResults = window.dash_clientside.qfResults || {};
  window.dash_clientside.qfResults.focusTrade = function (selectedRows, runId) {
    const graph = document.querySelector("#price-marker-chart .js-plotly-plot");
    const row = selectedRows && selectedRows.length ? selectedRows[0] : null;
    const selectedIndex = row && row.__run_id === runId
      ? Number(row.__trade_index)
      : null;
    if (!graph || !window.Plotly || !Array.isArray(graph.data)) {
      return row
        ? "The selected trade could not be shown because the price chart is unavailable."
        : "Select a trade to identify its entry and exit on the price chart.";
    }

    const selectedBarTimes = [];
    graph.data.forEach(function (trace, traceIndex) {
      if (trace.type !== "scatter" || trace.mode !== "markers" || !Array.isArray(trace.customdata)) return;
      const entry = String(trace.name || "").toLowerCase().includes("entry");
      const selected = trace.customdata.map(function (item) {
        return selectedIndex !== null && Number(item && item[0]) === selectedIndex;
      });
      const sizes = selected.map(function (active) { return active ? 17 : 9; });
      const colors = selected.map(function (active) {
        return active ? "#facc15" : (entry ? "#16a34a" : "#dc2626");
      });
      const lineColors = selected.map(function (active) {
        return active ? "#172033" : (entry ? "#064e3b" : "#7f1d1d");
      });
      const lineWidths = selected.map(function (active) { return active ? 2.5 : 1; });
      window.Plotly.restyle(
        graph,
        {
          "marker.size": [sizes],
          "marker.color": [colors],
          "marker.line.color": [lineColors],
          "marker.line.width": [lineWidths],
        },
        [traceIndex]
      );
      if (trace.visible !== false) {
        selected.forEach(function (active, pointIndex) {
          if (active) selectedBarTimes.push(new Date(trace.x[pointIndex]).getTime());
        });
      }
    });

    if (selectedIndex === null) {
      return "Select a trade to identify its entry and exit on the price chart.";
    }

    const finiteTimes = selectedBarTimes.filter(Number.isFinite);
    const axis = graph._fullLayout && graph._fullLayout.xaxis;
    if (finiteTimes.length && axis && Array.isArray(axis.range)) {
      const currentStart = new Date(axis.range[0]).getTime();
      const currentEnd = new Date(axis.range[1]).getTime();
      const selectedStart = Math.min.apply(null, finiteTimes);
      const selectedEnd = Math.max.apply(null, finiteTimes);
      if (
        Number.isFinite(currentStart) && Number.isFinite(currentEnd) &&
        (selectedStart < currentStart || selectedEnd > currentEnd)
      ) {
        const currentDuration = currentEnd - currentStart;
        const selectedDuration = Math.max(selectedEnd - selectedStart, 60 * 1000);
        const duration = Math.max(currentDuration, Math.ceil(selectedDuration * 1.25));
        const center = selectedStart + ((selectedEnd - selectedStart) / 2);
        window.Plotly.relayout(graph, {
          "xaxis.range": [new Date(center - duration / 2), new Date(center + duration / 2)],
        });
      }
    }

    const entryTime = row["Entry timestamp"] || "entry time not recorded";
    const exitTime = row["Exit/valuation timestamp"] || "exit not recorded";
    return row.Trade + " identified on chart. Entry " + entryTime +
      "; exit/valuation " + exitTime + ". Bars and View are unchanged.";
  };

  new MutationObserver(bindAll).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", bindAll);
  bindAll();
})();
