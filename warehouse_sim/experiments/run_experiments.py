
"""
Warehouse Robot Fleet Allocation Experiment Runner

Compares:
    1. Centralized task allocation
    2. Distributed auction task allocation

Runs paired experiments using identical seeds, collects metrics,
and exports raw results and statistical summaries to CSV.

Run from the project root:

    python -m warehouse_sim.experiments.run_experiments
"""

import csv
import random
import statistics
from pathlib import Path

from warehouse_sim.model import WarehouseModel


# ============================================================
# CONFIGURATION
# ============================================================

ALGORITHMS = ["centralized", "auction"]

SEEDS = [42, 123, 456, 789, 1001]

SIMULATION_TICKS = 200

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RAW_FILE = RESULTS_DIR / "baseline_raw_results.csv"
SUMMARY_FILE = RESULTS_DIR / "baseline_summary.csv"


# 95% confidence interval t-critical values for small samples
T_CRITICAL = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
}


# ============================================================
# KPI HELPER
# ============================================================

def read_kpi(kpis, *keys, default=0):
    """Read a KPI using alternate possible key names."""

    for key in keys:
        if key in kpis and kpis[key] is not None:
            return kpis[key]

    return default


# ============================================================
# COLLECT METRICS
# ============================================================

def collect_metrics(model, algorithm, seed, ticks):

    kpis = model.get_kpis()

    # Read robot battery levels from Fleet Manager telemetry
    robot_registry = model.fleet_manager.robot_registry

    robot_data = list(robot_registry.values())

    batteries = [
        robot.get("battery", 0)
        for robot in robot_data
    ]

    average_battery = (
        statistics.mean(batteries)
        if batteries
        else 0
    )

    # Completed tasks
    tasks_completed = len(
        model.order_agent.completed_tasks
    )

    # Tasks received during the simulation
    tasks_received = getattr(
        model.order_agent,
        "total_orders_received",
        0,
    )

    # Task queues
    pending_tasks = model.order_agent.get_pending_count()

    active_tasks = model.order_agent.get_active_count()

    return {
        "algorithm": algorithm,
        "seed": seed,
        "simulation_ticks": ticks,

        "tasks_completed": tasks_completed,
        "tasks_received": tasks_received,
        "pending_tasks": pending_tasks,
        "active_tasks": active_tasks,

        "throughput": (
            tasks_completed / ticks
            if ticks > 0
            else 0
        ),

        "average_battery": average_battery,

        "robots_charging": read_kpi(
            kpis, "robots_charging"
        ),

        "collision_count": read_kpi(
            kpis, "collision_count", "collision"
        ),

        "deadlocks_resolved": read_kpi(
            kpis, "deadlocks_resolved", "deadlocks"
        ),

        "reroutes": read_kpi(
            kpis, "reroutes"
        ),

        "shocks_triggered": read_kpi(
            kpis, "shocks_triggered"
        ),

        "shock_recovery_successes": read_kpi(
            kpis, "shock_recovery_successes"
        ),

        "shock_recovery_failures": read_kpi(
            kpis, "shock_recovery_failures"
        ),

        "shock_recovery_pending": read_kpi(
            kpis, "shock_recovery_pending"
        ),
    }


# ============================================================
# RUN ONE SIMULATION
# ============================================================

def run_single_experiment(algorithm, seed, ticks):

    # Reset randomness before model construction
    random.seed(seed)

    model = WarehouseModel(seed=seed)

    # Select allocation strategy
    model.fleet_manager.set_allocation_mode(
        algorithm
    )

    # Run simulation
    for _ in range(ticks):
        model.step()

    # Collect metrics
    result = collect_metrics(
        model=model,
        algorithm=algorithm,
        seed=seed,
        ticks=ticks,
    )

    print(
        f"Finished | "
        f"{algorithm:12} | "
        f"Seed: {seed:4} | "
        f"Completed: {result['tasks_completed']:4} | "
        f"Pending: {result['pending_tasks']:4} | "
        f"Battery: {result['average_battery']:.2f}%"
    )

    return result


# ============================================================
# RUN EXPERIMENTS
# ============================================================

def run_all_experiments():

    results = []

    total_runs = len(ALGORITHMS) * len(SEEDS)
    run_number = 0

    print("\n" + "=" * 65)
    print("WAREHOUSE TASK ALLOCATION EXPERIMENT")
    print("=" * 65)

    print(f"Algorithms      : {ALGORITHMS}")
    print(f"Seeds          : {SEEDS}")
    print(f"Ticks per run  : {SIMULATION_TICKS}")
    print(f"Total runs     : {total_runs}")

    print("=" * 65)

    # Same seed is used for both algorithms
    for seed in SEEDS:

        print(f"\n--- Seed {seed} ---")

        for algorithm in ALGORITHMS:

            run_number += 1

            print(
                f"\nRun {run_number}/{total_runs}"
            )

            result = run_single_experiment(
                algorithm=algorithm,
                seed=seed,
                ticks=SIMULATION_TICKS,
            )

            results.append(result)

    return results


# ============================================================
# SUMMARY METRICS
# ============================================================

SUMMARY_METRICS = [
    "tasks_completed",
    "tasks_received",
    "pending_tasks",
    "active_tasks",
    "throughput",
    "average_battery",
    "robots_charging",
    "collision_count",
    "deadlocks_resolved",
    "reroutes",
    "shocks_triggered",
    "shock_recovery_successes",
    "shock_recovery_failures",
    "shock_recovery_pending",
]


# ============================================================
# CALCULATE STATISTICS
# ============================================================

def calculate_summary(results):

    summary = []

    for algorithm in ALGORITHMS:

        algorithm_results = [
            row
            for row in results
            if row["algorithm"] == algorithm
        ]

        for metric in SUMMARY_METRICS:

            values = [
                row[metric]
                for row in algorithm_results
            ]

            n = len(values)

            if n == 0:
                mean = 0
                std = 0
                ci_lower = 0
                ci_upper = 0

            else:

                mean = statistics.mean(values)

                std = (
                    statistics.stdev(values)
                    if n > 1
                    else 0
                )

                if n > 1:

                    df = n - 1

                    t_value = T_CRITICAL.get(
                        df, 1.96
                    )

                    margin = (
                        t_value * std / (n ** 0.5)
                    )

                else:
                    margin = 0

                ci_lower = mean - margin
                ci_upper = mean + margin

            summary.append({
                "algorithm": algorithm,
                "metric": metric,
                "runs": n,
                "mean": mean,
                "std": std,
                "ci95_lower": ci_lower,
                "ci95_upper": ci_upper,
            })

    return summary


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(data, filepath):

    if not data:
        print(f"No data to save: {filepath}")
        return

    with open(
        filepath,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=data[0].keys(),
        )

        writer.writeheader()
        writer.writerows(data)

    print(f"Saved: {filepath}")


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary(summary):

    display_metrics = [
        "tasks_completed",
        "throughput",
        "pending_tasks",
        "average_battery",
        "collision_count",
        "deadlocks_resolved",
        "reroutes",
    ]

    print("\n" + "=" * 65)
    print("RESULT SUMMARY")
    print("=" * 65)

    for metric in display_metrics:

        print(f"\n{metric.upper()}")
        print("-" * 55)

        for algorithm in ALGORITHMS:

            row = next(
                (
                    item for item in summary
                    if item["algorithm"] == algorithm
                    and item["metric"] == metric
                ),
                None,
            )

            if row is None:
                continue

            print(
                f"{algorithm:12} | "
                f"Mean = {row['mean']:.3f} | "
                f"Std = {row['std']:.3f} | "
                f"95% CI = "
                f"[{row['ci95_lower']:.3f}, "
                f"{row['ci95_upper']:.3f}]"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\nStarting baseline experiments...\n")

    # 1. Run all simulations
    results = run_all_experiments()

    # 2. Calculate summary statistics
    summary = calculate_summary(results)

    # 3. Export raw results
    save_csv(
        results,
        RAW_FILE,
    )

    # 4. Export summary statistics
    save_csv(
        summary,
        SUMMARY_FILE,
    )

    # 5. Display results
    print_summary(summary)

    print("\n" + "=" * 65)
    print("EXPERIMENTS FINISHED")
    print("=" * 65)

    print(f"Total runs: {len(results)}")
    print(f"\nRaw data : {RAW_FILE}")
    print(f"Summary  : {SUMMARY_FILE}")

    print("\n")


if __name__ == "__main__":
    main()
