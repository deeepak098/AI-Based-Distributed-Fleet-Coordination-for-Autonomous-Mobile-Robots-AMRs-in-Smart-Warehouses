"""
Auction-based task allocation for the warehouse fleet.

Robots independently calculate bids.
The lowest eligible bid wins.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Bid:
    robot_id: int
    task_id: int
    cost: float


class DistributedAuction:

    def __init__(
        self,
        distance_weight: float = 0.4,
        energy_weight: float = 0.4,
        workload_weight: float = 0.2,
    ):
        self.distance_weight = distance_weight
        self.energy_weight = energy_weight
        self.workload_weight = workload_weight

    def calculate_bid(
        self,
        robot_id: int,
        task_id: int,
        distance_score: float,
        energy_score: float,
        workload_score: float,
    ) -> Optional[Bid]:

        scores = [distance_score, energy_score, workload_score]

        if any(not 0 <= score <= 1 for score in scores):
            return None

        cost = (
            self.distance_weight * distance_score
            + self.energy_weight * energy_score
            + self.workload_weight * workload_score
        )

        return Bid(robot_id, task_id, cost)

    @staticmethod
    def select_winner(bids: list[Bid]) -> Optional[Bid]:

        if not bids:
            return None

        return min(bids, key=lambda bid: (bid.cost, bid.robot_id))