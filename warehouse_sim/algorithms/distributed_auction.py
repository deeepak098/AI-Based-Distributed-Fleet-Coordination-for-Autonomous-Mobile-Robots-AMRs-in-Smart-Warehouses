
"""
Auction-based task allocation for the warehouse fleet.

Robots independently calculate bids using the common scoring formula:
    Cost = 0.4 * Distance + 0.4 * Energy - 0.2 * Urgency

The lowest eligible bid wins.
"""

from dataclasses import dataclass
from typing import Optional


# Common scoring weights used by both centralized and auction allocation.
DISTANCE_WEIGHT = 0.4
ENERGY_WEIGHT = 0.4
PRIORITY_WEIGHT = 0.2


@dataclass
class Bid:
    robot_id: int
    task_id: int
    cost: float


class DistributedAuction:

    def __init__(
        self,
        distance_weight: float = DISTANCE_WEIGHT,
        energy_weight: float = ENERGY_WEIGHT,
        priority_weight: float = PRIORITY_WEIGHT,
    ):
        self.distance_weight = distance_weight
        self.energy_weight = energy_weight
        self.priority_weight = priority_weight

    def calculate_bid(
        self,
        robot_id: int,
        task_id: int,
        distance_score: float,
        energy_score: float,
        workload_score: float = 0.0,
        urgency_score: float = 0.0,
    ) -> Optional[Bid]:
        """
        Calculate a robot's bid using distance, battery, and urgency.

        workload_score is retained for backward compatibility with older
        callers, but is intentionally excluded from the scoring formula.
        """

        scores = [distance_score, energy_score, urgency_score]

        # Reject invalid scores.
        if any(not 0 <= score <= 1 for score in scores):
            return None

        # Common formula shared with centralized task allocation.
        cost = (
            self.distance_weight * distance_score
            + self.energy_weight * energy_score
            - self.priority_weight * urgency_score
        )

        return Bid(robot_id, task_id, cost)

    @staticmethod
    def select_winner(bids: list[Bid]) -> Optional[Bid]:
        """Select the lowest-cost bid. Break ties using robot ID."""

        if not bids:
            return None

        return min(bids, key=lambda bid: (bid.cost, bid.robot_id))
