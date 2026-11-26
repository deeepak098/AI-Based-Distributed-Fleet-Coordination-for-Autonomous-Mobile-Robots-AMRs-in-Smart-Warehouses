"""
Warehouse Simulation Engine — Mesa Model orchestrating all agents.

Owner: Rohith (cb.sc.u4cse23018) & Kalyan (cb.sc.u4cse23060)
Responsibility: Holds the 20x20 MultiGrid, instantiates all agent types,
runs the staged scheduler (sense → decide → act), collects metrics via
DataCollector, and logs inter-agent messages to simulation_log.jsonl.


The model is the single source of truth for the warehouse state and is
callable from both the CLI (main.py) and the Streamlit dashboard.
"""

from __future__ import annotations



import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple


import mesa
import numpy as np


from .agents.charging_agent import ChargingAgent
from .agents.customer_agent import CustomerAgent
from .agents.fleet_manager_agent import FleetManagerAgent
from .agents.inventory_agent import InventoryAgent
from .agents.order_agent import OrderAgent
from .agents.robot_agent import RobotAgent
from .agents.traffic_controller_agent import TrafficControllerAgent



# ── Grid Layout Constants ─────────────────────────────────────────────
GRID_WIDTH = 20
GRID_HEIGHT = 20
NUM_ROBOTS = 5



# Shelf locations — distributed across the grid in two "aisles"
SHELF_LOCATIONS: List[Tuple[int, int]] = [
    (3, 4), (3, 8), (3, 12), (3, 16),
    (8, 4), (8, 8), (8, 12), (8, 16),
    (13, 4), (13, 8),
]



# Packing station — bottom-right area
PACKING_STATION: Tuple[int, int] = (17, 2)



# Charging docks — near entrance
CHARGING_DOCKS: List[Tuple[int, int]] = [(1, 1), (1, 18)]



# Robot starting positions — near the entrance
ROBOT_START_POSITIONS: List[Tuple[int, int]] = [
    (0, 0), (0, 5), (0, 10), (0, 15), (0, 19),
]



class WarehouseModel(mesa.Model):
    """
    Mesa Model orchestrating the full warehouse fulfillment simulation.



    Grid encodes: shelves (fixed), aisles (walkable), packing station (fixed),
    charging docks (fixed), and currently-blocked cells (mutable for shocks).
    Uses staged execution: sense → decide → act per tick.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        """Initialize the warehouse model with all agents and grid layout."""
        super().__init__()



        self.grid_width = GRID_WIDTH
        self.grid_height = GRID_HEIGHT
        self.grid = mesa.space.MultiGrid(GRID_WIDTH, GRID_HEIGHT, torus=False)



        self.current_tick: int = 0
        self.blocked_cells: set = set()
        self.shelf_locations = list(SHELF_LOCATIONS)
        self.packing_station = PACKING_STATION
        self.charging_docks = list(CHARGING_DOCKS)
        self.message_log: List[Dict[str, Any]] = []

        # Environmental shock tracking
        self.shocks_triggered: int = 0
        self.shock_recovery_successes: int = 0
        self.shock_recovery_failures: int = 0
        self.shock_recovery_pending: int = 0

        # Keep legacy counter temporarily for backward compatibility
        self.shocks_recovered: int = 0

        # Store individual shock records for recovery tracking
        self.shock_records: List[Dict[str, Any]] = []
        self._log_file_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "simulation_log.jsonl"
        )



        # Clear log file on init
        with open(self._log_file_path, "w") as f:
            pass



        # ── Instantiate singleton agents ──────────────────────────────
        self.order_agent = OrderAgent(self)
        self.inventory_agent = InventoryAgent(self, self.shelf_locations)
        self.fleet_manager = FleetManagerAgent(self)
        self.traffic_controller = TrafficControllerAgent(self)
        self.charging_agent = ChargingAgent(self, self.charging_docks)
        self.customer_agent = CustomerAgent(self)



        # ── Instantiate robot agents ──────────────────────────────────
        self.robots: Dict[int, RobotAgent] = {}
        for i in range(NUM_ROBOTS):
            start_pos = ROBOT_START_POSITIONS[i % len(ROBOT_START_POSITIONS)]
            robot = RobotAgent(self, robot_id=i, start_pos=start_pos)
            self.robots[i] = robot
            self.fleet_manager.register_robot(i, start_pos)
            self.grid.place_agent(robot, start_pos)



        # ── Data Collector ────────────────────────────────────────────
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Orders_Completed": lambda m: len(m.order_agent.completed_tasks),
                "Pending_Tasks": lambda m: m.order_agent.get_pending_count(),
                "Active_Tasks": lambda m: m.order_agent.get_active_count(),
                "Avg_Battery": lambda m: np.mean(
                    [r.battery for r in m.robots.values()]
                ) if m.robots else 0,
                "Robots_Charging": lambda m: m.charging_agent.get_charging_count(),
                "Robots_Active": lambda m: sum(
                    1 for r in m.robots.values() if r.status not in ("IDLE", "FAILED", "CHARGING")
                ),
                "Collision_Count": lambda m: m.traffic_controller.collision_count,
                "Deadlocks_Resolved": lambda m: m.traffic_controller.deadlocks_resolved,
                "Shocks_Triggered": lambda m: m.shocks_triggered,
                "Shock_Recovery_Successes": lambda m: m.shock_recovery_successes,
                "Shock_Recovery_Failures": lambda m: m.shock_recovery_failures,
                "Shock_Recovery_Pending": lambda m: m.shock_recovery_pending,
                "Reroutes": lambda m: m.traffic_controller.reroutes_performed,
            }
        )

    def step(self) -> None:
        """
        Advance the simulation by one tick using staged execution.



        Stage 1 — SENSE: All agents observe the environment.
        Stage 2 — DECIDE: All agents make decisions.
        Stage 3 — ACT: All agents execute their actions.
        """
        self.current_tick += 1



        # ── Stage 1: SENSE ────────────────────────────────────────────
        self.customer_agent.sense()
        self.order_agent.sense()
        self.traffic_controller.sense()
        self.charging_agent.sense()
        self.fleet_manager.sense()
        for robot in self.robots.values():
            if robot.status != "FAILED":
                robot.sense()



        # ── Stage 2: DECIDE ───────────────────────────────────────────
        self.customer_agent.decide()
        self.order_agent.decide()
        self.traffic_controller.decide()
        self.charging_agent.decide()
        self.fleet_manager.decide()
        for robot in self.robots.values():
            if robot.status != "FAILED":
                robot.decide()



        # ── Stage 3: ACT ──────────────────────────────────────────────
        self.customer_agent.act()
        self.order_agent.act()
        self.charging_agent.act()
        self.fleet_manager.act()
        for robot in self.robots.values():
            if robot.status != "FAILED":
                robot.act()
        self.traffic_controller.act()

        # Monitor asynchronous shock recovery after agents act.
        # Import locally to avoid a circular import with events.py.
        from .events import monitor_shock_recoveries
        monitor_shock_recoveries(self)

        # ── Collect data ──────────────────────────────────────────────
        self.datacollector.collect(self)



    def log_message(
        self, from_agent: str, to_agent: str, payload: Dict[str, Any]
    ) -> None:
        """
        Log an inter-agent message to both in-memory log and JSONL file.



        Args:
            from_agent: Name of the sending agent.
            to_agent: Name of the receiving agent.
            payload: Message content dictionary.
        """
        entry = {
            "tick": self.current_tick,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "payload": _serialize_payload(payload),
        }
        self.message_log.append(entry)



        # Append to JSONL file
        try:
            with open(self._log_file_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Don't crash simulation on log failure



    def get_robot_by_id(self, robot_id: int) -> Optional[RobotAgent]:
        """Look up a robot by its ID."""
        return self.robots.get(robot_id)



    def get_robots_at(self, pos: Tuple[int, int]) -> List[RobotAgent]:
        """Get all robots at a specific grid position."""
        return [r for r in self.robots.values() if r.pos_tuple == pos]



    def get_grid_state(self) -> Dict[str, Any]:
        """Return the full grid state for dashboard visualization."""
        robot_positions = {
            rid: {"pos": r.pos_tuple, "status": r.status, "battery": r.battery}
            for rid, r in self.robots.items()
        }



        shelf_states = {}
        for loc, state in self.inventory_agent.shelf_state.items():
            total_qty = sum(state["skus"].values())
            shelf_states[str(loc)] = {
                "reserved": state["reserved"],
                "total_qty": total_qty,
            }



        return {
            "tick": self.current_tick,
            "grid_width": self.grid_width,
            "grid_height": self.grid_height,
            "robots": robot_positions,
            "shelves": shelf_states,
            "shelf_locations": self.shelf_locations,
            "packing_station": self.packing_station,
            "charging_docks": self.charging_docks,
            "blocked_cells": list(self.blocked_cells),
        }



    def register_shock(self, shock_type: str, details: Optional[Dict[str, Any]] = None) -> int:
        """Register a new shock and mark its recovery as pending."""
        shock_id = len(self.shock_records)
        record = {
            "shock_id": shock_id,
            "shock_type": shock_type,
            "tick": self.current_tick,
            "status": "PENDING",
            "details": details or {},
        }
        self.shock_records.append(record)
        self.shocks_triggered += 1
        self.shock_recovery_pending += 1
        return shock_id


    def update_shock_status(self, shock_id: int, status: str) -> bool:
        """Update a shock's recovery status exactly once."""
        if status not in ("RECOVERED", "FAILED"):
            raise ValueError("Status must be RECOVERED or FAILED")

        for record in self.shock_records:
            if record["shock_id"] == shock_id:
                # Prevent counting the same recovery multiple times
                if record["status"] != "PENDING":
                    return False

                record["status"] = status
                self.shock_recovery_pending -= 1
                if status == "RECOVERED":
                    self.shock_recovery_successes += 1
                    self.shocks_recovered += 1
                else:
                    self.shock_recovery_failures += 1
                record["resolved_tick"] = self.current_tick
                return True
        return False


    def get_kpis(self) -> Dict[str, Any]:
        """Return key performance indicators for dashboard display."""
        active_robots = sum(
            1 for r in self.robots.values()
            if r.status not in ("IDLE", "FAILED", "CHARGING")
        )
        failed_robots = sum(
            1 for r in self.robots.values() if r.status == "FAILED"
        )



        return {
            "tick": self.current_tick,
            "orders_completed": len(self.order_agent.completed_tasks),
            "orders_received": self.order_agent.total_orders_received,
            "pending_tasks": self.order_agent.get_pending_count(),
            "active_robots": active_robots,
            "robots_charging": self.charging_agent.get_charging_count(),
            "robots_failed": failed_robots,
            "robots_queued_charge": self.charging_agent.get_queue_length(),
            "collision_count": self.traffic_controller.collision_count,
            "deadlocks_resolved": self.traffic_controller.deadlocks_resolved,
            "shocks_triggered": self.shocks_triggered,
            "shock_recovery_successes": self.shock_recovery_successes,
            "shock_recovery_failures": self.shock_recovery_failures,
            "shock_recovery_pending": self.shock_recovery_pending,
            # Legacy metric — temporarily retained
            "shocks_recovered": self.shocks_recovered,
            "avg_battery": float(np.mean(
                [r.battery for r in self.robots.values()]
            )) if self.robots else 0.0,
            "total_tasks_completed": sum(
                r.tasks_completed for r in self.robots.values()
            ),
        }



    def get_recent_messages(self, n: int = 50) -> List[Dict[str, Any]]:
        """Return the last N inter-agent messages."""
        return self.message_log[-n:]




def _serialize_payload(payload: Dict) -> Dict:
    """Convert any non-serializable values in the payload to strings."""
    result = {}
    for k, v in payload.items():
        if isinstance(v, tuple):
            result[k] = list(v)
        elif isinstance(v, set):
            result[k] = list(v)
        else:
            result[k] = v
    return result
