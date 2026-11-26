"""
Fleet Manager Agent — Assigns robots to tasks using selectable allocation algorithms.

Auction mode now uses the model CommunicationSystem for bid requests and bid
responses. The Fleet Manager still centrally coordinates the auction and commits
the winning assignment; this is message-based bidding, not peer-to-peer consensus.
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
    """Manage robot registration, allocation, task assignment, and recovery."""

    def __init__(self, model: WarehouseModel) -> None:
        super().__init__(model)

        self.robot_registry: Dict[int, Dict[str, Any]] = {}
        self.pending_assignments: List[Any] = []
        self.tasks_in_progress: Dict[int, Any] = {}
        self.auction = DistributedAuction()
        self.allocation_mode: str = "auction"
        self._retryable_tasks: List[Any] = []

        # Active message-based auctions, keyed by task ID.
        self.pending_auctions: Dict[int, Dict[str, Any]] = {}
        self.auction_timeout_ticks: int = 10
        # Assignment delivery is retried until the robot acknowledges it.
        self.pending_assignment_deliveries: Dict[int, Dict[str, Any]] = {}
        self.assignment_retry_ticks: int = 3

        # Diagnostics for explaining coordination delays/failures.
        self.auctions_started: int = 0
        self.auctions_timed_out: int = 0
        self.auctions_failed: int = 0
        self.assignment_message_retries: int = 0
        self.assignment_rejections: int = 0
        self.auction_durations: List[int] = []
        self.assignment_delays: List[int] = []  # order-arrival to robot ACK
        self.assignment_delivery_delays: List[int] = []  # committed assignment to ACK
        self.task_wait_to_assignment_ticks: List[int] = []  # task arrival to allocation commitment

    # ------------------------------------------------------------------
    # ALLOCATION MODE CONFIGURATION
    # ------------------------------------------------------------------

    def set_allocation_mode(self, mode: str) -> None:
        """Switch between centralized and message-based auction allocation."""
        if mode not in ("centralized", "auction"):
            raise ValueError(
                "Invalid allocation mode. Choose 'centralized' or 'auction'."
            )

        self.allocation_mode = mode
        self.model.log_message(
            from_agent="FleetManager",
            to_agent="System",
            payload={"action": "allocation_mode_changed", "mode": mode},
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
        """Select a robot using centralized scoring."""
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
    # LEGACY SYNCHRONOUS AUCTION HELPER (kept for compatibility)
    # ------------------------------------------------------------------

    def select_robot_via_auction(self, task: Any) -> Optional[int]:
        """
        Synchronous helper retained for existing callers/tests.

        The live assign_task() and pending-retry paths use message-based
        auctions instead. This helper directly asks robot objects for bids and
        should not be used for communication-delay experiments.
        """
        bids: List[Bid] = []
        for robot_id in self.robot_registry:
            robot = self.model.get_robot_by_id(robot_id)
            if robot is None:
                continue
            bid = robot.calculate_bid(task)
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

    def select_robot(self, task: Any) -> Optional[int]:
        """Compatibility selection entry point (synchronous)."""
        if self.allocation_mode == "centralized":
            return self.select_robot_centralized(task)
        if self.allocation_mode == "auction":
            return self.select_robot_via_auction(task)
        raise ValueError(f"Unsupported allocation mode: {self.allocation_mode}")

    # ------------------------------------------------------------------
    # MESSAGE-BASED AUCTIONS
    # ------------------------------------------------------------------

    def _eligible_robot_ids(self) -> set[int]:
        """Snapshot robots that are eligible to bid at auction start."""
        return {
            robot_id
            for robot_id, state in self.robot_registry.items()
            if state.get("status") == "IDLE"
            and state.get("battery", 0.0) >= 20.0
        }

    def _start_message_auction(self, task: Any) -> bool:
        """Send bid requests through CommunicationSystem and track the auction."""
        task_id = task.task_id
        if task_id in self.pending_auctions:
            return False

        expected = self._eligible_robot_ids()
        if not expected:
            self._add_pending_task(task)
            return False

        tick = self.model.current_tick
        auction_state = {
            "task": task,
            "expected_robots": set(expected),
            "received_bids": {},
            "started_tick": tick,
            "deadline_tick": tick + self.auction_timeout_ticks,
            "status": "WAITING_FOR_BIDS",
        }
        self.pending_auctions[task_id] = auction_state
        self.auctions_started += 1

        request_payload = {
            "type": "BID_REQUEST",
            "task_id": task.task_id,
            "shelf_location": tuple(task.shelf_location),
            "priority": getattr(task, "priority", "normal"),
        }

        sent_count = 0
        for robot_id in sorted(expected):
            message = self.model.communication.send(
                sender="FleetManager",
                receiver=f"Robot-{robot_id}",
                payload=request_payload.copy(),
                current_tick=tick,
            )
            if message is not None:
                sent_count += 1

        self.model.log_message(
            from_agent="FleetManager",
            to_agent="Auction",
            payload={
                "action": "message_auction_started",
                "task_id": task_id,
                "eligible_robots": sorted(expected),
                "requests_sent": sent_count,
                "deadline_tick": auction_state["deadline_tick"],
            },
        )
        return True

    def _process_bid_responses(self) -> None:
        """Collect BID_RESPONSE messages delivered to the Fleet Manager."""
        for message in self.model.delivered_messages:
            if message.receiver != "FleetManager":
                continue
            payload = message.payload
            if payload.get("type") != "BID_RESPONSE":
                continue

            task_id = payload.get("task_id")
            robot_id = payload.get("robot_id")
            state = self.pending_auctions.get(task_id)
            if state is None or state["status"] != "WAITING_FOR_BIDS":
                continue
            if robot_id not in state["expected_robots"]:
                continue
            if robot_id in state["received_bids"]:
                continue

            try:
                cost = float(payload["cost"])
            except (KeyError, TypeError, ValueError):
                continue

            state["received_bids"][robot_id] = Bid(
                robot_id=robot_id,
                task_id=task_id,
                cost=cost,
            )

            self.model.log_message(
                from_agent=f"Robot-{robot_id}",
                to_agent="FleetManager",
                payload={
                    "action": "bid_response_received",
                    "task_id": task_id,
                    "bid": cost,
                },
            )

    def _finalize_message_auction(self, task_id: int) -> None:
        """Close an auction and assign its winner, or queue the task for retry."""
        state = self.pending_auctions.get(task_id)
        if state is None or state["status"] != "WAITING_FOR_BIDS":
            return

        task = state["task"]
        bids = list(state["received_bids"].values())
        winner = self.auction.select_winner(bids)

        state["status"] = "FINALIZED"
        self.pending_auctions.pop(task_id, None)
        self.auction_durations.append(max(0, self.model.current_tick - state["started_tick"]))

        if winner is None:
            self.auctions_failed += 1
            self._add_pending_task(task)
            self.model.log_message(
                from_agent="Auction",
                to_agent="FleetManager",
                payload={
                    "action": "message_auction_no_winner",
                    "task_id": task_id,
                    "received_bids": len(bids),
                },
            )
            return

        # Recheck availability at commit time; telemetry or another assignment
        # may have changed since the robot submitted its bid.
        robot_id = winner.robot_id
        robot_state = self.robot_registry.get(robot_id)
        if (
            robot_state is None
            or robot_state.get("status") != "IDLE"
            or robot_state.get("battery", 0.0) < 20.0
        ):
            self.auctions_failed += 1
            self._add_pending_task(task)
            self.model.log_message(
                from_agent="Auction",
                to_agent="FleetManager",
                payload={
                    "action": "message_auction_winner_unavailable",
                    "task_id": task_id,
                    "robot_id": robot_id,
                },
            )
            return

        self.model.log_message(
            from_agent="Auction",
            to_agent=f"Robot-{robot_id}",
            payload={
                "action": "message_auction_won",
                "task_id": task_id,
                "winning_bid": winner.cost,
            },
        )
        self._execute_assignment(robot_id, task)
        self._remove_pending_task(task)

    def _advance_message_auctions(self) -> None:
        """Finalize auctions when all expected bids arrive or timeout expires."""
        now = self.model.current_tick
        ready_task_ids = []

        for task_id, state in self.pending_auctions.items():
            all_replies_received = (
                len(state["received_bids"]) >= len(state["expected_robots"])
            )
            timed_out = now >= state["deadline_tick"]
            if timed_out and not all_replies_received:
                self.auctions_timed_out += 1
            if all_replies_received or timed_out:
                ready_task_ids.append(task_id)

        for task_id in ready_task_ids:
            self._finalize_message_auction(task_id)

    # ------------------------------------------------------------------
    # TASK QUEUE HELPERS
    # ------------------------------------------------------------------

    def _is_task_pending(self, task: Any) -> bool:
        return any(pending.task_id == task.task_id for pending in self.pending_assignments)

    def _add_pending_task(self, task: Any) -> None:
        if task.status != "PENDING":
            task.status = "PENDING"
        if not self._is_task_pending(task):
            self.pending_assignments.append(task)

    def _remove_pending_task(self, task: Any) -> None:
        self.pending_assignments = [
            pending for pending in self.pending_assignments
            if pending.task_id != task.task_id
        ]

    # ------------------------------------------------------------------
    # TASK ASSIGNMENT
    # ------------------------------------------------------------------

    def assign_task(self, task: Any) -> bool:
        """Start assignment; auction mode is asynchronous, centralized is immediate."""
        if self.allocation_mode == "centralized":
            robot_id = self.select_robot_centralized(task)
            if robot_id is None:
                self._add_pending_task(task)
                return False
            self._execute_assignment(robot_id, task)
            self._remove_pending_task(task)
            return True

        if self.allocation_mode == "auction":
            self._remove_pending_task(task)
            started = self._start_message_auction(task)
            return started

        raise ValueError(f"Unsupported allocation mode: {self.allocation_mode}")

    def _assignment_payload(self, task: Any) -> Dict[str, Any]:
        """Serialize the task fields needed by a robot over the message network."""
        return {
            "task_id": task.task_id,
            "sku": task.sku,
            "qty": task.qty,
            "priority": task.priority,
            "priority_rank": getattr(task, "priority_rank", 1),
            "arrival_tick": getattr(task, "arrival_tick", self.model.current_tick),
            "status": "IN_PROGRESS",
            "assigned_robot": getattr(task, "assigned_robot", -1),
            "shelf_location": tuple(task.shelf_location),
        }

    def _send_assignment(self, task_id: int) -> bool:
        state = self.pending_assignment_deliveries.get(task_id)
        if state is None:
            return False
        message = self.model.communication.send(
            sender="FleetManager",
            receiver=f"Robot-{state['robot_id']}",
            payload={"type": "ASSIGNMENT", "task": state["task_payload"]},
            current_tick=self.model.current_tick,
        )
        state["last_sent_tick"] = self.model.current_tick
        state["attempts"] += 1
        return message is not None


    def _process_assignment_acks(self) -> None:
        """Handle robot acceptance/rejection and stop retries after acknowledgment."""
        for message in self.model.delivered_messages:
            if message.receiver != "FleetManager" or message.payload.get("type") != "ASSIGNMENT_ACK":
                continue
            task_id = message.payload.get("task_id")
            state = self.pending_assignment_deliveries.get(task_id)
            if state is None or message.payload.get("robot_id") != state["robot_id"]:
                continue
            if message.payload.get("accepted"):
                task = state.get("task")
                arrival_tick = getattr(task, "arrival_tick", state.get("created_tick", 0))
                self.assignment_delays.append(max(0, self.model.current_tick - arrival_tick))
                committed_tick = state.get("assignment_started_tick", arrival_tick)
                self.assignment_delivery_delays.append(max(0, self.model.current_tick - committed_tick))
                self.pending_assignment_deliveries.pop(task_id, None)
                self.model.log_message(
                    from_agent=f"Robot-{state['robot_id']}", to_agent="FleetManager",
                    payload={"action": "assignment_acknowledged", "task_id": task_id},
                )
            else:
                self.assignment_rejections += 1
                self.pending_assignment_deliveries.pop(task_id, None)
                robot_id = state["robot_id"]
                task = state["task"]
                self.tasks_in_progress.pop(robot_id, None)
                self.robot_registry[robot_id]["status"] = "IDLE"
                self.robot_registry[robot_id]["current_task"] = None
                self.model.inventory_agent.release(task.shelf_location)
                task.status = "PENDING"
                task.assigned_robot = -1
                self._add_pending_task(task)

    def _retry_assignment_deliveries(self) -> None:
        now = self.model.current_tick
        for task_id, state in list(self.pending_assignment_deliveries.items()):
            last_sent = state.get("last_sent_tick", -self.assignment_retry_ticks)
            if now - last_sent >= self.assignment_retry_ticks:
                self.assignment_message_retries += 1
                self._send_assignment(task_id)

    def _execute_assignment(self, robot_id: int, task: Any) -> None:
        """Commit assignment, reserve inventory, and notify via CommunicationSystem."""
        arrival_tick = getattr(task, "arrival_tick", self.model.current_tick)
        self.task_wait_to_assignment_ticks.append(max(0, self.model.current_tick - arrival_tick))
        self.robot_registry[robot_id]["status"] = "BUSY"
        self.robot_registry[robot_id]["workload"] += 1
        self.robot_registry[robot_id]["current_task"] = task.task_id

        self.tasks_in_progress[robot_id] = task
        task.status = "IN_PROGRESS"
        task.assigned_robot = robot_id

        self.model.inventory_agent.reserve(task.shelf_location, robot_id)

        robot_pos = self.robot_registry[robot_id]["pos"]
        self.model.traffic_controller.request_route(
            robot_id, robot_pos, task.shelf_location
        )

        # No direct robot method call: assignment must travel over the network.
        self.pending_assignment_deliveries[task.task_id] = {
            "robot_id": robot_id,
            "task": task,
            "task_payload": self._assignment_payload(task),
            "last_sent_tick": -self.assignment_retry_ticks,
            "attempts": 0,
            "created_tick": self.model.current_tick,
            "assignment_started_tick": self.model.current_tick,
        }
        self._send_assignment(task.task_id)

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
        if robot_id not in self.robot_registry:
            return

        self.robot_registry[robot_id]["status"] = "FAILED"
        if robot_id in self.tasks_in_progress:
            task = self.tasks_in_progress.pop(robot_id)
            self.model.inventory_agent.release(task.shelf_location)
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
        if robot_id not in self.tasks_in_progress:
            return

        task = self.tasks_in_progress.pop(robot_id)
        self.model.inventory_agent.release(task.shelf_location)
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
        if robot_id not in self.tasks_in_progress:
            return

        task = self.tasks_in_progress.pop(robot_id)
        self.robot_registry[robot_id]["workload"] = max(
            0, self.robot_registry[robot_id]["workload"] - 1
        )
        self.robot_registry[robot_id]["status"] = "IDLE"
        self.robot_registry[robot_id]["current_task"] = None

        self.model.inventory_agent.release(task.shelf_location)
        self.model.inventory_agent.decrement_stock(
            task.shelf_location, task.sku, task.qty
        )
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
    # SENSE / DECIDE / ACT
    # ------------------------------------------------------------------

    def sense(self) -> None:
        """Process incoming bid responses and assignment acknowledgments."""
        self._process_bid_responses()
        self._process_assignment_acks()

    def decide(self) -> None:
        """Snapshot pending tasks eligible for retry this tick."""
        self._retryable_tasks = [
            task for task in self.pending_assignments
            if task.status == "PENDING"
        ]

    def act(self) -> None:
        """Progress auctions, retry assignment messages, and pending tasks."""
        self._advance_message_auctions()
        self._retry_assignment_deliveries()

        # Retry tasks, but don't start duplicate auctions for a task already
        # undergoing an auction. A fresh auction is initiated at most once
        # during this ACT phase for each pending task.
        for task in self._retryable_tasks:
            if task.status != "PENDING":
                continue
            if task.task_id in self.pending_auctions:
                continue

            if self.allocation_mode == "centralized":
                robot_id = self.select_robot_centralized(task)
                if robot_id is not None:
                    self._execute_assignment(robot_id, task)
                    self._remove_pending_task(task)
            elif self.allocation_mode == "auction":
                self._start_message_auction(task)

        self._retryable_tasks = []
