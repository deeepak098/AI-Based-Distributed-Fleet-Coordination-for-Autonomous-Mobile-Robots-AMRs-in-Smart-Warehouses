# Updated Experiment Protocol

## Purpose
Compare centralized task allocation (reference) with message-based auction allocation under communication conditions and fleet-size changes.

## Scenarios
`run_communication_experiments.py` runs five communication conditions for both algorithms using the same five seeds:
- baseline: 0-tick latency, no outage
- latency_1_tick: 1-tick latency
- latency_3_ticks: 3-tick latency
- short_outage: outage from tick 50 through tick 64
- outage_recovery: 1-tick latency, outage from tick 50 through tick 89

`run_degraded_scalability_experiments.py` compares 5 and 15 robots under normal (0 latency) and degraded (3 ticks) communication.

## Paired analysis
For every seed, each metric's difference is calculated as `auction - centralized`. The mean paired difference and a 95% t-confidence interval are reported. Positive/negative signs should be interpreted according to metric direction (e.g., more tasks completed is favorable; more pending tasks is unfavorable).

## Output files
All outputs are separate from prior result files:
- `baseline_network_integrated_raw_results.csv`
- `baseline_network_integrated_summary.csv`
- `baseline_network_integrated_paired_summary.csv`
- `network_integrated_scalability_raw_results.csv`
- `network_integrated_scalability_summary.csv`
- `communication_raw_results.csv`
- `communication_summary.csv` (includes paired rows)
- `degraded_scalability_raw_results.csv`
- `degraded_scalability_summary.csv` (includes paired rows)

## Interpretation caveat
Centralized allocation is a reference policy and is not intended to incur auction messaging overhead. The auction is message-based, but winner selection and assignment commitment remain coordinated by the Fleet Manager; this is not peer-to-peer consensus. Communication counters are network-level totals. They do not by themselves measure assignment delay or auction duration.

## Running
Run commands from the repository root after activating the project's virtual environment:

```bash
python3 -m warehouse_sim.experiments.run_experiments
python3 -m warehouse_sim.experiments.run_scalability_experiments
python3 -m warehouse_sim.experiments.run_communication_experiments
python3 -m warehouse_sim.experiments.run_degraded_scalability_experiments
```

## Audit-fix diagnostic metrics

- `auctions_started`: number of message-based auctions initiated during a run.
- `auctions_timed_out`: auctions whose deadline was reached before all expected bids arrived.
- `auctions_failed`: auctions finalized without a usable winner or with a winner that was no longer available.
- `assignment_message_retries`: assignment-delivery resend attempts after the configured retry interval.
- `mean_auction_duration_ticks`: mean ticks from auction start to auction finalization, for finalized auctions only.
- `mean_assignment_delay_ticks`: mean ticks from task arrival to robot assignment ACK, for ACKed assignments only.
- `mean_assignment_delivery_delay_ticks`: mean ticks from assignment commitment to robot ACK, for ACKed assignments only.
- Observation-count columns accompany averages; a zero average with zero observations means no observations were recorded, not a measured zero delay.

## Reproducible exogenous random streams

Customer demand, inventory initialization, and event-injected order randomness use separate seeded RNG streams. This is intended to keep order traces and initial stock reproducible across allocation algorithms when the same seed is used.

- `mean_task_wait_to_assignment_ticks`: mean task-arrival to allocation-commit time, recorded for assignments committed during the run.

- `assignment_rejections`: robot assignment acknowledgments explicitly rejecting the assignment.
