"""Paired communication-condition experiments for warehouse fleet allocation.

Run from the repository root: python3 -m warehouse_sim.experiments.run_communication_experiments
Results are written to communication_raw_results.csv and communication_summary.csv.
"""
import csv
import random
import statistics
from pathlib import Path

from warehouse_sim.model import WarehouseModel
from warehouse_sim.experiments.run_experiments import collect_metrics, T_CRITICAL



ALGORITHMS = ["centralized", "auction"]
SEEDS = [42, 123, 456, 789, 1001]
SIMULATION_TICKS = 200
SCENARIOS = {
    "baseline": {"latency_ticks": 0, "outage_start": None, "outage_end": None},
    "latency_1_tick": {"latency_ticks": 1, "outage_start": None, "outage_end": None},
    "latency_3_ticks": {"latency_ticks": 3, "outage_start": None, "outage_end": None},
    "short_outage": {"latency_ticks": 0, "outage_start": 50, "outage_end": 65},
    "outage_recovery": {"latency_ticks": 1, "outage_start": 50, "outage_end": 90},
}
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RAW_FILE = RESULTS_DIR / "communication_raw_results.csv"
SUMMARY_FILE = RESULTS_DIR / "communication_summary.csv"
METRICS = [
    "tasks_completed", "throughput", "pending_tasks", "active_tasks", "average_battery",
    "collision_count", "deadlocks_resolved", "reroutes", "messages_sent",
    "messages_delivered", "messages_delayed", "messages_dropped", "messages_in_transit",
    "messages_held_by_outage", "shock_recovery_successes", "shock_recovery_failures",
    "auctions_started", "auctions_timed_out", "auctions_failed", "assignment_message_retries", "assignment_rejections",
    "mean_auction_duration_ticks", "auction_duration_observations",
    "mean_assignment_delay_ticks", "assignment_delay_observations", "mean_assignment_delivery_delay_ticks", "assignment_delivery_delay_observations", "mean_task_wait_to_assignment_ticks", "task_wait_to_assignment_observations",
]


def run_one(scenario, config, algorithm, seed):
    random.seed(seed)
    model = WarehouseModel(seed=seed, **config)
    model.fleet_manager.set_allocation_mode(algorithm)
    for _ in range(SIMULATION_TICKS):
        model.step()
    result = collect_metrics(model, algorithm, seed, SIMULATION_TICKS)
    result["scenario"] = scenario
    result["latency_ticks"] = config["latency_ticks"]
    result["outage_start"] = config["outage_start"]
    result["outage_end"] = config["outage_end"]
    print(f"Scenario={scenario:18} Algorithm={algorithm:12} Seed={seed} Tasks={result['tasks_completed']} MsgSent={result['messages_sent']}")
    return result


def mean_ci(values):
    n = len(values)
    mean = statistics.mean(values) if n else 0.0
    std = statistics.stdev(values) if n > 1 else 0.0
    margin = T_CRITICAL.get(n - 1, 1.96) * std / (n ** 0.5) if n > 1 else 0.0
    return n, mean, std, mean - margin, mean + margin


def summarize(results):
    rows = []
    for scenario in SCENARIOS:
        for algorithm in ALGORITHMS:
            subset = [r for r in results if r["scenario"] == scenario and r["algorithm"] == algorithm]
            for metric in METRICS:
                n, mean, std, lo, hi = mean_ci([r[metric] for r in subset])
                rows.append({"scenario": scenario, "algorithm": algorithm, "metric": metric,
                            "runs": n, "mean": mean, "std": std, "ci95_lower": lo, "ci95_upper": hi})
        # Paired seed-level auction minus centralized differences, when both observations exist.
        for metric in METRICS:
            paired = []
            for seed in SEEDS:
                by_alg = {r["algorithm"]: r for r in results if r["scenario"] == scenario and r["seed"] == seed}
                if all(a in by_alg for a in ALGORITHMS):
                    paired.append(by_alg["auction"][metric] - by_alg["centralized"][metric])
            n, mean, std, lo, hi = mean_ci(paired)
            rows.append({"scenario": scenario, "algorithm": "paired_auction_minus_centralized", "metric": metric,
                        "runs": n, "mean": mean, "std": std, "ci95_lower": lo, "ci95_upper": hi})
    return rows


def save_csv(rows, path):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {path}")


def main():
    all_results = []
    total = len(SCENARIOS) * len(ALGORITHMS) * len(SEEDS)
    count = 0
    print(f"Communication experiments: {len(SCENARIOS)} scenarios x {len(ALGORITHMS)} algorithms x {len(SEEDS)} seeds = {total} runs")
    for scenario, config in SCENARIOS.items():
        for seed in SEEDS:
            for algorithm in ALGORITHMS:
                count += 1
                print(f"Run {count}/{total}")
                all_results.append(run_one(scenario, config, algorithm, seed))
    save_csv(all_results, RAW_FILE)
    save_csv(summarize(all_results), SUMMARY_FILE)
    print("Experiment suite complete.")
    print(f"Raw: {RAW_FILE}\nSummary: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
