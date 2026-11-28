# NEXUS: Autonomous Warehouse Digital Twin

## Complete Project Report, User Guide, Case-Study Analysis, and Presentation Handbook

**Project type:** Multi-agent artificial intelligence and digital-twin simulation  
**Institution:** Amrita School of Computing, Coimbatore  
**Application:** Autonomous warehouse order fulfilment  
**Technology:** Python, Mesa, Streamlit, Plotly, NumPy, NetworkX  

---

## 1. Executive Summary

NEXUS is an autonomous warehouse simulation in which several specialized software agents cooperate to fulfil customer orders. The simulation represents a 20 × 20 warehouse containing shelves, a packing station, charging docks, blocked cells, and five mobile robots.

The system is more than a robot animation. It is a **digital twin**: the user interface reflects the current state of the simulation model, including robot locations, batteries, order queues, completed work, environmental disruptions, and messages exchanged between agents. Each simulation tick follows a transparent **sense → decide → act** cycle.

The main research question is:

> How can multiple intelligent agents coordinate task allocation, navigation, inventory, charging, and failure recovery in a shared warehouse environment?

The project demonstrates:

- cooperation between seven agent roles;
- battery-aware and workload-aware task allocation;
- A-star pathfinding for efficient routes;
- Conflict-Based Search (CBS) for multi-robot conflict resolution;
- wait-for graph analysis for deadlock detection;
- autonomous responses to five environmental shocks;
- a live, explainable dashboard for observation and experimentation; and
- automated verification of algorithms and full simulation scenarios.

At the time this report was prepared, the complete test suite contained **55 passing tests**. The stability tests include 100- and 200-tick simulations, rapid shock succession, multiple blocked cells, and the failure of all robots. The tested scenarios maintain a collision count of zero.

---

## 2. Problem Statement

Modern warehouses must process many orders while robots share narrow aisles, chargers, shelves, and packing facilities. A simple centralized script becomes difficult to maintain because decisions are interconnected:

- a customer order changes the task queue;
- the task requires available inventory;
- inventory selection creates a destination;
- a robot must be selected using its position, battery, and workload;
- the selected route may conflict with another robot;
- a low battery may require task handoff and charging; and
- failures or blocked aisles require immediate replanning.

The project addresses this coordination problem using a multi-agent system. Each agent has a focused responsibility and communicates relevant decisions to other agents. This division makes behavior easier to reason about, test, and extend.

---

## 3. Objectives

### Primary objectives

1. Model an autonomous warehouse using cooperating intelligent agents.
2. Fulfil normal and urgent customer orders from shelf to packing station.
3. Allocate tasks to suitable robots instead of using random assignment.
4. Plan efficient routes while avoiding robot conflicts.
5. Manage battery charging without manually stopping the simulation.
6. Recover from failures, obstacles, congestion, and deadlocks.
7. expose internal decisions through a live digital-twin dashboard.
8. Verify important behavior with repeatable automated tests.

### Success criteria

- The simulation does not crash during normal and stress operation.
- Robots reach valid destinations without entering blocked cells.
- Multi-robot plans resolve vertex and edge conflicts.
- Low-battery, busy, charging, or failed robots are not incorrectly assigned.
- Orders and agent messages remain observable.
- Demonstration shocks produce understandable recovery behavior.
- Collision count remains zero in the tested scenarios.

---

## 4. Scope

### Included

- A discrete 20 × 20 grid warehouse.
- Five autonomous robot agents.
- Ten shelf locations, one packing station, and two charging docks.
- Normal and urgent order priorities.
- Inventory reservations and stock updates.
- Scored task allocation.
- A-star and CBS route planning.
- Battery consumption and charging queues.
- Five interactive disruption scenarios.
- KPI collection, robot telemetry, and message logging.
- Command-line and Streamlit interfaces.
- Unit and integration tests.

### Not included

- Control of physical robots or industrial machinery.
- Continuous physics, acceleration, turning radius, or real sensor noise.
- Human workers moving within the grid.
- Economic optimization using real warehouse cost data.
- Authentication, cloud deployment, or a production database.
- A formal guarantee that simulation performance will match a real warehouse.

This is an academic digital-twin prototype. It demonstrates concepts and algorithms safely before physical deployment.

---

## 5. System Architecture

The `WarehouseModel` is the single source of truth. It stores the grid, agents, robots, blocked cells, simulation clock, messages, and collected metrics.

```text
Customer Agent
      │ creates demand
      ▼
Order Agent ──► Inventory Agent
      │              │ validates/reserves stock
      └──────────────▼
                Fleet Manager
                      │ selects robot
          ┌───────────┼───────────┐
          ▼           ▼           ▼
     Robot Agents  Traffic     Charging
       (five)      Controller    Agent
          │        A-star/CBS       │
          └───────────┬─────────────┘
                      ▼
               WarehouseModel
          state, KPIs, event and message logs
                      │
                      ▼
              Streamlit Digital Twin
```

### Tick lifecycle

Every simulation tick has three stages:

1. **Sense:** agents observe orders, telemetry, paths, batteries, and environmental state.
2. **Decide:** agents prioritize work, choose robots, plan paths, or identify charging/deadlock actions.
3. **Act:** agents place orders, assign tasks, move robots, pick/drop goods, charge, and log messages.

Staged execution reduces dependence on arbitrary code order and makes the simulation easier to explain.

---

## 6. Agent Responsibilities and PEAS Summary

PEAS means **Performance measure, Environment, Actuators, and Sensors**. It is a standard method for describing an intelligent agent.

| Agent | Main responsibility | Important observations | Important actions | Performance concern |
|---|---|---|---|---|
| Customer | Generate realistic demand | Queue state and delivery feedback | Place normal or urgent orders | Sustainable order flow |
| Order | Control order/task lifecycle | Incoming orders and completion messages | Prioritize and create tasks | No lost orders; urgent work first |
| Inventory | Maintain stock truth | Shelf quantities and reservations | Reserve, release, decrement stock | Stock correctness |
| Fleet Manager | Select and manage robots | Position, battery, status, workload | Assign, reassign, complete tasks | Good utilization and safe assignment |
| Traffic Controller | Coordinate shared motion | Positions, paths, reservations, obstacles | Route, reroute, hold, resolve conflicts | Zero collisions and deadlocks |
| Robot (×5) | Execute physical workflow | Route, task, battery, local state | Move, pick, drop, dock | Safe and timely completion |
| Charging | Protect fleet energy | Battery levels and dock occupancy | Queue, allocate dock, release | Avoid battery exhaustion |

The agents are cooperative, but they compete for shared resources such as aisle cells, chargers, shelves, and the packing station.

---

## 7. Complete Order-Fulfilment Flow

1. The Customer Agent generates an order containing SKU, quantity, and priority.
2. The Order Agent receives it and creates a fulfilment task.
3. The Inventory Agent finds a shelf containing the SKU and checks quantity.
4. The Fleet Manager evaluates available robots.
5. A scored allocation function considers distance, battery, workload, and urgency.
6. The chosen shelf is reserved to prevent inconsistent allocation.
7. The Traffic Controller requests an A-star route from robot to shelf.
8. If the route conflicts with existing reservations, CBS plans compatible paths.
9. The Robot Agent travels to the shelf and performs the picking state.
10. A second route is planned to the packing station.
11. The robot delivers the item and reports task completion.
12. Inventory is decremented, reservations are released, and KPIs/messages update.
13. The robot becomes available or travels to charge if its battery is low.

This chain demonstrates cross-agent causality: a customer decision ultimately changes inventory, robot state, traffic reservations, battery usage, messages, and dashboard metrics.

---

## 8. Algorithms Studied

### 8.1 A-star pathfinding

A-star finds a route through the grid using actual path cost plus a Manhattan-distance estimate to the goal. Manhattan distance is appropriate because robots move through the four cardinal grid directions.

What was studied:

- admissible heuristics;
- open and closed search sets;
- obstacles and unreachable goals;
- optimal path length in a discrete grid; and
- time-expanded constraints used by CBS.

### 8.2 Conflict-Based Search

Independently optimal paths can still collide. CBS searches a constraint tree:

1. plan an initial path for each robot;
2. detect the first vertex or edge conflict;
3. branch by constraining one conflicting robot in each child;
4. replan only the constrained robot; and
5. continue until the joint solution is conflict-free.

The project tests both vertex conflicts—robots occupying the same cell at the same time—and edge conflicts—robots swapping positions head-on.

### 8.3 Scored task allocation

Robot selection combines several factors rather than using round-robin assignment:

- travel distance to the shelf;
- remaining battery;
- current workload;
- availability status; and
- urgent-task priority.

Robots with insufficient battery or unsuitable status are excluded. The tests confirm that closer, higher-battery, lower-workload robots receive better scores.

### 8.4 Deadlock detection

A wait-for graph represents which robot is waiting for another. Depth-first search detects cycles. When a cycle exists, a lower-priority robot yields, clears its reservation, and replans.

### 8.5 Finite-state robot control

Robot behavior is represented through explicit states such as idle, travelling to shelf, picking, travelling to packing, dropping, returning, needing charge, charging, and failed. State machines make transitions observable and prevent contradictory behavior.

---

## 9. User Interface Navigation Guide

### Starting the application

From the project directory:

```powershell
python -m pip install -r warehouse_sim\requirements.txt
streamlit run warehouse_sim\dashboard.py
```

Open `http://localhost:8501` in a browser. The interface intentionally reveals content using slow, staggered animations. Users who enable reduced motion in their operating system will receive an accessible non-animated version.

### Persistent left control room

The sidebar remains available on every page.

| Control | Purpose |
|---|---|
| Presentation menu | Navigate between the five project sections |
| Run | Continuously advance the simulation |
| Pause | Freeze the digital twin for explanation or shock injection |
| Simulation pace | Select 1–5 ticks per visual refresh |
| Step one tick | Advance exactly one sense–decide–act cycle |
| Reset demo | Create a clean seeded model and clear history |
| Status indicator | Shows RUNNING/PAUSED and current tick |

For teaching, use **Step one tick** to explain causality slowly. For demonstration, use **Run** at pace 1 or 2 so robot motion and metrics remain easy to follow.

### Page 1: Overview

Purpose: introduce the problem and main idea before showing technical details.

What the audience sees:

- project thesis and scope;
- grid, robot, agent, and resilience counts;
- the five-stage demand-to-fulfilment flow;
- adaptive allocation, conflict-free motion, and recovery capabilities.

What to say:

> “This project studies how specialized AI agents can collaborate inside a shared warehouse. The dashboard is connected to the live model, so every metric and position reflects actual simulation state.”

### Page 2: Live Twin

Purpose: observe the system operating.

Top metrics:

- **Tick:** current simulation time;
- **Completed:** fulfilled tasks;
- **Pending:** work waiting for a robot;
- **Active robots:** robots currently performing work;
- **Avg battery:** mean battery percentage across the fleet;
- **Collisions:** conflicts that became actual collisions.

Spatial grid legend:

- shelf cells store inventory;
- the packing cell receives completed picks;
- charging docks restore robot batteries;
- blocked cells are inaccessible;
- labelled circles are robots.

Robot marker colors communicate state: idle, active, charging, low battery, or failed. Hover over a robot for its ID, state, and battery.

The operational trend plots completed and pending tasks over time. The communication panel shows which agent sent a message, its recipient, the tick, and the action. This is evidence that responsibilities are coordinated explicitly.

Recommended demonstration:

1. Set pace to 1.
2. Click Run.
3. Watch orders appear and robot paths change.
4. Point out agent messages as allocation and routing occur.
5. Pause after 15–25 ticks and explain the KPI values.

### Page 3: Architecture

Purpose: explain how the solution works internally.

This page presents the seven agent roles, the sense–decide–act lifecycle, and the decision stack. Expand **Algorithms used** to explain A-star, CBS, scored allocation, and wait-for graphs.

Important distinction:

> A-star answers “How can one robot reach a goal efficiently?” CBS answers “How can multiple robots follow paths without temporal conflicts?”

### Page 4: Resilience Lab

Purpose: create controlled failures and observe autonomous response.

Best practice: run the warehouse first, pause it, inject one scenario, discuss the immediate result, and then resume.

| Scenario | User action | Expected system response |
|---|---|---|
| Robot failure | Select and disable a robot | Clear its reservations and requeue unfinished work |
| Blocked aisle | Choose a valid empty cell | Identify affected paths and reroute robots |
| Battery drain | Select a robot | Set battery to 5% and route it toward charging behavior |
| Urgent order surge | Choose number of orders | Add high-priority demand and stress allocation |
| Controlled deadlock | Click injection button | Create a conflict and invoke detection/replanning |

Some invalid requests are intentionally rejected—for example, blocking a shelf, packing station, or charging dock. This preserves model invariants.

The recovery history table records result data for every attempted scenario.

### Page 5: Evidence

Purpose: finish the presentation with measurable verification.

This page displays current simulation ticks, collision count, deadlocks resolved, and shocks recovered. It also summarizes the automated test areas and shows commands for reproduction.

Never claim that attractive animation proves algorithm correctness. Use the automated tests and displayed invariants as the evidence.

---

## 10. Environmental Shock Analysis

### Robot failure

The selected robot enters FAILED state, its active route reservations are cleared, and the Fleet Manager requeues unfinished work. This studies fault tolerance and graceful degradation.

### Blocked aisle

The cell becomes an obstacle. Active routes containing it are identified and recalculated. This represents spills, temporary obstructions, or unsafe areas.

### Battery failure

Battery drops to 5%, the robot enters a charging-needed state, and charging/task-handoff logic can respond. This studies energy-aware autonomy.

### Urgent order flood

Multiple urgent orders arrive simultaneously. This studies backlog growth, prioritization, fleet utilization, and congestion response.

### Deadlock injection

Two suitable robots are placed in a controlled conflict. The system uses routing and wait-for logic to avoid permanent standstill.

---

## 11. Verification and Results

Run the full suite from `warehouse_sim`:

```powershell
pytest -q
```

### Verified result at document preparation time

```text
55 passed
```

### What is covered

- A-star direct paths, obstacles, constraints, unreachable goals, and optimal length;
- CBS conflict detection, vertex conflicts, edge conflicts, multi-robot cases, and invalid configurations;
- task-allocation distance, battery, workload, urgency, and exclusion rules;
- deadlock cycle detection and yield selection;
- 100 ticks with all five shocks;
- 200 ticks without crashes;
- rapid shock succession;
- all robots failed without a simulation crash; and
- multiple blocked cells.

### Verified claims

- All 55 existing automated tests pass.
- The 200-tick stability test completes.
- The full-shock integration test completes.
- Collision count remains zero in the tested integration scenarios.
- Model grid and message state remain accessible after stress testing.

### Claims that require future experiments

Exact percentages for speed, throughput improvement, node reduction, energy savings, or superiority over round-robin allocation are **not established by the current test suite**. These should only be claimed after controlled baseline experiments with repeated random seeds and statistical reporting.

---

## 12. What We Studied and Learned

### Artificial intelligence concepts

- rational agents and PEAS formulation;
- multi-agent cooperation and resource contention;
- heuristic search and admissibility;
- constraint-based multi-agent pathfinding;
- task-allocation heuristics;
- finite-state machines;
- deadlock graphs and cycle detection;
- reactive recovery and replanning; and
- explainable decision traces.

### Software-engineering concepts

- separation of responsibilities;
- staged model execution;
- single source of truth;
- event logging and telemetry;
- interactive visualization;
- deterministic seeded demonstrations;
- unit versus integration testing;
- graceful handling of invalid user actions; and
- dependency management.

### Operational insights

- Local optimization is not sufficient when robots share space.
- Battery must influence scheduling before it becomes an emergency.
- Reservations reduce collisions but can create waiting dependencies.
- Resilience must be designed as part of normal operation.
- A digital twin is valuable when it explains internal decisions, not only physical positions.

---

## 13. Usefulness to Human Society

### Worker safety

Unsafe routes, congested aisles, and failure policies can be studied in simulation before exposing employees or physical equipment to risk. In a real deployment, robots could take over repetitive long-distance movement and heavy transport while humans supervise, handle exceptions, and perform tasks requiring judgment and dexterity.

### Reliable access to goods

More resilient fulfilment systems can support timely distribution of food, medicine, emergency supplies, and essential products. Failure recovery is especially relevant during high-demand periods or disruptions.

### Energy and resource efficiency

Battery-aware allocation and route planning can reduce unnecessary travel and charging emergencies. Better utilization may reduce wasted energy and avoid over-provisioning equipment, although real savings require physical-world measurement.

### Education and workforce development

The project makes abstract AI concepts visible. Students can observe how one order changes several agents, how a route conflict is resolved, and why verification is necessary. It supports training in AI, robotics, operations research, and software engineering.

### Safer innovation through digital twins

Organizations can test “what-if” situations digitally before modifying a physical warehouse. This can reduce experimentation cost, equipment damage, and service interruptions.

### Human-centered deployment requirements

Automation should augment human work, not ignore workers. A responsible real deployment should include:

- worker consultation and reskilling;
- safe physical separation and emergency stops;
- transparent responsibility when automation fails;
- privacy limits for employee and operational data;
- accessibility for control-room users;
- cybersecurity and audit trails; and
- human authority to override unsafe decisions.

The simulation supports decision-making; it does not replace safety engineering or human accountability.

---

## 14. Ethical, Safety, and Sustainability Considerations

1. **Employment impact:** automation can displace some tasks; deployment should include role redesign and training.
2. **Bias in prioritization:** urgent-order rules must be defined fairly and transparently.
3. **Surveillance:** telemetry should track equipment needs, not become unjustified worker monitoring.
4. **Safety assurance:** simulation results are not sufficient for physical certification.
5. **Cybersecurity:** compromised routing or control systems could cause physical harm.
6. **Environmental impact:** efficiency benefits must be compared with robot manufacturing, battery, and computing costs.
7. **Accountability:** a named human organization must remain responsible for operational outcomes.

---

## 15. Limitations

- Discrete grid movement simplifies real robot dynamics.
- Orders, failures, and inventory are simulated rather than drawn from real data.
- Communication is assumed to be reliable and low-latency.
- Sensor uncertainty and localization error are not modelled.
- The packing station is simplified.
- No human–robot interaction is represented.
- CBS performance may become expensive with many robots and dense conflicts.
- The dashboard is designed for demonstration, not production security.
- Current tests establish functional correctness for defined scenarios, not industrial certification.

---

## 16. Future Enhancements

- Import a real warehouse floor plan.
- Add human workers and safety zones.
- Model robot speed, turning, payload, and sensor noise.
- Add reinforcement learning or market-based task allocation for comparison.
- Benchmark round-robin, greedy, and scored allocation across repeated seeds.
- Measure throughput, latency, route length, energy, charger utilization, and fairness.
- Add predictive maintenance from simulated telemetry.
- Store experiment runs in a database and export reports.
- Add authentication and role-based controls.
- Connect to ROS, physical robots, or IoT devices in a controlled laboratory.
- Add accessibility testing and multilingual explanations.
- Run larger experiments to study CBS scalability.

---

## 17. Suggested Experimental Methodology

To turn the prototype into a stronger research study:

1. Define baselines: random, round-robin, nearest-robot, and current scored allocation.
2. Use identical order streams and shocks for every policy.
3. Run at least 30 random seeds per experimental condition.
4. Measure completed orders, mean fulfilment time, path length, battery usage, waiting time, reroutes, and collisions.
5. Vary robot count, order rate, aisle density, dock count, and shock frequency.
6. Report mean, standard deviation, confidence intervals, and failure cases.
7. Separate observed results from interpretations.

This methodology would support defensible quantitative claims.

---

## 18. Project Structure

```text
warehouse_sim/
├── dashboard.py                 Professor-facing digital twin UI
├── main.py                      Command-line simulation
├── model.py                     WarehouseModel and KPI/state APIs
├── events.py                    Five controlled environmental shocks
├── requirements.txt             Python dependencies
├── simulation_log.jsonl         Runtime communication log
├── agents/
│   ├── customer_agent.py
│   ├── order_agent.py
│   ├── inventory_agent.py
│   ├── fleet_manager_agent.py
│   ├── traffic_controller_agent.py
│   ├── robot_agent.py
│   └── charging_agent.py
├── algorithms/
│   ├── astar.py
│   ├── cbs.py
│   └── task_allocation.py
└── tests/
    ├── test_astar.py
    ├── test_cbs.py
    ├── test_task_allocation.py
    ├── test_deadlock_recovery.py
    └── test_full_shock_cycle.py
```

---

## 19. Installation and Troubleshooting

### Recommended setup

```powershell
cd C:\Users\BhaviChasvi\Downloads\foai_case_study
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r warehouse_sim\requirements.txt
streamlit run warehouse_sim\dashboard.py
```

### Common issues

| Problem | Solution |
|---|---|
| Browser does not open | Manually visit `http://localhost:8501` |
| Port already in use | Run with `--server.port 8502` |
| Imports fail | Start Streamlit from the project root using the command above |
| UI appears frozen | Check whether status says PAUSED; click Run or Step one tick |
| Shock returns an error | Select a valid robot or an empty blockable cell |
| Need a clean presentation | Click Reset demo before beginning |

---

## 20. Professor Presentation Script

### Two-minute version

1. **Overview:** “NEXUS is a multi-agent digital twin for warehouse fulfilment.”
2. Explain the customer-to-packing flow and seven roles.
3. **Live Twin:** run at pace 1 and show grid, KPI changes, and messages.
4. **Resilience Lab:** pause and block an aisle or fail a robot.
5. Resume and show recovery information.
6. **Evidence:** show zero collisions and the 55-test result.

### Eight-minute version

1. **Problem (45 seconds):** shared aisles, energy, inventory, and disruptions make coordination difficult.
2. **Architecture (90 seconds):** explain agents and sense–decide–act.
3. **Algorithms (90 seconds):** distinguish A-star, CBS, task scoring, and deadlock detection.
4. **Normal operation (90 seconds):** run Live Twin and trace one order through messages.
5. **Stress demonstration (90 seconds):** inject a failure and describe responsibility transfer.
6. **Verification (45 seconds):** present tests and verified claims.
7. **Societal value and limitations (50 seconds):** safety, reliability, education, and responsible deployment.

### Suggested viva questions

**Why use multiple agents?**  
Because order handling, inventory, routing, fleet allocation, robot execution, and charging have different observations and responsibilities. Modular agents improve separation, explainability, and extensibility.

**Why is A-star alone insufficient?**  
A-star can find a valid path for one robot but does not automatically prevent time-dependent conflicts between several independently planned paths.

**Why use CBS?**  
CBS resolves vertex and edge conflicts using constraints while preserving efficient per-agent search.

**What is a digital twin here?**  
The dashboard is a live visual representation of model state and behavior, including positions, batteries, tasks, KPIs, events, and communication.

**How is deadlock different from collision?**  
A collision is simultaneous unsafe occupancy or movement; a deadlock is a waiting cycle in which agents cannot progress even without colliding.

**Is this ready for a physical warehouse?**  
No. It is an academic prototype. Physical deployment needs sensor models, real-time guarantees, safety certification, cybersecurity, and hardware integration.

**How do you prove correctness?**  
Focused unit tests validate algorithms, while integration tests run long and disruptive simulations. The current suite has 55 passing tests, but industrial assurance would require more formal and physical testing.

---

## 21. Conclusion

NEXUS demonstrates how multi-agent AI can coordinate a complex operational workflow while remaining observable and testable. The most important achievement is not only that robots move: orders, inventory, allocation, traffic, charging, and recovery are represented as connected responsibilities with visible causal effects.

The case study shows that resilient automation requires three qualities together:

1. **intelligence** to choose and plan;
2. **coordination** to share limited resources safely; and
3. **explainability and verification** so humans can understand and trust system behavior.

Used responsibly, ideas from this project can contribute to safer work, more reliable supply chains, efficient resource use, and practical AI education. Human oversight, ethics, and physical safety engineering must remain central to any real-world extension.

---


---

**Document note:** Test counts and behavior statements describe the project state at the time this guide was generated. Re-run `pytest -q` before a final submission and update the result if the implementation changes.
