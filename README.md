# AI-Powered Multi-Agent Warehouse Fleet Coordination

A simulation-based **multi-agent warehouse automation system** where autonomous mobile robots (AMRs) coordinate to fulfill orders, navigate warehouse aisles, avoid collisions, recover from deadlocks, and manage battery charging.

NEXUS creates a digital twin of a smart warehouse to demonstrate how multiple autonomous robots can work together efficiently in a shared environment.

---

## 📌 Overview

Modern warehouses use Autonomous Mobile Robots (AMRs) to transport goods, retrieve items, and fulfill orders. As the number of robots increases, coordination becomes more challenging due to shared paths, congestion, task conflicts, battery limitations, and unexpected disruptions.

NEXUS simulates a warehouse environment where multiple intelligent agents collaborate to manage fulfillment operations while maintaining efficient robot movement and coordination.

The project combines **multi-agent systems, pathfinding algorithms, task allocation, collision avoidance, deadlock recovery, and warehouse simulation**.

---

## ✨ Key Features

- 🤖 **Multi-Agent Architecture** — Multiple autonomous agents work together to manage warehouse operations.
- 📦 **Intelligent Task Allocation** — Assigns order-picking tasks to suitable robots based on distance, workload, availability, battery level, and urgency.
- 🗺️ **A* Pathfinding** — Robots navigate the warehouse grid using heuristic path planning.
- 🚦 **Multi-Robot Conflict Resolution** — Conflict-Based Search (CBS) helps resolve movement conflicts between robots.
- 🔄 **Deadlock Detection & Recovery** — Detects circular waiting conditions and enables recovery strategies.
- 🔋 **Battery & Charging Management** — Robots monitor battery levels and coordinate charging activities.
- ⚡ **Dynamic Event Simulation** — Simulates disruptions such as blocked aisles, robot failures, battery drain, and order surges.
- 📊 **Interactive Dashboard** — Visualizes warehouse activity, robot status, simulation metrics, and agent communication.
- 🧪 **Automated Tests** — Test cases for core algorithms and system behavior.

---

## 🏗️ System Architecture

The system uses a multi-agent architecture in which specialized agents handle different responsibilities.

| Agent | Responsibility |
|---|---|
| Customer Agent | Generates customer orders |
| Order Agent | Manages order processing and fulfillment |
| Inventory Agent | Tracks warehouse inventory |
| Fleet Manager Agent | Assigns tasks to available robots |
| Traffic Controller Agent | Coordinates robot movement and resolves traffic conflicts |
| Robot Agents | Perform navigation, picking, transportation, and delivery tasks |
| Charging Agent | Manages battery-related decisions and charging resources |

### Agent Interaction

The simulation follows a staged agent lifecycle:

**Sense → Decide → Act**

1. **Sense:** Agents observe the current warehouse state and relevant information.
2. **Decide:** Agents determine the next action based on their state, assigned tasks, and constraints.
3. **Act:** Agents execute their decisions within the simulation environment.

---

## 🧠 Algorithms

### 1. Task Allocation

Tasks are assigned to robots using a scoring approach that considers:

- Distance to the assigned task
- Battery availability
- Current workload
- Robot availability
- Order urgency

Unavailable robots, robots already busy, failed robots, and robots with critically low battery levels are excluded from eligible assignments.

### 2. A* Pathfinding

A* is used to find paths through the warehouse grid.

It combines:

- Cost already travelled
- Estimated distance to the destination

The Manhattan distance heuristic is used for grid-based navigation.

### 3. Conflict-Based Search (CBS)

CBS is used for multi-robot path planning to address conflicts between robots, including:

- Vertex conflicts — robots attempting to occupy the same cell
- Edge conflicts — robots attempting conflicting movements across the same edge

### 4. Deadlock Detection

A wait-for graph is used to detect circular waiting relationships between robots.

When a deadlock is detected, the system can select a robot to yield, release its reservations, and replan its path.

### 5. Battery & Charging Management

Robots monitor their battery state and make charging-related decisions. The simulation incorporates charging docks, charging queues, and battery-aware robot behavior.

---

## 🏭 Warehouse Environment

The simulation models a grid-based warehouse containing robots, shelves, packing stations, charging docks, and navigable aisles.

| Component | Configuration |
|---|---|
| Warehouse Grid | 20 × 20 |
| Mobile Robots | 5 |
| Shelves | 10 |
| Packing Stations | 1 |
| Charging Docks | 2 |

The warehouse environment is configurable through the simulation model.

---

## 🖥️ Dashboard

The project includes an interactive Streamlit dashboard for monitoring and interacting with the warehouse digital twin.

Dashboard sections include:

- **Overview** — Simulation metrics and warehouse performance.
- **Live Twin** — Visual representation of the warehouse and robot activity.
- **Architecture** — Overview of system components and agent architecture.
- **Resilience Lab** — Experiment with warehouse disruptions and recovery.
- **Evidence** — View simulation results and experimental evidence.

The dashboard supports starting, pausing, stepping through, and resetting the simulation.

---

## 🧰 Tech Stack

| Technology | Purpose |
|---|---|
| Python | Core simulation logic |
| Mesa | Agent-based modeling and simulation |
| Streamlit | Interactive dashboard |
| Plotly | Interactive visualizations |
| NumPy | Numerical operations |
| NetworkX | Graph-based algorithms and deadlock analysis |
| Pytest | Automated testing |

---

## 📂 Project Structure

```text
.
├── warehouse_sim/
│   ├── agents/
│   │   ├── charging_agent.py
│   │   ├── customer_agent.py
│   │   ├── fleet_manager_agent.py
│   │   ├── inventory_agent.py
│   │   ├── order_agent.py
│   │   ├── robot_agent.py
│   │   └── traffic_controller_agent.py
│   │
│   ├── algorithms/
│   │   ├── astar.py
│   │   ├── cbs.py
│   │   └── task_allocation.py
│   │
│   ├── tests/
│   │   ├── test_astar.py
│   │   ├── test_cbs.py
│   │   ├── test_deadlock_recovery.py
│   │   ├── test_full_shock_cycle.py
│   │   └── test_task_allocation.py
│   │
│   ├── dashboard.py
│   ├── events.py
│   ├── main.py
│   └── model.py
│
├── .gitignore
├── requirements.txt
└── PROJECT_SHOWCASE_GUIDE.md
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or newer
- Git
- pip

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
```

Navigate into the project:

```bash
cd YOUR_REPOSITORY_FOLDER
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
```

### 3. Activate the virtual environment

**macOS / Linux**

```bash
source .venv/bin/activate
```

### 4. Install dependencies

```bash
python -m pip install --upgrade pip
```

```bash
python -m pip install -r requirements.txt
```

### 5. Run the dashboard

```bash
streamlit run warehouse_sim/dashboard.py
```

The dashboard will open in your browser, usually at:

```text
http://localhost:8501
```

---

## ▶️ Running the Simulation from Terminal

Run the simulation for 200 ticks:

```bash
python -m warehouse_sim.main --ticks 200
```

Run the simulation with disruption events enabled:

```bash
python -m warehouse_sim.main --ticks 200 --shock
```

---

## 🧪 Running Tests

Execute the test suite using:

```bash
pytest -q
```

Tests cover areas including:

- A* pathfinding
- Multi-robot conflict resolution
- Task allocation
- Deadlock recovery
- Full disruption scenarios

---

## ⚡ Resilience Scenarios

The simulation supports warehouse disruption scenarios to evaluate robot coordination under changing conditions.

| Scenario | Description |
|---|---|
| 🤖 Robot Failure | Simulates a robot becoming unavailable |
| 🚧 Blocked Aisle | Introduces a blocked warehouse path |
| 🔋 Battery Drain | Simulates unexpected battery loss |
| 📦 Order Surge | Introduces a sudden increase in order demand |
| 🔄 Deadlock | Simulates a controlled robot deadlock condition |

These scenarios can be used to study how a multi-agent warehouse system responds to operational disruptions.

---

## 📈 Performance Metrics

The simulation can be used to study warehouse performance through metrics such as:

- Order throughput
- Order completion time
- Robot travel distance
- Robot utilization
- Waiting time
- Collision count
- Charging activity
- Task completion rate

These metrics can help evaluate different coordination and task-allocation strategies.

---

## 🔮 Future Improvements

Potential directions for extending the project include:

- Decentralized task allocation strategies
- Improved robot-to-robot coordination
- Communication delays and unreliable agent communication
- Comparative benchmarking of task allocation algorithms
- Reinforcement learning for fleet coordination
- Scaling experiments with larger robot fleets
- More advanced congestion-aware routing
- Realistic warehouse layout support
- Predictive battery management

---

## ⚠️ Limitations

- The system is a software simulation and does not control physical robots.
- Robot movement is modeled using a discrete grid.
- Real-world sensor uncertainty and physical dynamics are not fully represented.
- Communication is modeled within a simulated environment.
- Results depend on simulation configurations and assumptions.

This project is intended for academic experimentation and demonstration purposes, not industrial safety certification.

---

## 🎓 Project Purpose

NEXUS serves as a simulation environment for exploring how multi-agent systems can coordinate autonomous robots in warehouse fulfillment operations.

It provides a foundation for experimenting with task allocation, navigation, traffic management, deadlock recovery, and resilience under dynamic conditions.

---

## 👨‍💻 Author

**Deepak**

Academic and experimental project on multi-agent systems, autonomous robot coordination, and smart warehouse automation.

---

*Built for learning, experimentation, and exploring the future of intelligent warehouse automation.*