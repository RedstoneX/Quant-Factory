"""Report Monte Carlo evidence availability for the current RSI workflow."""
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
from backtesting.monte_carlo import MonteCarloConfig, run_monte_carlo, write_report
from backtesting.monte_carlo.sources import load_rsi_walk_forward_source

INPUT = PROJECT_ROOT / "results" / "rsi_spy_walk_forward.json"
OUTPUT = PROJECT_ROOT / "results" / "rsi_spy_monte_carlo.json"

def main():
    source = load_rsi_walk_forward_source(INPUT)
    result = run_monte_carlo(source, MonteCarloConfig())
    write_report(OUTPUT, result.to_dict())
    print(f"Monte Carlo status: {result.status}")
    print(f"Observations: {result.observation_count}")
    for reason in result.reasons: print(f"Reason: {reason}")
    print(f"Saved report to {OUTPUT}")
if __name__ == "__main__": main()
