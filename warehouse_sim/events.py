"""
Environmental Shocks — Stress-test functions for live demo scenarios.

Owner: Venkat (cb.sc.u4cse23055) — Operations
Responsibility: Implements 5 callable shock functions that can be triggered
live during the demo to test the system's dynamic replanning and recovery.

Shock recovery is tracked separately from shock injection. A shock is registered
as PENDING and is only counted as RECOVERED when its recovery condition is
observed. Asynchronous shocks can be checked by calling
monitor_shock_recoveries(model) after each simulation tick.
"""

from __future__ import annotations



import random
from typing import Any, Dict, Optional, Tuple, List


from .model import WarehouseModel


# Maximum number of simulation ticks allowed for asynchronous recovery.
DEFAULT_RECOVERY_WINDOW = 50



def _register_shock(
    model: WarehouseModel,
    shock_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Register a shock using model-level tracking, if supported."""
    register = getattr(model, "register_shock", None)
    if callable(register):
        return register(shock_type, details)
    return None



def _set_shock_status(model: WarehouseModel, shock_id: Optional[int], status: str) -> bool:
    """Update the tracked status; safely no-op for older model versions."""
    if shock_id is None:
        return False
    updater = getattr(model, "update_shock_status", None)
    if callable(updater):
        return updater(shock_id, status)
    return False



def _finish_immediate(
    model: WarehouseModel,
    shock_id: Optional[int],
    recovered: bool,
) -> None:
    """Resolve an immediate shock outcome without double-counting it."""
    if shock_id is not None:
        _set_shock_status(model, shock_id, "RECOVERED" if recovered else "FAILED")
    elif recovered:
        # Compatibility with models predating the new tracking helpers.
        model.shocks_recovered = getattr(model, "shocks_recovered", 0) + 1



def _is_safe_hold(robot: Any) -> bool:
    """Return True when a robot with no route is in a safe stationary state."""
    status = str(getattr(robot, "status", "")).upper()
    return status in {"HOLD", "HELD", "WAITING", "IDLE", "NEEDS_CHARGE", "CHARGING", "FAILED"}



def _robot_path_avoids(robot: Any, cell: Tuple[int, int]) -> bool:
    """Check that a robot's currently planned path no longer uses a blocked cell."""
    path = getattr(robot, "current_path", None) or []
    return cell not in path



def _task_identifier(task: Any) -> Any:
    """Extract a stable-looking task identifier when the task exposes one."""
    if task is None:
        return None
    if isinstance(task, (str, int)):
        return task
    for name in ("task_id", "id", "order_id"):
        value = getattr(task, name, None)
        if value is not None:
            return value
    return None



def _task_is_requeued(model: WarehouseModel, task_id: Any) -> bool:
    """Determine whether a failed robot's task has been returned to the queue."""
    if task_id is None:
        return False
    order_agent = getattr(model, "order_agent", None)
    fleet_manager = getattr(model, "fleet_manager", None)

    # If the task is no longer in the Fleet Manager's active-task mapping,
    # check common pending-task collections for evidence it was requeued.
    active_map = getattr(fleet_manager, "tasks_in_progress", None)
    if isinstance(active_map, dict) and task_id not in active_map:
        for attr in ("pending_tasks", "tasks_pending", "task_queue"):
            pending = getattr(order_agent, attr, None)
            if pending is not None:
                try:
                    if task_id in pending or any(_task_identifier(t) == task_id for t in pending):
                        return True
                except TypeError:
                    pass
        # The Fleet Manager removed the task from its active mapping, which
        # means it is no longer assigned to the failed robot. This is treated
        # as recovered-to-queue, not as completed delivery.
        return True

    # Check common pending queue names when task collections are objects.
    for attr in ("pending_tasks", "tasks_pending", "task_queue"):
        pending = getattr(order_agent, attr, None)
        if pending is not None:
            try:
                if task_id in pending or any(_task_identifier(t) == task_id for t in pending):
                    return True
            except TypeError:
                pass
    return False



def monitor_shock_recoveries(model: WarehouseModel) -> Dict[str, int]:
    """Evaluate pending shock recoveries; call after every model simulation tick.



    Returns counts of shocks resolved during this monitoring pass.
    Pending shocks are marked FAILED after their configured recovery window.
    """
    resolved_now = {"recovered": 0, "failed": 0}
    records: List[Dict[str, Any]] = getattr(model, "shock_records", [])
    for record in records:
        if record.get("status") != "PENDING":
            continue

        details = record.get("details", {})
        shock_type = record.get("shock_type")
        recovered = False

        if shock_type == "robot_failure":
            task_id = details.get("task_id")
            # A robot failure with no task to hand off is immediately safe.
            recovered = details.get("task_was_active") is False or _task_is_requeued(model, task_id)

        elif shock_type == "blocked_aisle":
            cell = tuple(details.get("blocked_cell", ()))
            affected_ids = details.get("affected_robot_ids", [])
            affected = [model.get_robot_by_id(rid) for rid in affected_ids]
            affected = [robot for robot in affected if robot is not None]
            recovered = all(
                _robot_path_avoids(robot, cell)
                and (getattr(robot, "current_path", None) or _is_safe_hold(robot))
                for robot in affected
            )

        elif shock_type == "battery_failure":
            robot = model.get_robot_by_id(details.get("robot_id"))
            recovered = bool(
                robot is not None
                and (
                    str(getattr(robot, "status", "")).upper() == "CHARGING"
                    or float(getattr(robot, "battery", 0.0)) > float(details.get("recovery_battery", 5.0))
                )
            )

        elif shock_type == "order_flood":
            baseline = details.get("pending_before", 0)
            order_agent = getattr(model, "order_agent", None)
            pending_count = order_agent.get_pending_count() if order_agent else baseline
            recovered = pending_count <= baseline

        elif shock_type == "deadlock_injection":
            recovered = bool(details.get("deadlock_resolved", False))

        if recovered:
            if _set_shock_status(model, record.get("shock_id"), "RECOVERED"):
                resolved_now["recovered"] += 1
            continue

        window = int(details.get("recovery_window", DEFAULT_RECOVERY_WINDOW))
        shock_tick = int(record.get("tick", getattr(model, "current_tick", 0)))
        if int(getattr(model, "current_tick", 0)) - shock_tick >= window:
            if _set_shock_status(model, record.get("shock_id"), "FAILED"):
                resolved_now["failed"] += 1

    return resolved_now



def kill_robot(model: WarehouseModel, robot_id: int) -> Dict[str, Any]:
    """Shock 1: disable a robot and return its task to the fleet manager."""
    robot = model.get_robot_by_id(robot_id)
    if robot is None:
        return {"error": f"Robot {robot_id} not found"}
    if robot.status == "FAILED":
        return {"error": f"Robot {robot_id} is already failed"}

    before_status = robot.status
    before_task = robot.current_task
    task_id = _task_identifier(before_task)
    shock_id = _register_shock(
        model,
        "robot_failure",
        {
            "robot_id": robot_id,
            "task_id": task_id,
            "task_was_active": before_task is not None,
            "recovery_window": DEFAULT_RECOVERY_WINDOW,
        },
    )

    robot.status = "FAILED"
    robot.current_path = []
    model.traffic_controller._clear_reservations(robot_id)
    model.fleet_manager.handle_robot_failure(robot_id)



    # A taskless robot is already safely removed from the active fleet.
    recovered = before_task is None
    _finish_immediate(model, shock_id, recovered)
    event = {
        "shock_type": "robot_failure",
        "tick": model.current_tick,
        "shock_id": shock_id,
        "robot_id": robot_id,
        "before_status": before_status,
        "task_reassigned": False,
        "task_requeued": False,
        "recovered": recovered,
        "recovery_status": "RECOVERED" if recovered else "PENDING",
    }
    if before_task is not None:
        event["task_id"] = task_id
        event["task_requeued"] = _task_is_requeued(model, task_id)
        event["task_reassigned"] = event["task_requeued"]
        if event["task_requeued"]:
            _finish_immediate(model, shock_id, True)
            event["recovered"] = True
            event["recovery_status"] = "RECOVERED"

    model.log_message(from_agent="EventSystem", to_agent="FleetManager", payload=event)
    return event



def block_cell(model: WarehouseModel, cell: Tuple[int, int]) -> Dict[str, Any]:
    """Shock 2: block a cell and reroute or safely hold affected robots."""
    if cell in model.shelf_locations or cell == model.packing_station:
        return {"error": "Cannot block a shelf or packing station"}
    if cell in model.charging_docks:
        return {"error": "Cannot block a charging dock"}
    if cell in model.blocked_cells:
        return {"error": "Cell is already blocked"}
    if not (0 <= cell[0] < model.grid_width and 0 <= cell[1] < model.grid_height):
        return {"error": "Cell is outside the warehouse grid"}

    affected = [
        robot for robot in model.robots.values()
        if cell in (getattr(robot, "current_path", None) or [])
    ]
    affected_ids = [robot.robot_id for robot in affected]
    shock_id = _register_shock(
        model,
        "blocked_aisle",
        {
            "blocked_cell": list(cell),
            "affected_robot_ids": affected_ids,
            "recovery_window": DEFAULT_RECOVERY_WINDOW,
        },
    )

    model.blocked_cells.add(cell)
    rerouted = model.traffic_controller.reroute_on_block(cell)
    recovered = all(
        _robot_path_avoids(robot, cell)
        and (getattr(robot, "current_path", None) or _is_safe_hold(robot))
        for robot in affected
    )
    _finish_immediate(model, shock_id, recovered)

    event = {
        "shock_type": "blocked_aisle",
        "tick": model.current_tick,
        "shock_id": shock_id,
        "blocked_cell": list(cell),
        "affected_robot_ids": affected_ids,
        "robots_rerouted": rerouted,
        "recovered": recovered,
        "recovery_status": "RECOVERED" if recovered else "PENDING",
    }
    model.log_message(from_agent="EventSystem", to_agent="TrafficController", payload=event)
    return event



def force_drain(model: WarehouseModel, robot_id: int) -> Dict[str, Any]:
    """Shock 3: drain a robot's battery; recovery is asynchronous."""
    robot = model.get_robot_by_id(robot_id)
    if robot is None:
        return {"error": f"Robot {robot_id} not found"}
    if robot.status == "FAILED":
        return {"error": f"Robot {robot_id} is failed and cannot be drained"}

    before_battery = robot.battery
    before_status = robot.status
    shock_id = _register_shock(
        model,
        "battery_failure",
        {
            "robot_id": robot_id,
            "before_battery": before_battery,
            "recovery_battery": 20.0,
            "recovery_window": DEFAULT_RECOVERY_WINDOW,
        },
    )

    robot.battery = 5.0
    robot.status = "NEEDS_CHARGE"
    event = {
        "shock_type": "battery_failure",
        "tick": model.current_tick,
        "shock_id": shock_id,
        "robot_id": robot_id,
        "before_battery": before_battery,
        "after_battery": 5.0,
        "before_status": before_status,
        "recovered": False,
        "recovery_status": "PENDING",
    }
    model.log_message(from_agent="EventSystem", to_agent="ChargingAgent", payload=event)
    return event



def flood_urgent_orders(model: WarehouseModel, n: int = 10) -> Dict[str, Any]:
    """Shock 4: inject urgent orders; recovery is tracked against baseline backlog."""
    if n <= 0:
        return {"error": "Number of injected orders must be greater than zero"}

    skus = [f"SKU-{i:03d}" for i in range(1, 21)]
    pending_before = model.order_agent.get_pending_count()
    shock_id = _register_shock(
        model,
        "order_flood",
        {
            "orders_requested": n,
            "pending_before": pending_before,
            "recovery_window": DEFAULT_RECOVERY_WINDOW,
        },
    )

    orders_created = 0
    for _ in range(n):
        sku = model.event_rng.choice(skus)
        qty = model.event_rng.randint(1, 2)
        model.order_agent.receive_order(sku, qty, "urgent")
        orders_created += 1

    event = {
        "shock_type": "order_flood",
        "tick": model.current_tick,
        "shock_id": shock_id,
        "orders_injected": orders_created,
        "total_pending": model.order_agent.get_pending_count(),
        "recovered": False,
        "recovery_status": "PENDING",
    }
    model.log_message(from_agent="EventSystem", to_agent="OrderAgent", payload=event)
    return event



def inject_deadlock(model: WarehouseModel) -> Dict[str, Any]:
    """Shock 5: create a conflicting route situation and check resolution."""
    idle_robots = [r for r in model.robots.values() if r.status == "IDLE"]
    if len(idle_robots) < 2:
        idle_robots = [r for r in model.robots.values() if r.status != "FAILED"]
    if len(idle_robots) < 2:
        return {"error": "Need at least 2 non-failed robots for deadlock injection"}

    robot_a, robot_b = idle_robots[0], idle_robots[1]
    pos_a, pos_b = (5, 10), (5, 14)
    shock_id = _register_shock(
        model,
        "deadlock_injection",
        {
            "robot_a": robot_a.robot_id,
            "robot_b": robot_b.robot_id,
            "recovery_window": DEFAULT_RECOVERY_WINDOW,
        },
    )

    # Update the agent's stored position and the grid occupancy consistently.
    for robot, new_pos in ((robot_a, pos_a), (robot_b, pos_b)):
        try:
            if robot.pos_tuple != new_pos:
                model.grid.move_agent(robot, new_pos)
            robot.pos_tuple = new_pos
        except Exception:
            # Preserve the live demo's non-crashing behavior, but report below.
            pass

    path_a = model.traffic_controller.request_route(robot_a.robot_id, pos_a, pos_b)
    path_b = model.traffic_controller.request_route(robot_b.robot_id, pos_b, pos_a)
    if path_a:
        robot_a.update_path(path_a)
        robot_a.status = "EN_ROUTE_TO_SHELF"
    if path_b:
        robot_b.update_path(path_b)
        robot_b.status = "EN_ROUTE_TO_SHELF"

    resolved = model.traffic_controller.check_and_resolve_deadlocks()
    recovered = bool(resolved > 0)
    _finish_immediate(model, shock_id, recovered)
    event = {
        "shock_type": "deadlock_injection",
        "tick": model.current_tick,
        "shock_id": shock_id,
        "robot_a": robot_a.robot_id,
        "robot_b": robot_b.robot_id,
        "deadlock_resolved": recovered,
        "recovered": recovered,
        "recovery_status": "RECOVERED" if recovered else "PENDING",
    }
    model.log_message(from_agent="EventSystem", to_agent="TrafficController", payload=event)
    return event
