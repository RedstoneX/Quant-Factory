# Synthetic standalone preview reproduction

This procedure renders the interaction design with deterministic invented
data. It does **not** reproduce SPYM, R07, MES, a backtest, or profitability.
The visible page is labelled `SYNTHETIC REVIEW / NOT TRADING EVIDENCE`.

From `review/dashboard-integration/prototype`:

```bash
python3 chart-first-private/generate-synthetic-evidence.py
python3 -m http.server 8000
```

Then open:

```text
http://127.0.0.1:8000/synthetic-review-preview.html
```

The page loads Plotly 3.1.0 from jsDelivr, so first rendering requires access
to that public CDN. The generator writes exactly 53,528 invented price rows and
366 invented trade rows, matching the interaction contract. Do not use its
JSON as a test fixture, research artifact, or evidence record. Delete
`chart-first-private/synthetic-review-evidence.json` after review; it is
intentionally not included in this package.

Expected review-only checks:

- the synthetic warning is visibly present;
- Metrics and Trades switch;
- chart interval and view controls respond;
- chart/report panels resize on desktop and stack on smaller screens; and
- selecting an invented trade focuses its invented chart markers.

The exact approved JavaScript remains in the package as a source reference but
is not loaded by this reproduction.
