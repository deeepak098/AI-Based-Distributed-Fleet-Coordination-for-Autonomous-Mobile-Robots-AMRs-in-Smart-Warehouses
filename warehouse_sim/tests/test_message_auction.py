from warehouse_sim.communication import CommunicationSystem
from warehouse_sim.algorithms.distributed_auction import Bid, DistributedAuction


def calculate_robot_bid(robot_id, robot_pos, battery, task_location, is_urgent):
    """Calculate a bid using the warehouse project's shared scoring formula."""

    distance = (
        abs(robot_pos[0] - task_location[0])
        + abs(robot_pos[1] - task_location[1])
    )

    distance_score = min(distance / 38.0, 1.0)
    energy_score = 1.0 - (battery / 100.0)
    urgency_score = 1.0 if is_urgent else 0.0

    auction = DistributedAuction()

    return auction.calculate_bid(
        robot_id=robot_id,
        task_id=999,
        distance_score=distance_score,
        energy_score=energy_score,
        urgency_score=urgency_score,
    )


def run_message_auction(latency_ticks=0, outage_start=None, outage_end=None):
    network = CommunicationSystem(
        latency_ticks=latency_ticks,
        outage_start=outage_start,
        outage_end=outage_end,
    )

    auction = DistributedAuction()

    robots = {
        "Robot-1": {"pos": (0, 0), "battery": 80},
        "Robot-2": {"pos": (4, 4), "battery": 90},
        "Robot-3": {"pos": (10, 10), "battery": 50},
    }

    task_location = (5, 5)
    is_urgent = False
    task_id = 999

    bids_received = []
    robots_that_bid = set()

    # Fleet Manager sends bid requests to all robots.
    for robot_id in robots:
        network.send(
            sender="FleetManager",
            receiver=robot_id,
            payload={
                "action": "bid_request",
                "task_id": task_id,
                "task_location": task_location,
                "is_urgent": is_urgent,
            },
            current_tick=1,
        )

    # Simulate message processing over multiple ticks.
    for tick in range(1, 10):
        delivered = network.deliver_due(tick)

        for message in delivered:
            action = message.payload.get("action")

            # Robot receives a request and calculates its own bid.
            if action == "bid_request":
                robot_id = message.receiver

                if robot_id in robots_that_bid:
                    continue

                robots_that_bid.add(robot_id)

                robot_data = robots[robot_id]

                bid = calculate_robot_bid(
                    robot_id=int(robot_id.split("-")[1]),
                    robot_pos=robot_data["pos"],
                    battery=robot_data["battery"],
                    task_location=message.payload["task_location"],
                    is_urgent=message.payload["is_urgent"],
                )

                if bid is not None:
                    network.send(
                        sender=robot_id,
                        receiver="FleetManager",
                        payload={
                            "action": "bid",
                            "task_id": task_id,
                            "robot_id": robot_id,
                            "cost": bid.cost,
                        },
                        current_tick=tick,
                    )

            # Fleet Manager receives a robot's bid.
            elif action == "bid":
                bids_received.append(
                    Bid(
                        robot_id=int(message.payload["robot_id"].split("-")[1]),
                        task_id=message.payload["task_id"],
                        cost=message.payload["cost"],
                    )
                )

        # Process messages created during the current tick
        # when zero-latency communication is configured.
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


def test_message_auction_selects_lowest_realistic_bid():
    result = run_message_auction()

    assert result["winner"] is not None
    assert result["winner"].robot_id == 2
    assert len(result["bids_received"]) == 3


def test_message_auction_with_latency():
    result = run_message_auction(latency_ticks=1)

    assert result["winner"] is not None
    assert result["winner"].robot_id == 2
    assert len(result["bids_received"]) == 3
    assert result["metrics"]["messages_delayed"] == 6


def test_message_auction_during_outage():
    result = run_message_auction(outage_start=1, outage_end=5)

    assert result["winner"] is None
    assert result["bids_received"] == []
    assert result["metrics"]["messages_dropped"] == 3


def test_urgent_task_changes_bid_scores():
    normal_bid = calculate_robot_bid(
        robot_id=1,
        robot_pos=(5, 5),
        battery=100,
        task_location=(5, 5),
        is_urgent=False,
    )

    urgent_bid = calculate_robot_bid(
        robot_id=1,
        robot_pos=(5, 5),
        battery=100,
        task_location=(5, 5),
        is_urgent=True,
    )

    assert urgent_bid.cost < normal_bid.cost
    assert round(normal_bid.cost, 2) == 0.00
    assert round(urgent_bid.cost, 2) == -0.20
