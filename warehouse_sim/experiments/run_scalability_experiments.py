import random
import statistics
import csv
from pathlib import Path

from warehouse_sim.model import WarehouseModel
from warehouse_sim.experiments.run_experiments import collect_metrics

FLEET_SIZES = [5, 10, 15, 20]
ALGORITHMS = ["centralized", "auction"]
SEEDS = [42, 123, 456, 789, 1001]
SIMULATION_TICKS = 200

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RAW_FILE = RESULTS_DIR / "scalability_raw_results.csv"
SUMMARY_FILE = RESULTS_DIR / "scalability_summary.csv"

METRICS = [
    "tasks_completed",
    "throughput",
    "pending_tasks",
    "average_battery",
    "collision_count",
    "deadlocks_resolved",
    "reroutes",
]

T_CRITICAL = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045,
}

def run_single(algorithm, seed, ticks, robot_count):
    random.seed(seed)
    model = WarehouseModel(seed=seed, num_robots=robot_count)
    model.fleet_manager.set_allocation_mode(algorithm)

    for _ in range(ticks):
        model.step()

    result = collect_metrics(
        model=model,
        algorithm=algorithm,
        seed=seed,
        ticks=ticks,
    )

    result["robot_count"] = robot_count

    print(
        f"Finished | Fleet: {robot_count:2} | "
        f"{algorithm:12} | Seed: {seed:4} | "
        f"Completed: {result['tasks_completed']:4} | "
        f"Pending: {result['pending_tasks']:4} | "
        f"Battery: {result['average_battery']:.2f}%"
    )

    return result

def run_all():
    results = []
    total_runs = len(FLEET_SIZES) * len(ALGORITHMS) * len(SEEDS)
    run_number = 0

    print("=" * 70)
    print("WAREHOUSE FLEET SCALABILITY EXPERIMENT")
    print(f"Fleet sizes: {FLEET_SIZES}")
    print(f"Algorithms: {ALGORITHMS}")
    print(f"Seeds: {SEEDS}")
    print(f"Ticks per run: {SIMULATION_TICKS}")
    print(f"Total simulations: {total_runs}")
    print("=" * 70)

    for fleet_size in FLEET_SIZES:
        print(f"\n######## FLEET SIZE: {fleet_size} ROBOTS ########")

        for seed in SEEDS:
            for algorithm in ALGORITHMS:
                run_number += 1
                print(f"\nRun {run_number}/{total_runs}")

                result = run_single(
                    algorithm=algorithm,
                    seed=seed,
                    ticks=SIMULATION_TICKS,
                    robot_count=fleet_size,
                )
                results.append(result)

    return results

def calculate_summary(results):
    summary = []

    for fleet_size in FLEET_SIZES:
        for algorithm in ALGORITHMS:
            subset = [
                row for row in results
                if row["robot_count"] == fleet_size
                and row["algorithm"] == algorithm
            ]

            for metric in METRICS:
                values = [row[metric] for row in subset]
                n = len(values)

                mean = statistics.mean(values) if n else 0
                std = statistics.stdev(values) if n > 1 else 0

                margin = (
                    T_CRITICAL.get(n - 1, 1.96) * std / (n ** 0.5)
                    if n > 1 else 0
                )

                summary.append({
                    "robot_count": fleet_size,
                    "algorithm": algorithm,
                    "metric": metric,
                    "runs": n,
                    "mean": mean,
                    "std": std,
                    "ci95_lower": mean - margin,
                    "ci95_upper": mean + margin,
                })

    return summary

def save_csv(data, filepath):
    if not data:
        print(f"No data to save: {filepath}")
        return

    with open(filepath, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

    print(f"Saved: {filepath}")

def main():
    results = run_all()
    summary = calculate_summary(results)

    save_csv(results, RAW_FILE)
    save_csv(summary, SUMMARY_FILE)

    print("\n" + "=" * 70)
    print("SCALABILITY EXPERIMENT SUMMARY")
    print("=" * 70)

    for metric in ["tasks_completed", "throughput", "pending_tasks", "average_battery"]:
        print(f"\n{metric.upper()}")

        for fleet_size in FLEET_SIZES:
            for algorithm in ALGORITHMS:
                row = next(
                    item for item in summary
                    if item["robot_count"] == fleet_size
                    and item["algorithm"] == algorithm
                    and item["metric"] == metric
                )

                print(
                    f"Robots: {fleet_size:2} | {algorithm:12} | "
                    f"Mean: {row['mean']:.3f} | "
                    f"Std: {row['std']:.3f} | "
                    f"95% CI: [{row['ci95_lower']:.3f}, "
                    f"{row['ci95_upper']:.3f}]"
                )

    print("\nSCALABILITY EXPERIMENTS COMPLETE")
    print(f"Raw results: {RAW_FILE}")
    print(f"Summary: {SUMMARY_FILE}")

if __name__ == "__main__":
    main()
