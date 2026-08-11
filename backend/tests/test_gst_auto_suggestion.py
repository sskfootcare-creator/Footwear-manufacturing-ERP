"""Tests for footwear GST rate threshold config and auto-suggestion logic."""
import pytest
from server import FOOTWEAR_GST_CONFIG, suggest_gst_pct, compute_style_costing


def test_gst_config_threshold_values():
    """Verify GST threshold config is set to confirmed footwear threshold values."""
    assert FOOTWEAR_GST_CONFIG["threshold"] == 2500.0
    assert FOOTWEAR_GST_CONFIG["rate_below_or_equal"] == 5.0
    assert FOOTWEAR_GST_CONFIG["rate_above"] == 18.0


def test_suggest_gst_pct_below_threshold():
    """Verify suggest_gst_pct returns 5% for price <= 2500."""
    assert suggest_gst_pct(0) == 5.0
    assert suggest_gst_pct(500) == 5.0
    assert suggest_gst_pct(2500.0) == 5.0


def test_suggest_gst_pct_above_threshold():
    """Verify suggest_gst_pct returns 18% for price > 2500."""
    assert suggest_gst_pct(2500.01) == 18.0
    assert suggest_gst_pct(3000) == 18.0
    assert suggest_gst_pct(5000) == 18.0


def test_compute_style_costing_auto_suggests_gst():
    """Verify compute_style_costing auto-suggests GST % if gst_pct is omitted/None."""
    # Style with low cost (target price = 100 + 25 = 125 <= 2500)
    low_cost_style = {
        "bom": [{"rate": 100, "quantity": 1}],
        "margin_pct": 25,
        "gst_pct": None,
    }
    c_low = compute_style_costing(low_cost_style)
    assert c_low["suggested_target_price"] == 125.0
    assert c_low["gst_amount"] == 6.25  # 5% of 125

    # Style with high cost (target price = 2400 + 600 = 3000 > 2500)
    high_cost_style = {
        "bom": [{"rate": 2400, "quantity": 1}],
        "margin_pct": 25,
        "gst_pct": None,
    }
    c_high = compute_style_costing(high_cost_style)
    assert c_high["suggested_target_price"] == 3000.0
    assert c_high["gst_amount"] == 540.0  # 18% of 3000


def test_compute_style_costing_preserves_manual_override():
    """Verify compute_style_costing respects explicit manual override of gst_pct."""
    style_with_override = {
        "bom": [{"rate": 100, "quantity": 1}],
        "margin_pct": 25,
        "gst_pct": 12.0,  # Manual override
    }
    costing = compute_style_costing(style_with_override)
    assert costing["gst_amount"] == 15.0  # 12% of 125, not 5%
