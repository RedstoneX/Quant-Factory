---
name: vbt-rust-backend
description: "Use the VectorBT PRO Rust backend from Python. Use when checking extension compatibility, selecting or benchmarking backends, or comparing results with Numba. Use vbt-rust-native for native Rust programs and ports of custom simulators."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Rust backend in Python

`vectorbtpro-rust` is an optional compiled backend. Automatic dispatch prefers Rust for supported,
compatible calls when an eligible matching build is installed, and falls back to Numba otherwise.
For Rust programs without Python, use `vbt-rust-native`.

Read `vbt-basics` once, then follow availability, dispatch, and parity below.

## 1. Check availability

* `vbt.is_rust_available()` is `True` only when `vectorbtpro_rust` imports and its version equals
  the VBT version exactly. `vbt.rs` exists only then. After upgrading vectorbtpro, upgrade
  `vectorbtpro-rust` to the same version. A mismatch warns when availability is checked, and the
  cached result makes automatic dispatch use Numba.
* The availability result is cached. `vbt.is_rust_available.cache_clear()` reruns that check, but
  does not reload a native library already imported. Restart Python after installing or rebuilding
  the extension so the library and `vbt.rs` alias are loaded together.
* The `__build_profile__` attribute of `vbt.rs` is `"release"` for published wheels and `"dev"` for
  local debug builds. Automatic dispatch warns and skips dev builds unless `VBT_RUST_DEV_AUTO=1` is
  set before importing vectorbtpro. Dev builds can be dozens of times slower, so never time them.
* The extension comes as platform wheels in each GitHub release. Install `vectorbtpro-rust` from
  them before installing `vectorbtpro`, as described in `/installation/#rust-backend`, and do not
  install `vectorbtpro[rust]` from GitHub. Building from source needs native compilers and can
  require substantial memory and time. Keep installation within the task scope described in
  `vbt-basics`.

## 2. Know which calls run on Rust

* Rust mirrors cover many built-in kernels: rolling and generic operations, indicators, signals,
  returns and metrics, records, and the static simulators behind `vbt.PF.from_signals` and
  `vbt.PF.from_orders`. Some support `parallel=True`. The API page of each Numba function names its
  Rust counterpart and whether it can run in parallel.
* Your own `@njit` functions, kernels that take a function, such as `vbt.rec_nb.reduce_mapped_nb`,
  and every simulation with a callback, such as `signal_func_nb`, `adjust_func_nb`, or
  `vbt.PF.from_order_func`, always run on Numba, because a callback cannot cross into Rust. Their
  Rust counterparts exist only for native Rust programs, described in `vbt-rust-native`.
* Rust kernels are compiled ahead of time, so they skip the Numba compilation of the first call in
  every process. Steady-state speed is similar to Numba, often somewhat faster. They also release
  the GIL around native computation. Measure representative inputs and include Python argument
  conversion when comparing end-to-end calls. Dispatch overhead is typically several microseconds
  per call. Measure import, compilation, argument preparation, and kernel execution separately to
  locate expensive work.

## 3. Control the backend

Automatic dispatch prefers Rust and falls back to Numba, so most code should pass nothing. Change it
only to compare backends or to pin one:

| Goal | Option |
| --- | --- |
| Force Numba for one call | `jitted="nb"` |
| Force Rust, raising if it cannot run | `jitted="rs"` |
| Run on several threads | `jitted=dict(parallel=True)`, or `jitted=dict(jitter="rs", parallel=True)` |
| Choose by benchmark results | `jitted="auto_bench"` (`"ab"`) or `"auto_bench_mixed"` (`"abm"`) per call, or `vbt.settings.jitting["backends"]["auto_mode"] = "bench"` or `"bench_mixed"` globally, after building a benchmark cache |
| Disable automatic Rust globally | `vbt.settings.jitting["backends"]["auto_mode"] = False` |
| Restore automatic Rust for one call while it is disabled globally | `jitted="auto"` |
| Change the policy for some functions | an entry in `vbt.settings.jitting["resolve_overrides"]` with `match` and `resolve_kwargs` |

* `jitted` is accepted by accessor methods, indicators, simulations, and metrics, such as
  `close.vbt.rolling_mean(20, jitted="nb")` or `vbt.PF.from_signals(..., jitted="nb")`.
* `jitted="rs"` is strict: it raises when Rust is missing, when the version differs, when a dtype
  cannot be cast safely, or when `parallel=True` is requested from a kernel without parallel
  support. Automatic dispatch falls back to Numba in all these cases instead, so
  `jitted=dict(parallel=True)` runs parallel Numba where Rust cannot parallelize. Rust accepts
  booleans, integers up to 64 bits, `float32`, and `float64`. Inputs of `float16` or complex dtype
  fall back to Numba, or raise with `jitted="rs"`.
* `vbt.resolve_jitted(func, disable_auto_backend=True)` resolves the Numba implementation while
  automatic dispatch stays enabled globally.
* Explicit jitter options bypass automatic backend preference. Backend runtime options such as
  `parallel=True` are the exception and can still use automatic Rust dispatch.
* Changing import-time globals, such as flexible indexing or math tolerances, makes automatic
  dispatch fall back to Numba and `jitted="rs"` raise, because Rust assumes the defaults.
* Memory layout changes which backend wins. Rust rolling kernels walk rows and copy column-major
  input into row order first, while Numba column kernels gain most on column-major arrays, such as
  `np.asfortranarray(arr)` or a DataFrame built from separate columns. Benchmark on the layout the
  pipeline produces.
* Parallel Rust needs enough independent columns or groups to offset scheduling overhead. Start with
  one layer of parallelism. Combining it with outer threads or processes can oversubscribe CPU
  cores.
* AutoBench uses benchmark records from `vbt.settings.jitting["backends"]["auto_bench_path"]`, which
  defaults to `"benchmarks/cache.json"`. The matrix CLI builds this cache. Use its `--help` and, in
  a source checkout, `benchmarks/README.md` to choose a relevant workload. A full matrix can be
  expensive. AutoBench selects within the requested serial or parallel mode and falls back to Numba
  in that mode. AutoBenchMixed compares both modes and falls back to serial Numba. For a function
  resolved with `jitted="auto_bench"`, `vbt.jit_reg.get_auto_bench_backend(func)` tells which
  backend its last call used.
* `vbt.resolve_jitted(vbt.ret_nb.sharpe_ratio_1d_nb, jitted="rs")` returns a Rust function with the
  Numba signature. The adapter validates and prepares arguments, with overhead that depends on their
  shapes, dtypes, and layouts. Pass `use_backend_wrapper=False`, or take the function from the
  `vbt.rs` namespace, to get the raw kernel. Raw kernels bypass the Python backend adapter. Their
  PyO3 conversions and native validation still apply, and each signature specifies its accepted
  dtypes. Pass enum codes such as `vbt.pf_enums.PriceType.Open`, not string names. Use them only
  when profiling shows the wrapper overhead matters.

## 4. Verify parity with Numba

For a parity check, force Rust and Numba on the same inputs. Automatic dispatch can fall back to
Numba, so comparing it with explicit Numba alone does not prove Rust parity. This program checks the
extension and reports when Rust could not be tested. It compares a rolling risk calculation and a
scheduled target-weight portfolio, exercising shared cash and automatic order sequencing:

```python
import numpy as np
import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=1000, timeframe="1D", seed=42)
returns = data.close.pct_change()
nb_vol = returns.vbt.rolling_std(20, jitted="nb")
weights = data.symbol_wrapper.fill(np.nan)
weights.iloc[::20] = [0.6, 0.4]
pf_kwargs = dict(
    size=weights,
    size_type="targetpercent",
    cash_sharing=True,
    group_by=True,
    call_seq="auto",
    price="open",
    val_price=data.open,
    fees=0.001,
    init_cash=10_000,
)
nb_pf = vbt.PF.from_orders(data, jitted="nb", **pf_kwargs)
assert len(nb_pf.orders.values) > 0
assert (nb_pf.orders.values["idx"] % 20 == 0).all()

if vbt.is_rust_available():
    rs_vol = returns.vbt.rolling_std(20, jitted="rs")
    np.testing.assert_allclose(rs_vol, nb_vol, equal_nan=True)
    rs_pf = vbt.PF.from_orders(data, jitted="rs", **pf_kwargs)
    assert rs_pf.equals(nb_pf, after_broadcast=True)
    returns = nb_pf.returns.values
    sharpe_rs = vbt.resolve_jitted(vbt.ret_nb.sharpe_ratio_1d_nb, jitted="rs")
    np.testing.assert_allclose(
        sharpe_rs(returns, ann_factor=365.0),
        vbt.ret_nb.sharpe_ratio_1d_nb(returns, ann_factor=365.0),
        equal_nan=True,
    )
    print("Rust and Numba parity checks passed")
else:
    print("Numba ran. Rust parity was not tested because a matching extension is unavailable.")
```

* Portfolios compare with `pf.equals(other_pf, after_broadcast=True)`, which compares records,
  stored state, and configuration using the configured numeric tolerances. Pass `check_exact=True`
  when exact comparison is required, and `debug=True` to locate a mismatch. Compare arrays with
  `np.allclose`, because floating-point sums can differ in the last bits, especially in parallel
  reductions. Investigate any difference that changes a signal or an order.
* Compare against compiled Numba, not with `NUMBA_DISABLE_JIT` set.
* For speed, time steady-state calls after a warm-up call, on a release build. `vbt.run_benchmarks`
  compares backends on built-in kernels.

## Pitfalls

* Explicit `jitted="rs"` in shared code breaks on machines without the extension. Prefer the default
  dispatch in code others will run.
* To call your own Rust kernel from Python, build it as a PyO3 function and attach it to the Numba
  function with `@vbt.register_jitted(backends=vbt.RustBackendSpec("my_module.my_func_rs"))`, as
  described under "Backend specs" in `rust/README.md`. Its signature must match the Numba function.
  Automatic argument specs require VBT annotations such as `vbt.tp.Array1d`. Otherwise, supply
  `args` explicitly on `RustBackendSpec`.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/documentation/rust/`: dispatch modes, fallback, compatibility, and building
* `/tutorials/from-python-to-rust/static/`: high-level VBT, Numba, and PyO3, with parity checks
* `/features/performance/compute-backends/`: backend selection, AutoBench, and benchmarks
