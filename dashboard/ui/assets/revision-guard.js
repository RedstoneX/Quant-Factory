(function () {
  "use strict";

  const cookieRevision = () => {
    const row = document.cookie.split(";").map((value) => value.trim()).find((value) => value.startsWith("qf_revision="));
    return row ? decodeURIComponent(row.split("=", 2)[1]) : "";
  };
  const loadedRevision = cookieRevision();
  let reloading = false;

  const requireReload = (nextRevision) => {
    if (reloading) return;
    reloading = true;
    const notice = document.createElement("div");
    notice.setAttribute("role", "alert");
    notice.style.cssText = "position:fixed;inset:0;z-index:2147483647;display:grid;place-items:center;background:#07090df2;color:#f1f5f9;font:500 16px Inter,sans-serif;text-align:center;padding:24px";
    notice.innerHTML = `<div><div style="font-size:20px;margin-bottom:8px">Quant Factory was updated</div><div style="color:#8a97a8">Reloading the current route on revision ${String(nextRevision || "current").slice(0, 12)}…</div></div>`;
    document.body.appendChild(notice);
    window.setTimeout(() => window.location.reload(), 500);
  };

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    if (response.status === 409 && response.headers.get("X-QF-Revision-Mismatch")) {
      requireReload(response.headers.get("X-QF-Revision-Mismatch"));
    }
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (...args) {
    this.addEventListener("load", () => {
      if (this.status === 409 && this.getResponseHeader("X-QF-Revision-Mismatch")) {
        requireReload(this.getResponseHeader("X-QF-Revision-Mismatch"));
      }
    });
    return originalOpen.apply(this, args);
  };

  window.setInterval(async () => {
    try {
      const response = await originalFetch("/__qf_revision__", {cache: "no-store", credentials: "same-origin"});
      const revisionDocument = await response.json();
      if (loadedRevision && revisionDocument.revision && revisionDocument.revision !== loadedRevision) requireReload(revisionDocument.revision);
    } catch (_) {
      // Service unavailability is represented elsewhere; avoid a reload loop.
    }
  }, 30000);
})();
