
"""
Task Allocation and Deadlock Detection for Warehouse Fleet Management.

Responsibility:
    Scores candidate robots for task assignment using a normalized,
    multi-factor cost function, and detects deadlocks using wait-for
    graph cycle detection.

Allocation scoring:
    - Normalized Manhattan distance
    - Battery risk
    - Urgency priority

Lower score = better candidate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from .astar import manhattan_distance


# ============================================================
# COMMON ALLOCATION SCORING WEIGHTS
# ============================================================

W_DISTANCE = 0.4
W_BATTERY = 0.4
W_PRIORITY = 0.2


# ============================================================
# ROBOT SCORING
# ============================================================

def score_robot(
    robot_pos: Tuple[int, int],
    robot_battery: float,
    robot_workload: int,
    task_location: Tuple[int, int],
    is_urgent: bool,
) -> float:
    """
    Calculate a normalized allocation cost.

    Lower cost = better candidate.

    Factors:
        - Distance: normalized Manhattan distance (0-1)
        - Battery: normalized battery risk (0-1)
        - Priority: urgency bonus (0 or 1)

    Args:
        robot_pos: Current robot position (x, y).
        robot_battery: Current battery percentage (0-100).
        robot_workload: Current assigned workload.
        task_location: Target shelf position (x, y).
        is_urgent: Whether the task is urgent.

    Returns:
        A float cost score. Lower values indicate better candidates.
    """

    # Calculate Manhattan distance
    distance = manhattan_distance(robot_pos, task_location)

    # Normalize distance for a 20x20 warehouse
    # Maximum Manhattan distance = 38
    distance_score = min(distance / 38.0, 1.0)

    # Battery risk:
    # Higher battery = lower risk
    battery_score = 1.0 - (robot_battery / 100.0)

    # Urgency priority
    priority_score = 1.0 if is_urgent else 0.0

    # Common normalized cost formula
    score = (
        W_DISTANCE * distance_score
        + W_BATTERY * battery_score
        - W_PRIORITY * priority_score
    )

    return score


# ============================================================
# CENTRALIZED TASK ALLOCATION
# ============================================================

def allocate_task(
    robots: Dict[int, Dict[str, Any]],
    task_location: Tuple[int, int],
    is_urgent: bool,
    min_battery_threshold: float = 20.0,
) -> Optional[int]:
    """
    Select the best robot for a task using centralized allocation.

    Only robots that are IDLE and have sufficient battery
    are considered.

    Args:
        robots: Dictionary mapping robot_id to robot information.
               Expected fields include:
               pos, battery, status, workload.
        task_location: Target shelf position (x, y).
        is_urgent: Whether the task is urgent.
        min_battery_threshold: Minimum battery percentage
                              required for assignment.

    Returns:
        The robot_id of the best candidate, or None if
        no eligible robot is available.
    """

    best_robot_id = None
    best_score = float("inf")

    for robot_id, info in robots.items():

        # Only consider idle robots
        if info["status"] != "IDLE":
            continue

        # Reject robots with insufficient battery
        if info["battery"] < min_battery_threshold:
            continue

        # Calculate robot cost using the common scoring formula
        robot_score = score_robot(
            robot_pos=info["pos"],
            robot_battery=info["battery"],
            robot_workload=info.get("workload", 0),
            task_location=task_location,
            is_urgent=is_urgent,
        )

        # Select the lowest-cost robot
        if robot_score < best_score:
            best_score = robot_score
            best_robot_id = robot_id

    return best_robot_id


# ============================================================
# DEADLOCK DETECTION
# ============================================================

def detect_deadlock(
    wait_for: Dict[int, Set[int]],
) -> Optional[List[int]]:
    """
    Detect a deadlock cycle in the wait-for graph using DFS.

    Each entry:
        wait_for[robot_id] = {robot_ids it is waiting on}

    represents a directed edge in the wait-for graph.

    Args:
        wait_for: Adjacency list representing the wait-for graph.

    Returns:
        A list of robot_ids forming a cycle if a deadlock
        is detected, or None if no deadlock exists.
    """

    visited: Set[int] = set()
    rec_stack: Set[int] = set()
    parent: Dict[int, Optional[int]] = {}

    def _dfs(node: int) -> Optional[List[int]]:
        """DFS helper that returns a cycle if found."""

        visited.add(node)
        rec_stack.add(node)

        for neighbor in wait_for.get(node, set()):

            if neighbor not in visited:
                parent[neighbor] = node

                result = _dfs(neighbor)

                if result is not None:
                    return result

            elif neighbor in rec_stack:
                # Found a cycle — reconstruct it
                cycle = [neighbor]
                current = node

                while current != neighbor:
                    cycle.append(current)
                    current = parent.get(current, neighbor)

                cycle.append(neighbor)
                cycle.reverse()

                return cycle

        rec_stack.discard(node)

        return None

    for node in wait_for:

        if node not in visited:
            parent[node] = None

            result = _dfs(node)

            if result is not None:
                return result

    return None


# ============================================================
# DEADLOCK RESOLUTION
# ============================================================

def resolve_deadlock(
    cycle: List[int],
    robot_priorities: Dict[int, int],
) -> int:
    """
    Resolve a deadlock by selecting the lowest-priority robot
    in the cycle to yield.

    The selected robot's reservation will be rolled back and
    it will be forced to replan via CBS.

    Args:
        cycle: Robot IDs forming the deadlock cycle.
        robot_priorities: Mapping of robot_id to priority.
                         Higher values mean greater importance.

    Returns:
        The robot_id that should yield.
    """

    # Exclude the duplicate closing node by converting
    # the cycle to a set
    unique_in_cycle = set(cycle)

    # Select the lowest-priority robot
    lowest_priority_robot = min(
        unique_in_cycle,
        key=lambda rid: robot_priorities.get(rid, 0),
    )

    return lowest_priority_robot
