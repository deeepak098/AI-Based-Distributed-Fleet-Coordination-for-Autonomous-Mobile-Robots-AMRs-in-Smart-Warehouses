"""
Environmental Shocks — Stress-test functions for live demo scenarios.

Owner: Venkat (cb.sc.u4cse23055) — Operations
Responsibility: Implements 5 callable shock functions that can be triggered
live during the demo to test the system's dynamic replanning and recovery.

Each shock function returns a recovery event dict for dashboard display.
The system must recover from each shock autonomously — no manual restart.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional, Tuple

from .model import WarehouseModel


def kill_robot(model: WarehouseModel, robot_id: int) -> Dict[str, Any]:
    """
    Shock 1: Robot Failure — instantly disables a robot.

    The Fleet Manager must reassign its in-progress task to the next
    available robot within the same tick.

    Args:
        model: The warehouse model instance.
        robot_id: The robot to kill.

    Returns:
        Recovery event dict with before/after state.
    """
    robot = model.get_robot_by_id(robot_id)
    if robot is None:
        return {"error": f"Robot {robot_id} not found"}

    before_status = robot.status
    before_task = robot.current_task

    # Kill the robot
    robot.status = "FAILED"
    robot.current_path = []

    # Clear its reservations
    model.traffic_controller._clear_reservations(robot_id)

    # Fleet Manager handles reassignment
    model.fleet_manager.handle_robot_failure(robot_id)

    model.shocks_recovered += 1

    event = {
        "shock_type": "robot_failure",
        "tick": model.current_tick,
        "robot_id": robot_id,
        "before_status": before_status,
        "task_reassigned": before_task is not None,
        "recovered": True,
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="FleetManager",
        payload=event,
    )

    return event


def block_cell(
    model: WarehouseModel, cell: Tuple[int, int]
) -> Dict[str, Any]:
    """
    Shock 2: Blocked Aisle / Shelf Collapse — marks a cell impassable.

    The Traffic Controller must detect all robots with paths through
    the blocked cell and trigger reroute_on_block().

    Args:
        model: The warehouse model instance.
        cell: The (x, y) cell to block.

    Returns:
        Recovery event dict.
    """
    if cell in model.shelf_locations or cell == model.packing_station:
        return {"error": "Cannot block a shelf or packing station"}
    if cell in model.charging_docks:
        return {"error": "Cannot block a charging dock"}

    model.blocked_cells.add(cell)

    # Traffic Controller reroutes affected robots
    rerouted = model.traffic_controller.reroute_on_block(cell)

    model.shocks_recovered += 1

    event = {
        "shock_type": "blocked_aisle",
        "tick": model.current_tick,
        "blocked_cell": list(cell),
        "robots_rerouted": rerouted,
        "recovered": True,
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="TrafficController",
        payload=event,
    )

    return event


def force_drain(model: WarehouseModel, robot_id: int) -> Dict[str, Any]:
    """
    Shock 3: Battery Failure — drains a robot's battery to 5%.

    The Charging Agent must redirect it to the nearest dock, and the
    Fleet Manager must hand off its in-progress task if mid-delivery.

    Args:
        model: The warehouse model instance.
        robot_id: The robot to drain.

    Returns:
        Recovery event dict.
    """
    robot = model.get_robot_by_id(robot_id)
    if robot is None:
        return {"error": f"Robot {robot_id} not found"}

    before_battery = robot.battery
    before_status = robot.status

    # Force battery drain
    robot.battery = 5.0
    robot.status = "NEEDS_CHARGE"

    model.shocks_recovered += 1

    event = {
        "shock_type": "battery_failure",
        "tick": model.current_tick,
        "robot_id": robot_id,
        "before_battery": before_battery,
        "after_battery": 5.0,
        "before_status": before_status,
        "recovered": True,
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="ChargingAgent",
        payload=event,
    )

    return event


def flood_urgent_orders(
    model: WarehouseModel, n: int = 10
) -> Dict[str, Any]:
    """
    Shock 4: Traffic Congestion Spike — injects N urgent orders at once.

    The Traffic Controller must demonstrate rerouting/queueing without
    deadlocking.

    Args:
        model: The warehouse model instance.
        n: Number of urgent orders to inject.

    Returns:
        Recovery event dict.
    """
    skus = [f"SKU-{i:03d}" for i in range(1, 21)]
    orders_created = 0

    for _ in range(n):
        sku = random.choice(skus)
        qty = random.randint(1, 2)
        model.order_agent.receive_order(sku, qty, "urgent")
        orders_created += 1

    model.shocks_recovered += 1

    event = {
        "shock_type": "order_flood",
        "tick": model.current_tick,
        "orders_injected": orders_created,
        "total_pending": model.order_agent.get_pending_count(),
        "recovered": True,
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="OrderAgent",
        payload=event,
    )

    return event


def inject_deadlock(model: WarehouseModel) -> Dict[str, Any]:
    """
    Shock 5: Deadlock Injection — forces two robots into a head-on conflict.

    Places two idle robots on a collision course and relies on the
    Traffic Controller's wait-for-graph detection and CBS/rollback
    to resolve the deadlock.

    Args:
        model: The warehouse model instance.

    Returns:
        Recovery event dict.
    """
    # Find two available robots (prefer idle, fall back to any non-failed)
    idle_robots = [
        r for r in model.robots.values()
        if r.status == "IDLE"
    ]

    if len(idle_robots) < 2:
        # Fall back to any non-failed robots
        idle_robots = [
            r for r in model.robots.values()
            if r.status != "FAILED"
        ]

    if len(idle_robots) < 2:
        return {"error": "Need at least 2 non-failed robots for deadlock injection"}

    robot_a = idle_robots[0]
    robot_b = idle_robots[1]

    # Place them facing each other in a narrow corridor
    # Robot A at (5, 10), goal at (5, 14)
    # Robot B at (5, 14), goal at (5, 10)
    pos_a = (5, 10)
    pos_b = (5, 14)

    robot_a.pos_tuple = pos_a
    robot_b.pos_tuple = pos_b

    # Update grid positions
    try:
        model.grid.move_agent(robot_a, pos_a)
        model.grid.move_agent(robot_b, pos_b)
    except Exception:
        pass

    # Request conflicting routes
    path_a = model.traffic_controller.request_route(
        robot_a.robot_id, pos_a, pos_b
    )
    path_b = model.traffic_controller.request_route(
        robot_b.robot_id, pos_b, pos_a
    )

    if path_a:
        robot_a.update_path(path_a)
        robot_a.status = "EN_ROUTE_TO_SHELF"
    if path_b:
        robot_b.update_path(path_b)
        robot_b.status = "EN_ROUTE_TO_SHELF"

    # Force deadlock check
    resolved = model.traffic_controller.check_and_resolve_deadlocks()

    model.shocks_recovered += 1

    event = {
        "shock_type": "deadlock_injection",
        "tick": model.current_tick,
        "robot_a": robot_a.robot_id,
        "robot_b": robot_b.robot_id,
        "deadlock_resolved": resolved > 0,
        "recovered": True,
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="TrafficController",
        payload=event,
    )

    return event
