from warehouse_sim.algorithms.distributed_auction import DistributedAuction


def test_lowest_bid_wins():
    auction = DistributedAuction()

    bids = [
        auction.calculate_bid(1, 101, 0.50, 0.30, 0.40),
        auction.calculate_bid(2, 101, 0.15, 0.20, 0.00),
        auction.calculate_bid(3, 101, 0.30, 0.80, 0.60),
        auction.calculate_bid(4, 101, 0.40, 0.35, 0.30),
    ]

    valid_bids = [bid for bid in bids if bid is not None]

    winner = auction.select_winner(valid_bids)

    assert winner is not None
    assert winner.robot_id == 2


def test_empty_auction():
    auction = DistributedAuction()

    winner = auction.select_winner([])

    assert winner is None


def test_invalid_score_rejected():
    auction = DistributedAuction()

    bid = auction.calculate_bid(
        robot_id=1,
        task_id=101,
        distance_score=1.5,
        energy_score=0.2,
        workload_score=0.1,
    )

    assert bid is None


def test_tie_breaking():
    auction = DistributedAuction()

    bids = [
        auction.calculate_bid(3, 101, 0.2, 0.2, 0.2),
        auction.calculate_bid(1, 101, 0.2, 0.2, 0.2),
    ]

    valid_bids = [bid for bid in bids if bid is not None]

    winner = auction.select_winner(valid_bids)

    assert winner is not None
    assert winner.robot_id == 1