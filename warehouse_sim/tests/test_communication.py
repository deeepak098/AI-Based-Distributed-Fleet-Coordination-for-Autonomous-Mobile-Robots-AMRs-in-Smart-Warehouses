from warehouse_sim.communication import CommunicationSystem


def test_normal_message_delivered_immediately():
    network = CommunicationSystem()

    network.send("A", "B", {"action": "hello"}, current_tick=1)
    delivered = network.deliver_due(current_tick=1)

    assert len(delivered) == 1
    assert delivered[0].sender == "A"
    assert delivered[0].receiver == "B"
    assert network.messages_delivered == 1


def test_latency_delays_message():
    network = CommunicationSystem(latency_ticks=3)

    network.send("A", "B", {"action": "hello"}, current_tick=1)

    assert network.deliver_due(current_tick=1) == []
    assert network.deliver_due(current_tick=2) == []
    assert network.deliver_due(current_tick=3) == []
    delivered = network.deliver_due(current_tick=4)

    assert len(delivered) == 1
    assert delivered[0].delivered_tick == 4
    assert network.messages_delayed == 1


def test_messages_sent_during_outage_are_dropped():
    network = CommunicationSystem(outage_start=3, outage_end=6)

    message = network.send(
        "A", "B", {"action": "hello"}, current_tick=4
    )

    assert message is None
    assert network.messages_dropped == 1
    assert network.messages_sent == 1


def test_in_transit_message_held_during_outage_then_delivered():
    network = CommunicationSystem(
        latency_ticks=1,
        outage_start=3,
        outage_end=5,
    )

    network.send("A", "B", {"action": "hello"}, current_tick=2)

    assert network.deliver_due(current_tick=3) == []
    assert network.messages_held_by_outage == 1
    assert network.get_in_transit_count() == 1

    assert network.deliver_due(current_tick=4) == []
    assert network.messages_held_by_outage == 1

    delivered = network.deliver_due(current_tick=5)

    assert len(delivered) == 1
    assert delivered[0].delivered_tick == 5
    assert network.messages_delivered == 1
    assert network.get_in_transit_count() == 0
