(function () {
  "use strict";

  window.dash_clientside = window.dash_clientside || {};
  window.dash_clientside.qfResults = window.dash_clientside.qfResults || {};
  window.dash_clientside.qfResults.focusTrade = function (selectedRows, runId) {
    const graph = document.querySelector("#price-marker-chart .js-plotly-plot");
    const row = selectedRows && selectedRows.length ? selectedRows[0] : null;
    const selectedIndex = row && row.__run_id === runId
      ? Number(row.__trade_index)
      : null;
    if (!row) return "Select a trade to identify its entry and exit on the price chart.";

    const traces = graph && window.Plotly && Array.isArray(graph.data) ? graph.data : [];
    traces.forEach(function (trace, traceIndex) {
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
    });

    if (selectedIndex === null) {
      return "Select a trade to identify its entry and exit on the price chart.";
    }

    const entryTime = row["Entry timestamp"] || "entry time not recorded";
    const exitTime = row["Exit/valuation timestamp"] || "exit not recorded";
    return row.Trade + " selected. Entry " + entryTime +
      "; exit/valuation " + exitTime + ". The chart window updates without changing Bars or View.";
  };
})();
