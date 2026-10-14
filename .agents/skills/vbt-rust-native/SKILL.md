---
name: vbt-rust-native
description: "Build native Rust programs with the VectorBT PRO crate. Use when implementing batch or streaming strategies, managing checkpoints and strategy state, exporting results to Python, or porting custom Numba simulators. Use vbt-rust-backend for the Python extension and backend selection."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Native Rust with VBT

The `vectorbtpro-rust` crate provides kernels, simulation engines, and streaming accumulators for
Rust programs without Python. Use the installed release's native API and Cargo manifest as the
contract. For a source checkout, read `rust/README.md` and generate API documentation with
`cargo doc --manifest-path rust/Cargo.toml --no-deps`. Add `--features serde` to include checkpoint
APIs. In a consuming project, enable the dependency's required features and use `cargo doc` to
inspect its public builders and traits before writing code.

Start with release selection, then choose a route: static kernels and simulators when orders or
signals are known in advance, or a strategy simulator when decisions depend on simulation state.
Read the streaming section for incremental execution and the porting section for a loop already
written in Numba. When exchanging results with Python, read `vbt-basics` for API discovery and
`vbt-analysis` for reconstruction and metrics. Use `vbt-rust-backend` to operate the Python backend.
Installing that extension does not port custom code.

## 1. Select the release and build

For a Rust program or service, choose a VBT release tag and check its Cargo manifest for the
`ndarray` minor version, because public functions take `ndarray` views. When exchanging results with
Python, use the tag matching that Python package's version. Replace the tag below with the selected
release tag:

```toml
[dependencies]
ndarray = "0.16"
vectorbtpro-rust = { git = "https://github.com/polakowo/vectorbt.pro.git", tag = "<matching-vbt-tag>" }
```

* For a local source checkout, use `vectorbtpro-rust = { path = "../vectorbt.pro/rust" }` instead.
  The API reference of the latest release is at `https://members.vectorbt.pro/rust-api/`.
* The repository is private. If Cargo cannot fetch it, run `gh auth setup-git` or set
  `CARGO_NET_GIT_FETCH_WITH_CLI=true`. Enable the `serde` feature to serialize accumulators,
  records, and stepper checkpoints. The `python` feature is only for building the extension. Build
  with `cargo build --release`.
* Kernels are `bon` builders: set required arguments by name, omit defaults, and finish with
  `.call()`, such as `sharpe_ratio_1d().returns(returns.view()).ann_factor(252.0).call()`. Strategy
  simulators and accumulators finish with `.build()` and then run. Defaults follow the Numba kernels
  rather than VBT settings, so `init_cash` is 100 unless set. Builders that support Rayon take
  `.parallel(true)`. Fallible calls return `VbtResult`, whose `VbtError` carries a category such as
  `Value` or `RejectedOrder`.
* Check native preconditions when translating Python calls. Some infallible kernels rely on inputs
  that their Python wrappers validate, such as positive rolling windows and `minp <= window`.
* Flexible arguments accept a scalar or a 2D view directly. A 1D view is ambiguous, so wrap it as
  `FlexArray2dRow(view)` to vary by row or `FlexArray2dCol(view)` to vary by column. Some optional
  arguments of the static simulators take the wrapped value, such as
  `.init_cash(Some(FlexArray1dView::scalar(1000.0)))`.
* Enums are uppercase constants, such as `PriceType::OPEN` and `SizeType::VALUE_PERCENT100`.
  Float-typed options take a cast, such as `.stop_entry_price(StopEntryPrice::FILL_PRICE as f64)`.
* The API mirrors the Numba kernels and is versioned with VBT. It is not a stable SDK, and
  serialized state is not compatible across releases.

## 2. Run precomputed signals and kernels

When signals, orders, and stops are known before the simulation, call the static simulators
`from_signals` in `portfolio::from_signals` and `from_orders` in `portfolio::from_orders`. They are
the same kernels that run behind `vbt.PF.from_signals` and `vbt.PF.from_orders` with the Rust
backend. Their builders mirror the low-level Numba kernels and produce the same records. Translate
high-level broadcasting, labels, string enums, and settings into explicit kernel inputs. Compute
those inputs with the builders in `generic`, `indicators`, `signals`, and `returns`:

```rust
use ndarray::{array, Array2};
use vectorbtpro_rust::base::flex_indexing::FlexArray1dView;
use vectorbtpro_rust::generic::base::{crossed_above, crossed_below};
use vectorbtpro_rust::generic::rolling::rolling_mean;
use vectorbtpro_rust::portfolio::from_signals::from_signals;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let close: Array2<f64> = array![
        [10.0, 20.0], [11.0, 19.0], [12.0, 18.0], [11.0, 19.0], [10.0, 21.0],
        [9.0, 22.0], [10.0, 21.0], [12.0, 20.0], [13.0, 19.0], [12.0, 18.0],
    ];
    let fast = rolling_mean().arr(close.view()).window(2).call();
    let slow = rolling_mean().arr(close.view()).window(4).call();
    let entries = crossed_above().arr1(fast.view()).arr2(slow.view()).call()?;
    let exits = crossed_below().arr1(fast.view()).arr2(slow.view()).call()?;

    let group_lens = array![1, 1];
    let sim_out = from_signals()
        .target_shape(close.dim())
        .group_lens(group_lens.view())
        .close(close.view())
        .init_cash(Some(FlexArray1dView::scalar(1000.0)))
        .long_entries(entries.view())
        .long_exits(exits.view())
        .fees(0.001)
        .call()?;
    println!("{} orders", sim_out.order_records.len());
    sim_out.save_npz(std::env::temp_dir().join("static.npz"))?;
    Ok(())
}
```

These signals are decided on the close and fill at the same close. For next-open execution, shift
the signals and any close-derived stop inputs by one bar with `fshift` in `generic::base`, supply
open prices, and select `PriceType::OPEN`. Use `.fill_value(false)` when shifting boolean signals.

For custom computation outside portfolio simulation, choose the corresponding native engine:

| Numba customization | Native Rust |
| --- | --- |
| Apply, map, and reduce functions | Engines in `generic::apply_reduce` and `records::apply_reduce`, such as `RollingReducer` |
| Signal generators and `rank_nb` | `SignalGenerator` and `SignalRanker` in `signals` |
| `allocate_meta_nb`, `optimize_meta_nb` | `PointAllocator` and `RangeOptimizer` in `portfolio::pfopt` |

## 3. Choose the strategy simulator and its state

Use `OrderSimulator` for one order per column and bar, `FlexOrderSimulator` for several orders, and
`SignalSimulator` for state-dependent signals with built-in stop and limit handling. Keep
strategy-owned memory in the strategy struct. The table maps Python customization points to their
native equivalents when porting:

| Numba callback | Native Rust |
| --- | --- |
| `order_func_nb` of `from_order_func` | `OrderSimulator` with an `OrderStrategy` |
| `flex_order_func_nb` | `FlexOrderSimulator` with a `FlexOrderStrategy` |
| `signal_func_nb` of `from_signals` | `SignalSimulator` with a `SignalStrategy` and a `SignalConfig` |
| Active-stop and pending-limit adjustments in `adjust_func_nb` | `SignalStrategy::signals` with `sl_stop_mut`, `tsl_stop_mut`, `pending_limit_mut`, and related context methods |
| Prepared-order changes in `pre_order_segment_func_nb` | `SignalStrategy::on_order_segment_start` with `decisions_mut` |
| `pre_sim_func_nb`, `post_sim_func_nb` | Ordinary Rust code before and after the run |
| `pre_group_func_nb`, `post_group_func_nb` | `on_group_start`, `on_group_end` |
| `pre_segment_func_nb`, `post_segment_func_nb` | `on_segment_start`, `on_segment_end` |
| Call-sequence changes in `pre_segment_func_nb` | `OrderStrategy::on_order_segment_start` with `call_seq_mut` |
| `post_order_func_nb` | `on_order_end` with the execution report |
| `from_order_func_rw_nb`, `from_flex_order_func_rw_nb` | No batch counterpart. Use a stepper |
| Arrays passed through templates and `in_outputs` | Fields of the strategy struct |

* Wrap a closure with `FnOrderStrategy`, `FnSignalStrategy`, or `FnFlexOrderStrategy`, or implement
  the trait on a struct to keep state. `run_single` runs one group, `run` takes a factory with one
  strategy per group, and `run_parallel` runs groups on Rayon. Rows within a group stay sequential.
* `SimulationConfig` and `StreamConfig` need `.cash_sharing(true)` for a shared-cash group, unlike
  the static `from_signals` builder, where grouped columns always share cash.
* In a context, `col()` is the absolute column for indexing input arrays, and `local_col()` indexes
  state sized from `GroupInfo` per group. `i()` counts rows within the current run or stepper, and
  `global_i()` adds the row offset of a continued run or restored stepper, so store deadlines with
  `global_i()`.
* In `on_order_end`, compare `report.before.position` and `report.after.position` to detect a close,
  and read the record of this execution with `ctx.order_record_now()`. Earlier records come from
  `ctx.order_records(col)`, which is `None` in a stepper unless it retains records. An
  `OrderStrategy` receives `on_order_end` even when `order` returned `None`, with no report.
  Flexible and signal strategies receive it only after an order is processed.
* With cash sharing, `call_seq_mut` reorders or repeats columns within the group's segment, and
  `save_call_seq(true)` on the simulator keeps the sequence actually used. Without cash sharing the
  sequence is read-only. Call-sequence entries are local to the group, while `col()` is absolute.
* Signal callbacks run left to right and observe the row's pre-execution portfolio state. Orders
  execute after all columns produce their signals, so changing the call sequence cannot make later
  signal callbacks observe earlier fills. `from_ago` shifts parameter lookup, not the row on which
  the callback runs or the order executes. Delay close-based signals explicitly.
* Adjust active stops and pending limits in `SignalStrategy::signals`, before the current row checks
  for hits. Its context exposes methods such as `sl_stop_mut` and `pending_limit_mut`. Changes
  affect live pending state. A fill that opens, reverses, or increases a position re-arms stops from
  configuration, replacing those adjustments.
* `on_order_segment_start` runs after signal, stop, and limit resolution. Its `decisions_mut`
  adjusts prepared orders, execution settings, new pending limits, and fill-time stop setup before
  execution. It is too late there to change which active stop or limit was hit on that row. It
  cannot insert an order that the signals did not produce. Use an `OrderStrategy` or
  `FlexOrderStrategy` for direct order construction.
* Inactive rows still update accounting but skip orders and signals. `call_pre_segment` and
  `call_post_segment` on the configuration run the segment hooks on those rows too. `stop_group()`
  at group start skips every row, and during a row it lets that row finish. The output's `sim_end`
  shows the shortened range.
* To continue a batch over later rows, pass the earlier output's `last_state` to the builder of the
  same simulator family, such as `OrderSimulator::builder().config(config).last_state(state)`. Rows
  continue after `last_state.last_idx`, so records keep their global rows and cumulative IDs. Set
  `row_offset` only to choose another origin. Strategy state lives in the strategy you own with
  `run_single`, or in the completed strategies returned by `run` and `run_parallel`.

## 4. Stream bars and preserve state

* Each simulator has a stepper, `OrderStepper`, `FlexOrderStepper`, and `SignalStepper`, that takes
  a `StreamConfig` and one `StreamRow` per bar and reproduces the batch records exactly. A
  `SignalStepper` also takes `SignalStreamOptions` for stream-lifetime settings, such as stop arrays
  and `auto_call_seq`, and one `SignalRow` per bar, where `with_sl_stop` supplies row stops. Each
  step returns only that bar's records. `StreamRecordRetention::All` additionally retains history
  for `finish()`. Set `target_rows` for a finite replay. Input validation errors leave the stepper
  usable. Errors after execution starts poison it because state may already have changed. Restore a
  checkpoint taken before the failed bar to retry safely. Its post-error `state()` is not a
  rollback, and `finish()` still reports records already produced on the failed bar.
* `finish()` returns `StreamOutput`, with failures in `output.error`. Check that field even when
  every `step` succeeded because a group-end callback can fail during finalization.
* When `from_ago` selects an earlier row within the current wrapper, supply that row's resolved
  parameters through `SignalRow::with_source_config`. Continuing an existing pending limit from
  `last_state` needs no earlier-row configuration because its execution snapshot is already saved.
* Timestamps in `StreamRow` are optional nanosecond Unix times that must not decrease. They are
  required for index-based time in force, expiry, and time or datetime stops. A stream that starts
  after row zero rejects them because the earlier index is missing, so set `freq` on the
  configuration instead. An open-ended stream with timestamps retains every timestamp, so its memory
  grows for the lifetime of the stream.
* `last_state` warm-starts a stepper as it continues a batch. For order and flexible-order steppers,
  `start_row` is a local scheduling cursor and `row_offset` the global origin. A continued chunk
  normally starts at row zero and omits the origin.
* `stepper.strategy_mut(group)` reaches the strategy between steps. Cloning a stepper is an exact
  in-memory checkpoint. To survive a restart, enable `serde`, save `stepper.checkpoint()` in a
  format that keeps NaN, such as MessagePack, and restore with `from_checkpoint` and the same
  configuration. An output's `last_state` or a stepper's `state()` continues the portfolio but does
  not preserve strategy state, record history, or random-number generators. Callbacks on a stepper
  restored from `last_state` see `None` for earlier records even with `StreamRecordRetention::All`.
  Clone a live stepper when a checkpoint must keep that history.
* An application checkpoint also needs the symbol order, last accepted feed timestamp or cursor, and
  any accumulators held outside the strategy. Persist them atomically with the stepper after
  completing the bar and updating strategy state. Validate symbol order on restore and resume after
  the saved cursor so already accepted bars do not advance the state twice.
* Accumulators in `generic::streaming`, `indicators::streaming`, and `returns::streaming` update
  indicators one value at a time and can be cloned as checkpoints. `update` cannot fail and returns
  NaN during numeric warm-up where applicable. `reset` clears observations but keeps configuration,
  and `samples_seen` counts observations since construction or the last reset. Give each symbol or
  column its own accumulator, such as in a `HashMap` keyed by symbol. Recursive ones, such as EWM
  and Wilder smoothing in `Atr` and `Adx`, need the same initial state and history as the batch run.
  Feed the same prefix or restore the corresponding accumulator checkpoint. Recomputing on a
  trailing window can change their values.
* For a strategy that decides at the close and executes at the next open, first step the current bar
  using signals and stop distances prepared from the previous bar. Then update each accumulator once
  with the completed bar to prepare the next decision. Keep these delayed values in strategy state
  so checkpoints preserve the decision timing.
* Emitted order records describe simulated fills after processing the bar. Broker submission needs a
  separate decision interface and reconciliation of actual fills, partial fills, and rejections.
* `save_npz` on a simulation output writes an archive that `vbt.load_simulation_npz` reads back.
  Pass it as `sim_out` to `vbt.Portfolio` with `data` or the wrapper and close, and with the
  `init_cash`, `cash_sharing`, and grouping the Rust run used. Mismatched reconstruction arguments
  can change the resulting equity and metrics. `save_records_npy` in `records::persistence` saves a
  single record array, and `NpzWriter` saves records together with strategy arrays for `np.load`.

## 5. Verify batch and streaming results

* Equal Rust and Numba seeds do not guarantee identical random samples. Generate inputs once and
  reuse them for cross-backend parity checks. Test seeded repeatability separately within each
  backend.
* `ensure_simulation_eq` from `SimulationEq` compares supported simulation fields exactly, treats
  NaNs as equal, and names the first mismatch. Batch-to-stream comparison requires a fully consumed
  finite stream with complete retained history. It does not compare strategy-owned state or
  batch-only arrays, so check those separately when they matter. Stepper records arrive row by row
  and batch records column by column. Sort by column and id before manual comparison.

This program runs a strategy in batch and bar by bar, checks that both agree, and updates a moving
average as bars arrive:

```rust
use ndarray::array;
use vectorbtpro_rust::generic::streaming::RollingMean;
use vectorbtpro_rust::portfolio::enums::{Order, OrderSide};
use vectorbtpro_rust::portfolio::simulator::{
    FnOrderStrategy, OrderContext, OrderSimulator, OrderStepper, SimulationConfig, SimulationEq,
    StreamConfig, StreamRecordRetention, StreamRow,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let close = array![[100.0], [98.0], [105.0], [112.0]];
    let group_lens = array![1];
    let strategy = || {
        FnOrderStrategy::new(|ctx: &OrderContext<'_, '_>| {
            let price = ctx.close(ctx.col());
            let position = ctx.position(ctx.col());
            if price <= 100.0 && position == 0.0 {
                Ok(Some(Order::builder().size(1.0).build()))
            } else if price >= 110.0 && position > 0.0 {
                Ok(Some(Order::builder().size(-position).build()))
            } else {
                Ok(None)
            }
        })
    };

    let config = SimulationConfig::builder()
        .target_shape(close.dim())
        .group_lens(group_lens.view())
        .close(close.view())
        .init_cash(1000.0)
        .build()?;
    let batch_out = OrderSimulator::builder().config(config).build()?.run_single(&mut strategy())?;

    let stream_config = StreamConfig::builder()
        .group_lens(group_lens.view())
        .init_cash(1000.0)
        .target_rows(close.nrows())
        .record_retention(StreamRecordRetention::All)
        .build()?;
    let mut stepper = OrderStepper::new_single(stream_config, None, strategy())?;
    let mut ma = RollingMean::builder().window(2).build()?;
    for row in close.rows() {
        let step = stepper.step(StreamRow::builder().close(row).build())?;
        for order in step.order_records() {
            let size = if order.side == OrderSide::BUY { order.size } else { -order.size };
            println!("row {}: {:+.0} at {:.0}", order.idx, size, order.price);
        }
        println!("close {:.0}, ma {:.1}", row[0], ma.update(row[0]));
    }
    batch_out.ensure_simulation_eq(&stepper.finish())?;
    Ok(())
}
```

## 6. Port a custom simulator

A custom simulator written from the order execution functions, as described in
`vbt-custom-simulators`, ports line by line: the crate has the same execution layer as `vbt.pf_nb`,
with matching arguments, defaults, validation, and results. Port when the simulator runs in
production, in a standalone binary, or on many cores without Numba's compilation at startup. Keep
developing in Numba while the logic changes.

| Numba | Rust |
| --- | --- |
| `vbt.pf_nb.execute_order_nb`, `process_order_nb`, `order_nb`, `close_position_nb`, `approx_order_value_nb` | `execute_order`, `process_order`, `order`, `close_position`, `approx_order_value` in `portfolio::core` |
| `vbt.pf_nb.check_price_hit_nb`, `check_limit_hit_nb`, `check_stop_hit_nb` | `check_price_hit`, `check_limit_hit`, `check_stop_hit` in `portfolio::core` |
| `vbt.pf_enums.ExecState`, `PriceArea`, `order_dt`, enums | `ExecState`, `PriceArea`, `OrderRecord`, and constants such as `SizeType::VALUE` in `portfolio::enums` |
| `vbt.flex_select_nb`, `vbt.pf_nb.insert_argsort_nb`, `vbt.nb.repartition_nb` | `FlexArray2dView` in `base::flex_indexing`, `insert_argsort` in `utils::array`, `repartition` in `generic::base` |

* `process_order` needs its record types even without logs:
  `process_order::<OrderRecord, LogRecord>()`.
* Fill the record array with `OrderRecord::empty()`, since `OrderRecord` has no default. Keep the
  counters in an `Array1<i64>`.
* Save the repartitioned records with `NpzWriter` from `records::persistence`, together with any
  arrays Python needs. `np.load` returns them with the `order_dt` dtype, ready for `vbt.PF`.

These lines from a port of the ladder program in `vbt-custom-simulators` show the changes:

```rust,ignore
let mut order_records = Array2::from_elem((n_rows * n_levels, n_cols), OrderRecord::empty());
let mut order_counts = Array1::<i64>::zeros(n_cols);

let (hit_price, _, _) = check_price_hit().open(o).high(h).low(l).close(c).price(pending[k]).call();
let buy = order().size(level_value).price(hit_price).size_type(SizeType::VALUE).direction(Direction::LONG_ONLY).call();
state.val_price = hit_price;
let (result, new_state) = process_order::<OrderRecord, LogRecord>()
    .group(col as i64).col(col as i64).i(i as i64)
    .exec_state(state)
    .order(buy)
    .price_area(price_area)
    .order_records(&mut order_records.view_mut())
    .order_counts(&mut order_counts.view_mut())
    .call()?;
state = new_state;

let records = repartition().arr(order_records.view()).counts(order_counts.view()).call()?;
let mut npz = NpzWriter::create("ladder.npz")?;
npz.write_records("order_records", &records)?;
npz.write_array2("close", &close)?;
npz.finish()?;
```

In Python, `vbt.PF(wrapper, np.load("ladder.npz")["order_records"], close=..., init_cash=...)` wraps
the records as described in `vbt-custom-simulators`. Run the Numba simulator on the same arrays and
require identical records before relying on the port.

## Pitfalls

* Preserve decision timing when porting. A strategy that reads the current close cannot fill at that
  bar's open. The examples in this skill use close fills and assume execution at the observed close.
  Delay close-based decisions when that execution assumption does not fit the task.
* Benchmark on representative inputs using the release build selected above. Compare records and
  final state before interpreting a speedup, and keep independent groups isolated during parallel
  execution.

## Documentation

In a source checkout, use `rust/README.md` and the crate's rustdoc. For the release's documentation
pages, use the discovery tools in `vbt-basics`:

* `/documentation/rust/`: native APIs, architecture, and building
* `/tutorials/from-python-to-rust/static/`: native kernels, exporting results, and parity checks
* `/tutorials/from-python-to-rust/dynamic/`: moving callbacks into native Rust strategies
* `/tutorials/from-python-to-rust/live/`: streaming bars, accumulators, and checkpoint recovery
