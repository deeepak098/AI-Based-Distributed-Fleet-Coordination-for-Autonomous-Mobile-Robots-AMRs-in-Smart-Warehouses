from warehouse_sim.communication import CommunicationSystem
from warehouse_sim.algorithms.distributed_auction import Bid, DistributedAuction


def run_message_auction(latency_ticks=0, outage_start=None, outage_end=None):
    """Isolated message-based auction prototype, not the warehouse simulation."""
    network = CommunicationSystem(
        latency_ticks=latency_ticks,
        outage_start=outage_start,
        outage_end=outage_end,
    )
    auction = DistributedAuction()
    robot_costs = {"Robot-1": 0.55, "Robot-2": 0.30, "Robot-3": 0.42}
    bids_received = []
    robots_that_bid = set()
    task_id = 999

    for robot_id in robot_costs:
        network.send(
            sender="FleetManager",
            receiver=robot_id,
            payload={"action": "bid_request", "task_id": task_id},
            current_tick=1,
        )

    for tick in range(1, 10):
        delivered = network.deliver_due(tick)

        for message in delivered:
            if message.payload.get("action") == "bid_request":
                robot_id = message.receiver
                if robot_id in robots_that_bid:
                    continue

                robots_that_bid.add(robot_id)
                network.send(
                    sender=robot_id,
                    receiver="FleetManager",
                    payload={
                        "action": "bid",
                        "task_id": task_id,
                        "robot_id": robot_id,
                        "cost": robot_costs[robot_id],
                    },
                    current_tick=tick,
                )

            elif message.payload.get("action") == "bid":
                bids_received.append(
                    Bid(
                        robot_id=int(message.payload["robot_id"].split("-")[1]),
                        task_id=message.payload["task_id"],
                        cost=message.payload["cost"],
                    )
                )

        same_tick_replies = network.deliver_due(tick)
        for message in same_tick_replies:
            if message.payload.get("action") == "bid":
                bids_received.append(
                    Bid(
                        robot_id=int(message.payload["robot_id"].split("-")[1]),
                        task_id=message.payload["task_id"],
                        cost=message.payload["cost"],
                    )
                )

    winner = auction.select_winner(bids_received)
    return {
        "winner": winner,
        "bids_received": bids_received,
        "metrics": network.get_metrics(),
    }


def test_message_auction_selects_lowest_bid():
    result = run_message_auction()

    assert result["winner"] is not None
    assert result["winner"].robot_id == 2
    assert result["winner"].cost == 0.30
    assert len(result["bids_received"]) == 3


def test_message_auction_with_latency_still_selects_winner():
    result = run_message_auction(latency_ticks=1)

    assert result["winner"] is not None
    assert result["winner"].robot_id == 2
    assert len(result["bids_received"]) == 3
    assert result["metrics"]["messages_delayed"] == 6


def test_message_auction_during_outage_gets_no_bids():
    result = run_message_auction(outage_start=1, outage_end=5)

    assert result["winner"] is None
    assert result["bids_received"] == []
    assert result["metrics"]["messages_dropped"] == 3
