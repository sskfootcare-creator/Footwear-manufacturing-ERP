import pytest
from routes.online_returns_engine import (
    classify_return_reason,
    parse_sku_details,
    get_footwear_placeholder_image,
)

def test_classify_return_reason():
    assert classify_return_reason("Size is different", "RETURN") == "SIZING_FIT"
    assert classify_return_reason("Product was defective", "RETURN") == "QUALITY_DEFECT"
    assert classify_return_reason("Product image was better than the actual product", "RETURN") == "CATALOG_MISMATCH"
    assert classify_return_reason("Received a completely different product", "RETURN") == "DISPATCH_ERROR"
    assert classify_return_reason("I do not need it anymore", "RETURN") == "BUYER_REMORSE"
    assert classify_return_reason("", "RTO") == "COURIER_RTO"
    assert classify_return_reason("Courier return", "RETURN") == "COURIER_RTO"

def test_parse_sku_details():
    res1 = parse_sku_details("FLL_AK_005_GO-7")
    assert res1["style_code"] == "FLL_AK_005"
    assert res1["color"] == "GO"
    assert res1["size"] == "7"

    res2 = parse_sku_details("CC-058-BR-38")
    assert res2["style_code"] == "CC_058"
    assert res2["color"] == "BR"
    assert res2["size"] == "38"

    res3 = parse_sku_details("SLIDE-01-9")
    assert res3["style_code"] == "SLIDE-01"
    assert res3["size"] == "9"

def test_get_footwear_placeholder_image():
    assert get_footwear_placeholder_image("SLIDE_101") == "/company/braided_slide.jpg"
    assert get_footwear_placeholder_image("FLL_AK_005") == "/company/laser_cut_flat.jpg"
    assert get_footwear_placeholder_image("CC_0003") == "/company/laser_cut_flat.jpg"
    assert get_footwear_placeholder_image("ETHNIC_JUTTI_01") == "/company/ethnic_embroidered.jpg"
    assert get_footwear_placeholder_image("DERBY_BLACK") == "/company/black_derby.jpg"
    assert get_footwear_placeholder_image("OXFORD_TAN") == "/company/classic_oxford.jpg"
