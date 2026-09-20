import os
import sys
import pytest
from collections import Counter

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from routes.online_returns_engine import (
    classify_return_reason,
    parse_sku_details,
    REASON_CATEGORIES,
)

SAMPLE_RETURNS_CSV = r"C:\Users\Dell\Downloads\AugReturn.csv"


def test_classify_return_reason():
    assert classify_return_reason("Size too small", "Return") == "SIZING_FIT"
    assert classify_return_reason("I did not like the fit", "Return") == "SIZING_FIT"
    assert classify_return_reason("", "RTO") == "COURIER_RTO"
    assert classify_return_reason("Product was defective", "Return") == "QUALITY_DEFECT"
    assert classify_return_reason("Color is different", "Return") == "CATALOG_MISMATCH"
    assert classify_return_reason("Received a completely different product", "Return") == "DISPATCH_ERROR"
    assert classify_return_reason("I do not need it anymore", "Return") == "BUYER_REMORSE"
    assert classify_return_reason("Random reason", "Return") == "OTHER"


def test_parse_sku_details():
    res1 = parse_sku_details("CC-0003-TN-38")
    assert res1["size"] == "38"
    assert res1["color"] == "TN"
    assert "CC_0003" in res1["style_code"] or "CC-0003" in res1["style_code"]

    res2 = parse_sku_details("FL_AK_008_GO-8")
    assert res2["size"] == "8"
    assert res2["color"] == "GO"

    res3 = parse_sku_details("")
    assert res3["style_code"] == "UNKNOWN"


def test_aug_returns_csv_if_available():
    if not os.path.exists(SAMPLE_RETURNS_CSV):
        pytest.skip(f"AugReturn.csv not found at {SAMPLE_RETURNS_CSV}")

    import csv
    with open(SAMPLE_RETURNS_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) > 0
    cats = Counter(classify_return_reason(r.get("return_reason"), r.get("status")) for r in rows)

    assert cats["SIZING_FIT"] > 0
    assert cats["COURIER_RTO"] > 0
    assert cats["QUALITY_DEFECT"] > 0
