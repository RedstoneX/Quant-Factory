/*
 * Quant Factory Results workspace layout behavior.
 *
 * Integration contract:
 * - root: .results-workspace[data-results-run-id]
 * - handles: [data-results-resize="chart-top|chart-report|report-bottom"]
 * - reset: [data-results-reset-layout]
 * - optional numeric root attributes (CSS px):
 *   data-results-chart-default/min/max and data-results-report-default/min/max
 *
 * This module writes only --qf-results-chart-height,
 * --qf-results-report-min-height, resize ARIA attributes, and browser-session
 * layout dimensions keyed by run ID. It never mutates Bars, View, report tab,
 * selected trade/leg, evidence, review, route, or persisted run state.
 */
(function () {
  "use strict";

  const ROOT_SELECTOR = ".results-workspace[data-results-run-id]";
  const HANDLE_SELECTOR = "[data-results-resize]";
  const RESET_SELECTOR = "[data-results-reset-layout]";
  const DESKTOP_QUERY = "(min-width: 1100px)";
  const STORAGE_PREFIX = "qf.results.workspace.layout.v1:";
  const KEYBOARD_STEP = 20;
  const DEFAULTS = Object.freeze({
    chart: 540,
    chartMin: 320,
    chartMax: 860,
    report: 320,
    reportMin: 220,
    reportMax: 760
  });
  const LABELS = Object.freeze({
    "chart-top": "Resize chart from its top edge",
    "chart-report": "Resize chart and report panels",
    "report-bottom": "Resize report from its bottom edge"
  });

  let drag = null;
  let hydrationQueued = false;
  const desktop = window.matchMedia(DESKTOP_QUERY);
  const initializedRuns = new WeakMap();

  function integer(value, fallback) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function limits(root) {
    const chartMin = integer(root.dataset.resultsChartMin, DEFAULTS.chartMin);
    const chartMax = Math.max(
      chartMin,
      integer(root.dataset.resultsChartMax, DEFAULTS.chartMax)
    );
    const reportMin = integer(root.dataset.resultsReportMin, DEFAULTS.reportMin);
    const reportMax = Math.max(
      reportMin,
      integer(root.dataset.resultsReportMax, DEFAULTS.reportMax)
    );
    return {
      chartMin,
      chartMax,
      reportMin,
      reportMax,
      chartDefault: clamp(
        integer(root.dataset.resultsChartDefault, DEFAULTS.chart),
        chartMin,
        chartMax
      ),
      reportDefault: clamp(
        integer(root.dataset.resultsReportDefault, DEFAULTS.report),
        reportMin,
        reportMax
      )
    };
  }

  function storageKey(root) {
    const runId = (root.dataset.resultsRunId || "").trim();
    return runId ? STORAGE_PREFIX + encodeURIComponent(runId) : null;
  }

  function readStored(root, bounds) {
    const key = storageKey(root);
    if (!key) return null;
    try {
      const parsed = JSON.parse(window.sessionStorage.getItem(key));
      if (!parsed || typeof parsed !== "object") return null;
      return {
        chart: clamp(integer(parsed.chart, bounds.chartDefault), bounds.chartMin, bounds.chartMax),
        report: clamp(integer(parsed.report, bounds.reportDefault), bounds.reportMin, bounds.reportMax)
      };
    } catch (_error) {
      return null;
    }
  }

  function currentDimensions(root, bounds) {
    return {
      chart: integer(root.dataset.resultsChartCurrent, bounds.chartDefault),
      report: integer(root.dataset.resultsReportCurrent, bounds.reportDefault)
    };
  }

  function applyDimensions(root, dimensions, bounds, persist) {
    const next = {
      chart: clamp(dimensions.chart, bounds.chartMin, bounds.chartMax),
      report: clamp(dimensions.report, bounds.reportMin, bounds.reportMax)
    };
    root.style.setProperty("--qf-results-chart-height", next.chart + "px");
    root.style.setProperty("--qf-results-report-min-height", next.report + "px");
    root.dataset.resultsChartCurrent = String(next.chart);
    root.dataset.resultsReportCurrent = String(next.report);
    updateHandleSemantics(root, next, bounds);

    if (persist) {
      const key = storageKey(root);
      if (key) {
        try {
          window.sessionStorage.setItem(key, JSON.stringify(next));
        } catch (_error) {
          // Restricted session storage must not break the dashboard.
        }
      }
    }
  }

  function updateHandleSemantics(root, dimensions, bounds) {
    root.querySelectorAll(HANDLE_SELECTOR).forEach(function (handle) {
      const kind = handle.dataset.resultsResize;
      const reportHandle = kind === "report-bottom";
      handle.setAttribute("role", "separator");
      handle.setAttribute("aria-orientation", "horizontal");
      handle.setAttribute("aria-label", LABELS[kind] || "Resize Results panel");
      handle.setAttribute("aria-disabled", desktop.matches ? "false" : "true");
      handle.tabIndex = desktop.matches ? 0 : -1;
      handle.setAttribute("aria-valuemin", String(reportHandle ? bounds.reportMin : bounds.chartMin));
      handle.setAttribute("aria-valuemax", String(reportHandle ? bounds.reportMax : bounds.chartMax));
      handle.setAttribute("aria-valuenow", String(reportHandle ? dimensions.report : dimensions.chart));
    });
  }

  function initializeRoot(root) {
    const bounds = limits(root);
    const runId = (root.dataset.resultsRunId || "").trim();
    if (initializedRuns.get(root) === runId) {
      updateHandleSemantics(root, currentDimensions(root, bounds), bounds);
      return;
    }
    const dimensions = readStored(root, bounds) || {
      chart: bounds.chartDefault,
      report: bounds.reportDefault
    };
    applyDimensions(root, dimensions, bounds, false);
    initializedRuns.set(root, runId);
  }

  function hydrate() {
    document.querySelectorAll(ROOT_SELECTOR).forEach(initializeRoot);
  }

  function queueHydration() {
    if (hydrationQueued) return;
    hydrationQueued = true;
    window.requestAnimationFrame(function () {
      hydrationQueued = false;
      hydrate();
    });
  }

  function dimensionsForDelta(kind, start, deltaY, bounds) {
    if (kind === "chart-top") {
      return { chart: start.chart - deltaY, report: start.report };
    }
    if (kind === "chart-report") {
      const minimumDelta = Math.max(
        bounds.chartMin - start.chart,
        start.report - bounds.reportMax
      );
      const maximumDelta = Math.min(
        bounds.chartMax - start.chart,
        start.report - bounds.reportMin
      );
      const appliedDelta = clamp(deltaY, minimumDelta, maximumDelta);
      return {
        chart: start.chart + appliedDelta,
        report: start.report - appliedDelta
      };
    }
    return { chart: start.chart, report: start.report + deltaY };
  }

  function beginPointerResize(event) {
    const handle = event.target.closest(HANDLE_SELECTOR);
    if (!handle || !desktop.matches || event.button !== 0) return;
    const root = handle.closest(ROOT_SELECTOR);
    if (!root) return;
    const bounds = limits(root);
    drag = {
      pointerId: event.pointerId,
      startY: event.clientY,
      kind: handle.dataset.resultsResize,
      handle,
      root,
      bounds,
      start: currentDimensions(root, bounds)
    };
    handle.dataset.resultsResizing = "true";
    handle.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function movePointerResize(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const next = dimensionsForDelta(
      drag.kind,
      drag.start,
      event.clientY - drag.startY,
      drag.bounds
    );
    applyDimensions(drag.root, next, drag.bounds, false);
    event.preventDefault();
  }

  function endPointerResize(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    applyDimensions(
      drag.root,
      currentDimensions(drag.root, drag.bounds),
      drag.bounds,
      true
    );
    delete drag.handle.dataset.resultsResizing;
    drag = null;
  }

  function keyboardDimensions(kind, key, start, bounds) {
    if (key === "Home") {
      return kind === "report-bottom"
        ? { chart: start.chart, report: bounds.reportMin }
        : { chart: bounds.chartMin, report: kind === "chart-report" ? bounds.reportMax : start.report };
    }
    if (key === "End") {
      return kind === "report-bottom"
        ? { chart: start.chart, report: bounds.reportMax }
        : { chart: bounds.chartMax, report: kind === "chart-report" ? bounds.reportMin : start.report };
    }
    const direction = key === "ArrowDown" ? 1 : -1;
    const delta = direction * KEYBOARD_STEP;
    return dimensionsForDelta(kind, start, delta, bounds);
  }

  function handleKeyboardResize(event) {
    const handle = event.target.closest(HANDLE_SELECTOR);
    if (!handle || !desktop.matches) return;
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    const root = handle.closest(ROOT_SELECTOR);
    if (!root) return;
    const bounds = limits(root);
    const start = currentDimensions(root, bounds);
    const next = keyboardDimensions(handle.dataset.resultsResize, event.key, start, bounds);
    applyDimensions(root, next, bounds, true);
    event.preventDefault();
  }

  function resetLayout(event) {
    const control = event.target.closest(RESET_SELECTOR);
    if (!control) return;
    const root = control.closest(ROOT_SELECTOR);
    if (!root) return;
    const bounds = limits(root);
    const key = storageKey(root);
    if (key) {
      try {
        window.sessionStorage.removeItem(key);
      } catch (_error) {
        // Restricted session storage must not break the reset action.
      }
    }
    applyDimensions(
      root,
      { chart: bounds.chartDefault, report: bounds.reportDefault },
      bounds,
      false
    );
  }

  document.addEventListener("pointerdown", beginPointerResize);
  document.addEventListener("pointermove", movePointerResize);
  document.addEventListener("pointerup", endPointerResize);
  document.addEventListener("pointercancel", endPointerResize);
  document.addEventListener("keydown", handleKeyboardResize);
  document.addEventListener("click", resetLayout);
  desktop.addEventListener("change", hydrate);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hydrate, { once: true });
  } else {
    hydrate();
  }

  new MutationObserver(queueHydration).observe(document.documentElement, {
    attributeFilter: ["data-results-run-id"],
    attributes: true,
    childList: true,
    subtree: true
  });
}());
