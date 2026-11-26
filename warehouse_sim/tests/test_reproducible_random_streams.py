"""Regression tests for independent, reproducible environmental RNG streams."""
from warehouse_sim.model import WarehouseModel


def _task_trace(model):
    return [(t.task_id, t.arrival_tick, t.sku, t.qty, t.priority)
            for t in model.order_agent.all_tasks]


def test_customer_order_trace_is_independent_of_allocation_mode():
    traces = []
    for mode in ("centralized", "auction"):
        model = WarehouseModel(seed=2026)
        model.fleet_manager.set_allocation_mode(mode)
        for _ in range(80):
            model.step()
        traces.append(_task_trace(model))
    assert traces[0] == traces[1]


def test_inventory_initialization_is_reproducible_for_same_seed():
    a = WarehouseModel(seed=17)
    b = WarehouseModel(seed=17)
    assert a.inventory_agent.shelf_state == b.inventory_agent.shelf_state


def test_workload_rng_stream_is_reproducible():
    a = WarehouseModel(seed=91)
    b = WarehouseModel(seed=91)
    values_a = [a.workload_rng.random() for _ in range(10)]
    values_b = [b.workload_rng.random() for _ in range(10)]
    assert values_a == values_b
