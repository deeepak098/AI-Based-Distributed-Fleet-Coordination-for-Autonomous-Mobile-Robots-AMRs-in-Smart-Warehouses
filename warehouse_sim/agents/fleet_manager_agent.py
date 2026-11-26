"""
Fleet Manager Agent — Assigns robots to tasks using selectable allocation algorithms.

Owner: Kalyan (cb.sc.u4cse23060) — Warehouse Intelligence

Responsibility:
    Maintains the live robot registry, selects robots using either centralized
    scored allocation or distributed auction allocation, assigns tasks, and
    handles task reassignment following robot failure or battery handoff.

Supported Allocation Modes:
    centralized:
        Uses the weighted scoring algorithm from task_allocation.py.

    auction:
        Robots independently calculate bids. The lowest valid bid wins.

PEAS Formulation:
    Performance: Assignment quality, task completion, battery efficiency,
                workload distribution, and reduced idle time.
    Environment: Live robot registry, warehouse grid, task queue.
    Actuators: Task assignment, inventory reservation, route requests.
    Sensors: Robot telemetry, task status, battery, position.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import mesa

from ..algorithms.distributed_auction import DistributedAuction, Bid
from ..algorithms.task_allocation import allocate_task


if TYPE_CHECKING:
    from ..model import WarehouseModel
    from .order_agent import Task


class FleetManagerAgent(mesa.Agent):
    """
    Manages the warehouse robot fleet.

    The allocation algorithm can be selected using set_allocation_mode():

        "centralized" -> weighted centralized scoring
        "auction"      -> distributed robot bidding

    Both allocation algorithms share the same task execution pipeline to ensure
    that assignment, routing, inventory reservation, and completion behavior
    remain consistent.
    """

    def __init__(self, model: WarehouseModel) -> None:
        """Initialize the fleet manager."""
        super().__init__(model)

        self.robot_registry: Dict[int, Dict[str, Any]] = {}

        self.pending_assignments: List[Any] = []
        self.tasks_in_progress: Dict[int, Any] = {}

        self.auction = DistributedAuction()

        # Default mode preserves the simulation's existing behavior.
        self.allocation_mode: str = "auction"

        # Tasks eligible for retry during the current simulation step.
        self._retryable_tasks: List[Any] = []

    # ------------------------------------------------------------------
    # ALLOCATION MODE CONFIGURATION
    # ------------------------------------------------------------------

    def set_allocation_mode(self, mode: str) -> None:
        """
        Switch the fleet manager between centralized and auction allocation.

        Args:
            mode: "centralized" or "auction"

        Raises:
            ValueError: If an unsupported allocation mode is provided.
        """
        if mode not in ("centralized", "auction"):
            raise ValueError(
                "Invalid allocation mode. Choose 'centralized' or 'auction'."
            )

        self.allocation_mode = mode

        self.model.log_message(
            from_agent="FleetManager",
            to_agent="System",
            payload={
                "action": "allocation_mode_changed",
                "mode": mode,
            },
        )

    # ------------------------------------------------------------------
    # ROBOT REGISTRY AND TELEMETRY
    # ------------------------------------------------------------------

    def register_robot(self, robot_id: int, pos: Tuple[int, int]) -> None:
        """Register a robot in the fleet registry."""
        self.robot_registry[robot_id] = {
            "pos": pos,
            "battery": 100.0,
            "status": "IDLE",
            "workload": 0,
            "current_task": None,
        }

    def update_telemetry(
        self,
        robot_id: int,
        pos: Tuple[int, int],
        battery: float,
        status: str,
    ) -> None:
        """Update a robot's position, battery, and status."""
        if robot_id not in self.robot_registry:
            return

        self.robot_registry[robot_id]["pos"] = pos
        self.robot_registry[robot_id]["battery"] = battery
        self.robot_registry[robot_id]["status"] = status

    # ------------------------------------------------------------------
    # CENTRALIZED ALLOCATION
    # ------------------------------------------------------------------

    def select_robot_centralized(self, task: Any) -> Optional[int]:
        """Select a robot using the centralized scoring algorithm."""
        is_urgent = bool(getattr(task, "is_urgent", False))

        robot_id = allocate_task(
            robots=self.robot_registry,
            task_location=task.shelf_location,
            is_urgent=is_urgent,
        )

        if robot_id is not None:
            self.model.log_message(
                from_agent="CentralAllocator",
                to_agent=f"Robot-{robot_id}",
                payload={
                    "action": "centralized_robot_selected",
                    "task_id": task.task_id,
                    "robot_id": robot_id,
                    "task_location": task.shelf_location,
                    "is_urgent": is_urgent,
                },
            )

        return robot_id

    # ------------------------------------------------------------------
    # DISTRIBUTED AUCTION ALLOCATION
    # ------------------------------------------------------------------

    def select_robot_via_auction(self, task: Any) -> Optional[int]:
        """Collect robot-local bids and select the lowest valid bid."""

        bids: List[Bid] = []

        for robot_id in self.robot_registry:

            # Retrieve the actual RobotAgent object.
            robot = self.model.get_robot_by_id(robot_id)

            if robot is None:
                continue

            # Each robot independently calculates its bid.
            bid = robot.calculate_bid(task)

            # Collect only valid bids.
            if bid is not None:
                bids.append(bid)

                self.model.log_message(
                    from_agent=f"Robot-{robot_id}",
                    to_agent="Auction",
                    payload={
                        "action": "bid_submitted",
                        "task_id": task.task_id,
                        "bid": bid.cost,
                    },
                )

        # The auction selects the lowest valid bid.
        winner = self.auction.select_winner(bids)

        if winner is None:
            return None

        self.model.log_message(
            from_agent="Auction",
            to_agent=f"Robot-{winner.robot_id}",
            payload={
                "action": "auction_won",
                "task_id": task.task_id,
                "winning_bid": winner.cost,
            },
        )

        return winner.robot_id

    # ------------------------------------------------------------------
    # UNIFIED ROBOT SELECTION
    # ------------------------------------------------------------------

    def select_robot(self, task: Any) -> Optional[int]:
        """
        Select a robot using the currently configured allocation algorithm.

        This method is the single selection entry point used for:
            - New tasks
            - Pending task retries
            - Robot failure reassignment
            - Battery handoff reassignment
        """
        if self.allocation_mode == "centralized":
            return self.select_robot_centralized(task)

        if self.allocation_mode == "auction":
            return self.select_robot_via_auction(task)

        # Defensive fallback; normally unreachable because mode validation
        # is performed by set_allocation_mode().
        raise ValueError(
            f"Unsupported allocation mode: {self.allocation_mode}"
        )

    # ------------------------------------------------------------------
    # TASK QUEUE HELPERS
    # ------------------------------------------------------------------

    def _is_task_pending(self, task: Any) -> bool:
        """Check whether a task is already present in the pending queue."""
        return any(
            pending.task_id == task.task_id
            for pending in self.pending_assignments
        )

    def _add_pending_task(self, task: Any) -> None:
        """Add a task to the pending queue without duplicating it."""
        if task.status != "PENDING":
            task.status = "PENDING"

        if not self._is_task_pending(task):
            self.pending_assignments.append(task)

    def _remove_pending_task(self, task: Any) -> None:
        """Remove a task from the pending queue by task ID."""
        self.pending_assignments = [
            pending
            for pending in self.pending_assignments
            if pending.task_id != task.task_id
        ]

    # ------------------------------------------------------------------
    # TASK ASSIGNMENT
    # ------------------------------------------------------------------

    def assign_task(self, task: Any) -> bool:
        """Assign a task using the currently selected allocation mode."""

        best_robot_id = self.select_robot(task)

        if best_robot_id is None:
            self._add_pending_task(task)
            return False

        self._execute_assignment(best_robot_id, task)
        self._remove_pending_task(task)

        return True

    def _execute_assignment(self, robot_id: int, task: Any) -> None:
        """
        Execute the actual robot-task assignment.

        Shared by both centralized and auction allocation to ensure the
        execution pipeline is identical across experimental conditions.
        """

        # Update the fleet registry.
        self.robot_registry[robot_id]["status"] = "BUSY"
        self.robot_registry[robot_id]["workload"] += 1
        self.robot_registry[robot_id]["current_task"] = task.task_id

        # Record task ownership.
        self.tasks_in_progress[robot_id] = task

        task.status = "IN_PROGRESS"
        task.assigned_robot = robot_id

        # Reserve the shelf via the Inventory Agent.
        self.model.inventory_agent.reserve(
            task.shelf_location,
            robot_id,
        )

        # Request a route via the Traffic Controller.
        robot_pos = self.robot_registry[robot_id]["pos"]

        self.model.traffic_controller.request_route(
            robot_id,
            robot_pos,
            task.shelf_location,
        )

        # Notify the robot of the assignment.
        robot = self.model.get_robot_by_id(robot_id)

        if robot is not None:
            robot.receive_assignment(task)

        # Log assignment.
        self.model.log_message(
            from_agent="FleetManager",
            to_agent=f"Robot-{robot_id}",
            payload={
                "action": "assign_task",
                "task_id": task.task_id,
                "shelf_location": task.shelf_location,
                "robot_id": robot_id,
                "allocation_mode": self.allocation_mode,
            },
        )

    # ------------------------------------------------------------------
    # ROBOT FAILURE HANDLING
    # ------------------------------------------------------------------

    def handle_robot_failure(self, robot_id: int) -> None:
        """
        Handle a robot failure and return its task to the pending queue.

        The task will be reassigned using the active allocation mode.
        """
        if robot_id not in self.robot_registry:
            return

        self.robot_registry[robot_id]["status"] = "FAILED"

        if robot_id in self.tasks_in_progress:
            task = self.tasks_in_progress.pop(robot_id)

            # Release shelf reservation.
            self.model.inventory_agent.release(task.shelf_location)

            # Re-queue the unfinished task.
            task.status = "PENDING"
            task.assigned_robot = -1

            self._add_pending_task(task)

            self.model.log_message(
                from_agent="FleetManager",
                to_agent="OrderAgent",
                payload={
                    "action": "task_reassignment",
                    "task_id": task.task_id,
                    "failed_robot": robot_id,
                    "reason": "robot_failure",
                    "allocation_mode": self.allocation_mode,
                },
            )

    # ------------------------------------------------------------------
    # LOW BATTERY HANDOFF
    # ------------------------------------------------------------------

    def handle_battery_handoff(self, robot_id: int) -> None:
        """
        Hand off an unfinished task from a low-battery robot.

        The task is returned to the pending queue and reassigned using the
        active allocation algorithm.
        """
        if robot_id not in self.tasks_in_progress:
            return

        task = self.tasks_in_progress.pop(robot_id)

        # Release the shelf reservation.
        self.model.inventory_agent.release(task.shelf_location)

        # Re-queue the task.
        task.status = "PENDING"
        task.assigned_robot = -1

        self._add_pending_task(task)

        self.model.log_message(
            from_agent="FleetManager",
            to_agent="System",
            payload={
                "action": "battery_handoff",
                "task_id": task.task_id,
                "from_robot": robot_id,
                "allocation_mode": self.allocation_mode,
            },
        )

    # ------------------------------------------------------------------
    # TASK COMPLETION
    # ------------------------------------------------------------------

    def complete_task(self, robot_id: int) -> None:
        """Mark a robot's task complete and return it to IDLE."""

        if robot_id not in self.tasks_in_progress:
            return

        task = self.tasks_in_progress.pop(robot_id)

        # Update workload.
        self.robot_registry[robot_id]["workload"] = max(
            0,
            self.robot_registry[robot_id]["workload"] - 1,
        )

        # Free the robot.
        self.robot_registry[robot_id]["status"] = "IDLE"
        self.robot_registry[robot_id]["current_task"] = None

        # Release inventory reservation and update stock.
        self.model.inventory_agent.release(task.shelf_location)

        self.model.inventory_agent.decrement_stock(
            task.shelf_location,
            task.sku,
            task.qty,
        )

        # Notify Order Agent.
        self.model.order_agent.mark_task_completed(task.task_id)

        self.model.log_message(
            from_agent="FleetManager",
            to_agent="OrderAgent",
            payload={
                "action": "task_completed",
                "task_id": task.task_id,
                "robot_id": robot_id,
            },
        )

    # ------------------------------------------------------------------
    # SENSE
    # ------------------------------------------------------------------

    def sense(self) -> None:
        """Sense robot telemetry; robots push updates to the registry."""
        pass

    # ------------------------------------------------------------------
    # DECIDE
    # ------------------------------------------------------------------

    def decide(self) -> None:
        """Identify pending tasks that can be retried this step."""

        self._retryable_tasks = [
            task
            for task in self.pending_assignments
            if task.status == "PENDING"
        ]

    # ------------------------------------------------------------------
    # ACT
    # ------------------------------------------------------------------

    def act(self) -> None:
        """Retry pending assignments using the active allocation mode."""

        still_pending: List[Any] = []

        for task in self._retryable_tasks:

            # Skip tasks that are no longer pending.
            if task.status != "PENDING":
                continue

            # Use the selected algorithm, not a hardcoded allocator.
            best_robot_id = self.select_robot(task)

            if best_robot_id is not None:
                self._execute_assignment(best_robot_id, task)
            else:
                still_pending.append(task)

        # Replace the queue with only tasks that remain unassigned.
        self.pending_assignments = still_pending

        # Clear the retry snapshot for the next step.
        self._retryable_tasks = []