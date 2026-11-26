"""
Full Shock Cycle Integration Test.

Validates:
    Run 100 ticks, fire all 5 shocks at predetermined ticks, and assert the
    model never throws and core invariants hold:
    - No unhandled exceptions
    - Collision count stays at 0
    - Shock recovery is tracked accurately (pending/recovered/failed)
    - Model state remains consistent
"""

import pytest

from warehouse_sim.model import WarehouseModel
from warehouse_sim.events import (
    kill_robot,
    block_cell,
    force_drain,
    flood_urgent_orders,
    inject_deadlock,
)



class TestFullShockCycle:
    """Integration tests exercising shock injection and continued simulation."""



    def test_100_ticks_with_all_shocks(self):
        """Run 100 ticks with all five shocks and validate tracking/invariants."""
        model = WarehouseModel()
        shock_results = []

        for tick in range(1, 101):
            model.step()

            if tick == 15:
                shock_results.append(("robot_failure", kill_robot(model, 0)))
            if tick == 30:
                shock_results.append(("blocked_aisle", block_cell(model, (5, 6))))
            if tick == 45:
                shock_results.append(("battery_failure", force_drain(model, 1)))
            if tick == 60:
                shock_results.append(("order_flood", flood_urgent_orders(model, 8)))
            if tick == 75:
                shock_results.append(("deadlock_injection", inject_deadlock(model)))

        # All five shock injection calls were made.
        assert len(shock_results) == 5



        # A shock injection may report an error when its preconditions cannot be
        # met (e.g., insufficient available robots for a deadlock scenario).
        for shock_type, result in shock_results:
            assert "error" not in result, f"Shock injection {shock_type} errored: {result}"



        # All shocks should be registered in the recovery tracker.
        assert model.shocks_triggered >= 5



        # Recovery is not assumed to happen instantly. Each registered shock
        # must be in exactly one state: pending, recovered, or failed.
        assert model.shock_recovery_successes >= 0
        assert model.shock_recovery_failures >= 0
        assert model.shock_recovery_pending >= 0
        assert (
            model.shock_recovery_successes
            + model.shock_recovery_failures
            + model.shock_recovery_pending
            == model.shocks_triggered
        ), "Shock recovery accounting is inconsistent"



        # The legacy recovered counter should reflect verified successes only.
        assert model.shocks_recovered == model.shock_recovery_successes



        # Collision count must remain zero.
        assert model.traffic_controller.collision_count == 0



        # Model remains healthy and reports the final tick.
        kpis = model.get_kpis()
        assert kpis["tick"] == 100
        assert kpis["collision_count"] == 0



        # Grid state remains accessible and correctly sized.
        grid_state = model.get_grid_state()
        assert grid_state["grid_width"] == 20
        assert grid_state["grid_height"] == 20



        # Messages/events should have been logged during the run.
        assert len(model.message_log) > 0



    def test_200_ticks_no_crash(self):
        """Run 200 ticks with no shocks as a baseline stability test."""
        model = WarehouseModel()



        for _ in range(200):
            model.step()



        kpis = model.get_kpis()
        assert kpis["tick"] == 200
        assert kpis["collision_count"] == 0



    def test_rapid_shock_succession(self):
        """Inject three shocks quickly and verify accounting/system stability."""
        model = WarehouseModel()



        for _ in range(20):
            model.step()



        kill_robot(model, 2)
        model.step()



        force_drain(model, 3)
        model.step()



        flood_urgent_orders(model, 5)
        model.step()



        for _ in range(30):
            model.step()



        kpis = model.get_kpis()
        assert kpis["collision_count"] == 0
        assert model.shocks_triggered >= 3
        assert (
            model.shock_recovery_successes
            + model.shock_recovery_failures
            + model.shock_recovery_pending
            == model.shocks_triggered
        ), "Shock recovery accounting is inconsistent after rapid shocks"

        # At least one shock may still be pending; do not require all shocks to
        # have recovered merely because the simulation continued running.



    def test_all_robots_killed_no_crash(self):
        """Killing all robots should not crash the simulation."""
        model = WarehouseModel()



        for _ in range(10):
            model.step()



        for rid in list(model.robots.keys()):
            kill_robot(model, rid)



        for _ in range(20):
            model.step()



        kpis = model.get_kpis()
        assert kpis["robots_failed"] == 5



    def test_multiple_cells_blocked(self):
        """Blocking multiple aisle cells should not crash the system."""
        model = WarehouseModel()



        for _ in range(10):
            model.step()



        cells_to_block = [(5, 5), (5, 7), (10, 10), (15, 15)]
        for cell in cells_to_block:
            block_cell(model, cell)



        for _ in range(50):
            model.step()



        assert len(model.blocked_cells) >= 4
