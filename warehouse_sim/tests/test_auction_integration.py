
from warehouse_sim.model import WarehouseModel
from warehouse_sim.agents.order_agent import Task


def make_task(task_id=9001, shelf=(3, 4)):
    return Task(
        priority_rank=1,
        arrival_tick=0,
        task_id=task_id,
        sku="SKU-TEST",
        qty=1,
        priority="normal",
        shelf_location=shelf,
    )


def advance_network_and_agents(model, tick):
    """Advance only message delivery and the two agents under test."""
    model.current_tick = tick
    model.delivered_messages = model.communication.deliver_due(tick)
    model.fleet_manager.sense()
    for robot in model.robots.values():
        if robot.status != "FAILED":
            robot.sense()


def test_assignment_is_sent_over_network_and_acknowledged():
    model = WarehouseModel(seed=1, num_robots=1)
    fm = model.fleet_manager
    robot = model.robots[0]
    task = make_task()


    fm._execute_assignment(0, task)
    assert task.status == "IN_PROGRESS"
    assert task.task_id in fm.pending_assignment_deliveries
    assert robot.current_task is None  # No direct assignment method call.



    advance_network_and_agents(model, 1)
    assert robot.current_task is not None
    assert robot.current_task.task_id == task.task_id
    assert robot.status == "EN_ROUTE_TO_SHELF"



    advance_network_and_agents(model, 2)
    assert task.task_id not in fm.pending_assignment_deliveries
    assert fm.robot_registry[0]["status"] == "EN_ROUTE_TO_SHELF" or fm.robot_registry[0]["status"] == "BUSY"




def test_duplicate_assignment_message_does_not_duplicate_robot_task():
    model = WarehouseModel(seed=2, num_robots=1)
    robot = model.robots[0]
    task = make_task(task_id=9002)
    payload = {"type": "ASSIGNMENT", "task": model.fleet_manager._assignment_payload(task)}



    for _ in range(2):
        model.communication.send(
            sender="FleetManager",
            receiver="Robot-0",
            payload=payload,
            current_tick=0,
        )



    advance_network_and_agents(model, 1)
    assert robot.current_task is not None
    assert robot.current_task.task_id == task.task_id
    assert robot.status == "EN_ROUTE_TO_SHELF"
    # Two ACKs are sent for duplicate deliveries, but the robot accepts the
    # task only once and remains in a single task state.
    ack_messages = [
        m for m in model.communication._in_transit
        if m.payload.get("type") == "ASSIGNMENT_ACK"
    ]
    assert len(ack_messages) == 2




def test_assignment_delivery_retries_after_network_outage():
    model = WarehouseModel(seed=3, num_robots=1)
    fm = model.fleet_manager
    robot = model.robots[0]
    task = make_task(task_id=9003)

    # Outage starts at tick 0, so the first assignment is dropped.
    # After recovery at tick 3, the Fleet Manager's retry should reach the robot.
    model.communication.outage_start = 0
    model.communication.outage_end = 3
    fm._execute_assignment(0, task)
    assert model.communication.messages_dropped >= 1
    assert robot.current_task is None
    assert task.task_id in fm.pending_assignment_deliveries

    for tick in range(1, 4):
        advance_network_and_agents(model, tick)
        fm._retry_assignment_deliveries()

    assert robot.current_task is None  # Retry sent at recovery tick; not yet delivered.
    advance_network_and_agents(model, 4)
    assert robot.current_task is not None
    assert robot.current_task.task_id == task.task_id
    advance_network_and_agents(model, 5)
    assert task.task_id not in fm.pending_assignment_deliveries
