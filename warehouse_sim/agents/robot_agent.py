"""
Robot Agent — Physical warehouse robot with state machine and battery management.

Owner: Rohith (cb.sc.u4cse23018) — Robot Intelligence
Responsibility: Executes assigned paths step-by-step, manages battery consumption,
follows a 7-state FSM, and broadcasts telemetry to the Fleet Manager every tick.

PEAS Formulation:
    Performance: Task completion time, safe navigation, battery discipline.
    Environment: Physical/simulated grid cell, shelf, packing station, charging dock.
    Actuators: move(), pick(), drop(), dock_to_charge().
    Sensors: Local grid occupancy, battery level, assigned route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import mesa

if TYPE_CHECKING:
    from ..model import WarehouseModel


# Battery constants
BATTERY_DRAIN_PER_MOVE = 1.0
BATTERY_DRAIN_PER_PICK = 2.0
BATTERY_CHARGE_PER_TICK = 5.0
BATTERY_LOW_THRESHOLD = 20.0
PICK_TICKS = 2
DROP_TICKS = 2


class RobotAgent(mesa.Agent):
    """
    Physical warehouse robot executing pick-and-deliver tasks.

    State Machine:
        IDLE → EN_ROUTE_TO_SHELF → PICKING → EN_ROUTE_TO_PACKING →
        DROPPING → RETURNING → IDLE

    The CHARGING state is reachable from any state when battery < 20%.
    """

    def __init__(
        self,
        model: WarehouseModel,
        robot_id: int,
        start_pos: Tuple[int, int],
    ) -> None:
        """Initialize the robot at its starting position."""
        super().__init__(model)
        self.robot_id: int = robot_id
        self.pos_tuple: Tuple[int, int] = start_pos
        self.battery: float = 100.0
        self.status: str = "IDLE"
        self.current_path: List[Tuple[int, int]] = []
        self.path_index: int = 0
        self.current_task: Optional[Any] = None
        self.tasks_completed: int = 0
        self._action_timer: int = 0
        self._pre_charge_status: str = "IDLE"
        self._pre_charge_task: Optional[Any] = None
        self._charging_dock: Optional[Tuple[int, int]] = None
        self._return_path: List[Tuple[int, int]] = []




    def calculate_bid(self, task: Any) -> Optional[Any]:
        """Calculate this robot's bid using the common scoring formula."""

        # Only idle robots are allowed to bid
        if self.status != "IDLE":
            return None

        # Reject robots with insufficient battery
        if self.battery < BATTERY_LOW_THRESHOLD:
            return None

        # Calculate Manhattan distance from robot to task shelf
        distance = (
            abs(self.pos_tuple[0] - task.shelf_location[0])
            + abs(self.pos_tuple[1] - task.shelf_location[1])
        )

        # Normalize distance between 0 and 1
        distance_score = min(distance / 38.0, 1.0)

        # Battery penalty: lower battery means higher cost
        energy_score = 1.0 - (self.battery / 100.0)

        # Determine task urgency
        urgency_score = (
            1.0 if str(task.priority).lower() == "urgent" else 0.0
        )

        # Create auction instance
        from ..algorithms.distributed_auction import DistributedAuction

        auction = DistributedAuction()

        # Submit bid using the common scoring formula
        return auction.calculate_bid(
            robot_id=self.robot_id,
            task_id=task.task_id,
            distance_score=distance_score,
            energy_score=energy_score,
            urgency_score=urgency_score,
        )

    def receive_assignment(self, task: Any) -> None:
        """Receive a task assignment from the Fleet Manager."""
        self.current_task = task
        self.status = "EN_ROUTE_TO_SHELF"


    

    def update_path(self, path: List[Tuple[int, int]]) -> None:
        """Update the robot's current navigation path."""
        self.current_path = path
        self.path_index = 0

    def hold(self) -> None:
        """Hold in place (wait) — used for deadlock resolution."""
        self.path_index = max(0, self.path_index)

    def sense(self) -> None:
        """Broadcast telemetry to the Fleet Manager."""
        self.model.fleet_manager.update_telemetry(
            self.robot_id, self.pos_tuple, self.battery, self.status
        )

    def decide(self) -> None:
        """Decide what action to take based on current state."""
        # Check for low battery (unless already charging)
        if (
            self.battery < BATTERY_LOW_THRESHOLD
            and self.status != "CHARGING"
            and self.status != "FAILED"
        ):
            self._pre_charge_status = self.status
            self._pre_charge_task = self.current_task
            self.status = "NEEDS_CHARGE"

    def act(self) -> None:
        """Execute one tick of robot behavior based on current state."""
        if self.status == "FAILED":
            return

        if self.status == "NEEDS_CHARGE":
            self._initiate_charging()
            return

        if self.status == "CHARGING":
            self._charge_tick()
            return

        if self.status == "IDLE":
            return

        if self.status in ("EN_ROUTE_TO_SHELF", "EN_ROUTE_TO_PACKING", "RETURNING"):
            self._follow_path()
            return

        if self.status == "PICKING":
            self._pick_tick()
            return

        if self.status == "DROPPING":
            self._drop_tick()
            return

    def _follow_path(self) -> None:
        """Move one step along the current path."""
        if not self.current_path or self.path_index >= len(self.current_path) - 1:
            self._arrive_at_destination()
            return

        self.path_index += 1
        next_pos = self.current_path[self.path_index]

        # Check if next cell is occupied by another robot
        # Allow sharing at packing station and charging docks (work areas)
        is_shared_area = (
            next_pos == self.model.packing_station
            or next_pos in self.model.charging_docks
            or self.path_index >= len(self.current_path) - 1  # destination
        )

        if not is_shared_area:
            occupants = self.model.get_robots_at(next_pos)
            if any(r.robot_id != self.robot_id for r in occupants):
                # Wait in place
                self.path_index -= 1
                return

        self.pos_tuple = next_pos
        self.battery = max(0, self.battery - BATTERY_DRAIN_PER_MOVE)

        # Update grid position
        if hasattr(self, 'pos') and self.pos is not None:
            self.model.grid.move_agent(self, next_pos)

    def _arrive_at_destination(self) -> None:
        """Handle arrival at the current destination."""
        if self.status == "EN_ROUTE_TO_SHELF":
            self.status = "PICKING"
            self._action_timer = PICK_TICKS
        elif self.status == "EN_ROUTE_TO_PACKING":
            self.status = "DROPPING"
            self._action_timer = DROP_TICKS
        elif self.status == "RETURNING":
            self.status = "IDLE"
            self.current_path = []
            self.path_index = 0

    def _pick_tick(self) -> None:
        """Process one tick of the picking action."""
        self._action_timer -= 1
        self.battery = max(0, self.battery - BATTERY_DRAIN_PER_PICK)

        if self._action_timer <= 0:
            # Picking complete — head to packing station
            self.status = "EN_ROUTE_TO_PACKING"
            packing = self.model.packing_station
            path = self.model.traffic_controller.request_route(
                self.robot_id, self.pos_tuple, packing
            )
            if path:
                self.update_path(path)
            else:
                # Fallback: try next tick
                self.status = "PICKING"
                self._action_timer = 1

            self.model.log_message(
                from_agent=f"Robot-{self.robot_id}",
                to_agent="TrafficController",
                payload={
                    "action": "request_route_to_packing",
                    "from": self.pos_tuple,
                    "to": packing,
                },
            )

    def _drop_tick(self) -> None:
        """Process one tick of the dropping action."""
        self._action_timer -= 1

        if self._action_timer <= 0:
            # Dropping complete — task finished
            self.tasks_completed += 1
            self.model.fleet_manager.complete_task(self.robot_id)

            # Clear reservations so other robots can use the paths
            self.model.traffic_controller._clear_reservations(self.robot_id)

            # Return to idle
            self.status = "IDLE"
            self.current_task = None
            self.current_path = []
            self.path_index = 0

    def _initiate_charging(self) -> None:
        """Request a charging dock from the Charging Agent."""
        self.model.charging_agent.request_charge(self.robot_id, self.pos_tuple)
        self.status = "CHARGING"

        # If we had an in-progress task, hand it off
        if self.current_task and self._pre_charge_status in (
            "EN_ROUTE_TO_SHELF",
            "EN_ROUTE_TO_PACKING",
        ):
            self.model.fleet_manager.handle_battery_handoff(self.robot_id)
            self.current_task = None

        self.model.log_message(
            from_agent=f"Robot-{self.robot_id}",
            to_agent="ChargingAgent",
            payload={
                "action": "request_charge",
                "battery": self.battery,
                "pos": self.pos_tuple,
            },
        )

    def _charge_tick(self) -> None:
        """Process one tick of charging."""
        self.battery = min(100.0, self.battery + BATTERY_CHARGE_PER_TICK)

        if self.battery >= 95.0:
            # Fully charged — release dock and resume
            self.model.charging_agent.release_robot(self.robot_id)
            self.status = "IDLE"
            self.current_path = []
            self.path_index = 0

            self.model.log_message(
                from_agent=f"Robot-{self.robot_id}",
                to_agent="ChargingAgent",
                payload={"action": "charge_complete", "battery": self.battery},
            )
