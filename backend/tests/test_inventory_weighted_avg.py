"""Unit & integration tests for weighted-average inventory valuation."""
import pytest
from server import _calculate_material_weighted_avg


def test_weighted_avg_two_in_movements_different_rates():
    """Verify: record two 'in' movements for the same material at different rates,
    confirm the computed value reflects the weighted average, not just the latest rate.
    """
    mat = {"_id": "mat_1", "code": "M001", "name": "Synthetic Leather", "rate": 0.0}
    movements = [
        {"material_id": "mat_1", "type": "in", "quantity": 100.0, "rate": 10.0, "created_at": "2026-08-01T10:00:00Z"},
        {"material_id": "mat_1", "type": "in", "quantity": 100.0, "rate": 20.0, "created_at": "2026-08-02T10:00:00Z"},
    ]

    summary = _calculate_material_weighted_avg(mat, movements)

    # 100 @ 10 (value 1000) + 100 @ 20 (value 2000) = 200 units, value 3000 -> weighted avg = 15.0
    assert summary["balance"] == 200.0
    assert summary["weighted_avg_rate"] == 15.0
    assert summary["value"] == 3000.0
    assert summary["last_rate"] == 20.0  # Most recent purchase price tracked separately


def test_weighted_avg_with_consumption_and_replenishment():
    """Verify consumption decreases stock without changing unit cost basis,
    and subsequent purchase correctly updates weighted average.
    """
    mat = {"_id": "mat_2", "code": "M002", "name": "Rubber Sole", "rate": 0.0}
    movements = [
        # In: 100 @ 10 -> balance 100, avg 10.0, val 1000
        {"material_id": "mat_2", "type": "in", "quantity": 100.0, "rate": 10.0, "created_at": "2026-08-01T09:00:00Z"},
        # Out: 60 units consumed -> balance 40, avg remains 10.0, val 400
        {"material_id": "mat_2", "type": "out", "quantity": 60.0, "rate": None, "created_at": "2026-08-02T09:00:00Z"},
        # In: 60 @ 20 -> balance 100, existing val 400 + new val 1200 = 1600 -> avg 16.0, val 1600
        {"material_id": "mat_2", "type": "in", "quantity": 60.0, "rate": 20.0, "created_at": "2026-08-03T09:00:00Z"},
    ]

    summary = _calculate_material_weighted_avg(mat, movements)

    assert summary["balance"] == 100.0
    assert summary["weighted_avg_rate"] == 16.0
    assert summary["value"] == 1600.0
    assert summary["last_rate"] == 20.0


def test_weighted_avg_fallback_to_master_rate_when_no_movements():
    """Verify materials with no movements fallback to master rate."""
    mat = {"_id": "mat_3", "code": "M003", "name": "EVA Sheet", "rate": 55.0}
    movements = []

    summary = _calculate_material_weighted_avg(mat, movements)

    assert summary["balance"] == 0.0
    assert summary["weighted_avg_rate"] == 55.0
    assert summary["value"] == 0.0
    assert summary["last_rate"] == 55.0


def test_weighted_avg_with_adjustments():
    """Verify stock adjustments are properly incorporated."""
    mat = {"_id": "mat_4", "code": "M004", "name": "Eyelets", "rate": 2.0}
    movements = [
        {"material_id": "mat_4", "type": "in", "quantity": 1000.0, "rate": 2.0, "created_at": "2026-08-01T00:00:00Z"},
        # Positive adjustment of 500 @ 3.5
        {"material_id": "mat_4", "type": "adjustment", "quantity": 500.0, "rate": 3.5, "created_at": "2026-08-02T00:00:00Z"},
    ]

    summary = _calculate_material_weighted_avg(mat, movements)

    # 1000 @ 2 (2000) + 500 @ 3.5 (1750) = 1500 units, val 3750 -> avg 2.5
    assert summary["balance"] == 1500.0
    assert summary["weighted_avg_rate"] == 2.5
    assert summary["value"] == 3750.0
