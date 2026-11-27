"""Fleet-size comparison under normal and degraded communication (paired seeds)."""
import csv, random, statistics
from pathlib import Path
from warehouse_sim.model import WarehouseModel
from warehouse_sim.experiments.run_experiments import collect_metrics, T_CRITICAL

FLEET_SIZES = [5, 15]
NETWORKS = {"normal": {"latency_ticks": 0, "outage_start": None, "outage_end": None},
           "degraded_latency": {"latency_ticks": 3, "outage_start": None, "outage_end": None}}
ALGORITHMS = ["centralized", "auction"]
SEEDS = [42, 123, 456, 789, 1001]
TICKS = 200
METRICS = ["tasks_completed", "throughput", "pending_tasks", "average_battery", "messages_sent", "messages_delivered", "messages_delayed", "messages_dropped", "messages_in_transit", "messages_held_by_outage", "auctions_started", "auctions_timed_out", "auctions_failed", "assignment_message_retries", "assignment_rejections", "mean_auction_duration_ticks", "auction_duration_observations", "mean_assignment_delay_ticks", "assignment_delay_observations", "mean_assignment_delivery_delay_ticks", "assignment_delivery_delay_observations", "mean_task_wait_to_assignment_ticks", "task_wait_to_assignment_observations"]
OUT = Path(__file__).resolve().parent / "results"
RAW = OUT / "degraded_scalability_raw_results.csv"
SUMMARY = OUT / "degraded_scalability_summary.csv"


def run(network, config, fleet, algorithm, seed):
    random.seed(seed)
    model = WarehouseModel(seed=seed, num_robots=fleet, **config)
    model.fleet_manager.set_allocation_mode(algorithm)
    for _ in range(TICKS):
        model.step()
    row = collect_metrics(model, algorithm, seed, TICKS)
    row.update(network=network, robot_count=fleet)
    return row


def stats(vals):
    n = len(vals); m = statistics.mean(vals) if n else 0
    sd = statistics.stdev(vals) if n > 1 else 0
    margin = T_CRITICAL.get(n-1, 1.96) * sd / n**0.5 if n > 1 else 0
    return n,m,sd,m-margin,m+margin


def summarize(rows):
    summary=[]
    for network in NETWORKS:
      for fleet in FLEET_SIZES:
        for algorithm in ALGORITHMS:
          group=[r for r in rows if r['network']==network and r['robot_count']==fleet and r['algorithm']==algorithm]
          for metric in METRICS:
            n,m,sd,lo,hi=stats([r[metric] for r in group])
            summary.append(dict(network=network,robot_count=fleet,algorithm=algorithm,metric=metric,runs=n,mean=m,std=sd,ci95_lower=lo,ci95_upper=hi))
        for metric in METRICS:
          pairs=[]
          for seed in SEEDS:
            subset={r['algorithm']:r for r in rows if r['network']==network and r['robot_count']==fleet and r['seed']==seed}
            if 'centralized' in subset and 'auction' in subset:
              pairs.append(subset['auction'][metric]-subset['centralized'][metric])
          n,m,sd,lo,hi=stats(pairs)
          summary.append(dict(network=network,robot_count=fleet,algorithm='paired_auction_minus_centralized',metric=metric,runs=n,mean=m,std=sd,ci95_lower=lo,ci95_upper=hi))
    return summary


def write(rows,path):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8') as f:
      w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)


def main():
    results=[]
    total=len(NETWORKS)*len(FLEET_SIZES)*len(ALGORITHMS)*len(SEEDS)
    idx=0
    print(f"Degraded scalability: {total} runs")
    for net,config in NETWORKS.items():
      for fleet in FLEET_SIZES:
       for seed in SEEDS:
        for alg in ALGORITHMS:
          idx+=1; print(f"Run {idx}/{total} | {net} | {fleet} robots | {alg} | seed {seed}")
          results.append(run(net,config,fleet,alg,seed))
    write(results,RAW);write(summarize(results),SUMMARY)
    print(f"Completed. Raw: {RAW}\nSummary: {SUMMARY}")

if __name__=='__main__': main()
