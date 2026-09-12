"""Tests for E-Way Bill JSON generation."""
import json
import pytest

# Ensure the backend directory is on sys.path for direct imports
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from eway_bill import (
    generate_eway_bill_data,
    generate_eway_bill_bytes,
    extract_pincode,
    extract_city,
    normalize_vehicle_no,
    map_transport_mode,
    normalize_date,
)


SAMPLE_PO = {
    "po_number": "2220011455",
    "client_name": "SIYARAM SILK MILLS LTD.",
    "client_gstin": "29AAACS6995D2ZX",
    "client_state": "Karnataka",
    "client_state_code": "29",
    "billing_address": "SIYARAM SILK MILLS LIMITED ZECODE BANGLORE PLOT NO. 2J/2K, 3RD PHASE KIADB OBEDENAHALLI INDUSTRIAL AREA BANGLORE, KARNATAKA DODDABALLAPUR 561203",
    "shipping_address": "SIYARAM SILK MILLS LIMITED ZECODE BANGLORE PLOT NO. 2J/2K, 3RD PHASE KIADB OBEDENAHALLI INDUSTRIAL AREA BANGLORE, KARNATAKA DODDABALLAPUR 561203",
    "cgst_rate": 0,
    "sgst_rate": 0,
    "igst_rate": 5,
}

SAMPLE_LINE_ITEMS = [
    {
        "style_code": "SSK_00034",
        "po_style_code": "5ZE1026WFFLT-0-0602",
        "description": "5ZE1026WFFLT-0-0602 CREAM",
        "color": "CREAM",
        "hsn_code": "64029990",
        "quantity": 520,
        "unit_price": 198.0,
        "amount": 102960.0,
        "mrp": "",
    }
]

SAMPLE_TOTALS = {
    "subtotal": 102960.0,
    "total_quantity": 520,
    "cgst_amount": 0.0,
    "sgst_amount": 0.0,
    "igst_amount": 5148.0,
    "cgst_rate": 0,
    "sgst_rate": 0,
    "igst_rate": 5,
    "grand_total": 108108.0,
    "net_amount": 108108.0,
}


def test_extract_pincode():
    assert extract_pincode("DODDABALLAPUR 561203") == "561203"
    assert extract_pincode("CHEMBUR, MUMBAI-400071") == "400071"
    assert extract_pincode("NO PIN HERE") is None
    assert extract_pincode("") is None
    assert extract_pincode("PREFIX 012345 SUFFIX") is None


def test_extract_city():
    assert extract_city("PLOT 2J/2K, OBEDENAHALLI INDUSTRIAL AREA BANGLORE, KARNATAKA DODDABALLAPUR 561203") != ""
    city = extract_city("Shree Nilaya, Beml Nagar, KARNATAKA 562160")
    assert city and not city.isdigit()


def test_normalize_vehicle_no():
    assert normalize_vehicle_no("MH-01-AB-1234") == "MH01AB1234"
    assert normalize_vehicle_no("mh 01 ab 1234") == "MH01AB1234"
    assert normalize_vehicle_no("") == ""


def test_map_transport_mode():
    assert map_transport_mode("Road") == 1
    assert map_transport_mode("rail") == 2
    assert map_transport_mode("Air") == 3
    assert map_transport_mode("Ship") == 4
    assert map_transport_mode("1") == 1
    assert map_transport_mode("3") == 3
    assert map_transport_mode("") == 1
    assert map_transport_mode("By Road") == 1


def test_generate_eway_bill_data_structure():
    """Verify top-level JSON structure matches NIC Bulk Generation schema v1.0.0621."""
    data = generate_eway_bill_data(
        po=SAMPLE_PO,
        line_items=SAMPLE_LINE_ITEMS,
        totals=SAMPLE_TOTALS,
        invoice_no="SSK26-27-020",
        invoice_date="11/09/2026",
        transport_mode="Road",
        vehicle_no="MH-01-AB-1234",
        transporter="SPEEDY LOGISTICS",
        transporter_id="27AABCT1234A1Z5",
        trans_distance=1000,
        vehicle_type="R",
        to_pincode="561203",
        to_place="Doddaballapur",
    )

    # Top-level structure
    assert "version" in data
    assert data["version"] == "1.0.0621"
    assert "billLists" in data
    assert isinstance(data["billLists"], list)
    assert len(data["billLists"]) == 1

    bill = data["billLists"][0]

    # Supply & doc type
    assert bill["supplyType"] == "O"
    assert bill["subSupplyType"] == 1
    assert bill["subSupplyDesc"] == ""
    assert bill["docType"] == "INV"
    assert bill["docNo"] == "SSK26-27-020"
    assert bill["docDate"] == "11/09/2026"
    assert bill["transType"] == 1

    # From (SSK / Supplier)
    assert bill["fromGstin"] == "27AFKFS4410F1Z2"
    assert bill["fromPlace"] == "MUMBAI"
    assert bill["fromPincode"] == 400071
    assert bill["fromStateCode"] == 27
    assert bill["actualFromStateCode"] == 27

    # To (Buyer / Client)
    assert bill["toGstin"] == "29AAACS6995D2ZX"
    assert bill["toTrdName"] == "SIYARAM SILK MILLS LTD."
    assert bill["toPlace"] == "DODDABALLAPUR"
    assert bill["toPincode"] == 561203
    assert bill["toStateCode"] == 29
    assert bill["actualToStateCode"] == 29

    # Values
    assert bill["totalValue"] == 102960.0
    assert bill["cgstValue"] == 0.0
    assert bill["sgstValue"] == 0.0
    assert bill["igstValue"] == 5148.0
    assert bill["totInvValue"] == 108108.0
    assert bill["cessValue"] == 0
    assert bill["TotNonAdvolVal"] == 0
    assert bill["OthValue"] == 0

    # Transport
    assert bill["transMode"] == 1
    assert bill["vehicleNo"] == "MH01AB1234"
    assert bill["vehicleType"] == "R"
    assert bill["transDistance"] == 1000
    assert bill["transporterName"] == "SPEEDY LOGISTICS"
    assert bill["transporterId"] == "27AABCT1234A1Z5"
    assert bill["transDocNo"] == ""
    assert bill["transDocDate"] == "11/09/2026"

    # Item list
    assert "itemList" in bill
    assert len(bill["itemList"]) == 1
    item = bill["itemList"][0]
    assert item["itemNo"] == 1
    assert item["productName"] == "5ZE1026WFFLT-0-0602 CREAM"
    assert item["hsnCode"] == "64029990"
    assert item["quantity"] == 520
    assert item["qtyUnit"] == "PRS"
    assert item["taxableAmount"] == 102960.0
    assert item["igstRate"] == -1
    assert item["cgstRate"] == -1
    assert item["sgstRate"] == -1
    assert item["cessRate"] == -1
    assert item["cessNonAdvol"] == -1

    # Main HSN
    assert bill["mainHsnCode"] == 64029990


def test_user_exact_sample_payload():
    """Verify exact match with user supplied format."""
    po = {
        "client_gstin": "29AAACS6995D2ZX",
        "client_name": "SIYARAM SILK MILLS LTD",
        "shipping_address": "SIYARAM SILK MILLS LIMITED ZECODE, BANGLORE PLOT NO. 2J/2K, 3RD PHASE KIADB OBEDENAHALLI INDUSTRIAL AREA BANGLORE, KARNATAKA 561203",
        "client_state_code": 29,
    }
    line_items = [
        {
            "product_name": "FOOTWEAR",
            "description": "WOMENS FOOTWEAR",
            "hsn_code": "64029990",
            "quantity": 100,
            "amount": 10000,
        }
    ]
    totals = {
        "subtotal": 10000,
        "cgst": 0,
        "sgst": 0,
        "igst": 500,
        "grand_total": 10500,
    }
    data = generate_eway_bill_data(
        po=po,
        line_items=line_items,
        totals=totals,
        invoice_no="SSK26-27-037",
        invoice_date="26/08/2026",
        transport_mode="1",
        vehicle_no="KA01AD3323",
        trans_distance=900,
        vehicle_type="R",
        to_place="BANGLORE",
        to_pincode="561203",
    )
    b = data["billLists"][0]
    assert data["version"] == "1.0.0621"
    assert b["userGstin"] == "27AFKFS4410F1Z2"
    assert b["supplyType"] == "O"
    assert b["subSupplyType"] == 1
    assert b["subSupplyDesc"] == ""
    assert b["docType"] == "INV"
    assert b["docNo"] == "SSK26-27-037"
    assert b["docDate"] == "26/08/2026"
    assert b["transType"] == 1
    assert b["fromGstin"] == "27AFKFS4410F1Z2"
    assert b["fromTrdName"] == ""
    assert b["fromAddr1"] == "REHAB BLDG  F WING JAY AMBE SRA,NEAR SHELL COLONY"
    assert b["fromAddr2"] == "CHEMBUR"
    assert b["fromPlace"] == "MUMBAI"
    assert b["fromPincode"] == 400071
    assert b["fromStateCode"] == 27
    assert b["actualFromStateCode"] == 27
    assert b["toGstin"] == "29AAACS6995D2ZX"
    assert b["toTrdName"] == "SIYARAM SILK MILLS LTD"
    assert b["toPlace"] == "BANGLORE"
    assert b["toPincode"] == 561203
    assert b["toStateCode"] == 29
    assert b["actualToStateCode"] == 29
    assert b["totalValue"] == 10000
    assert b["cgstValue"] == 0
    assert b["sgstValue"] == 0
    assert b["igstValue"] == 500
    assert b["cessValue"] == 0
    assert b["TotNonAdvolVal"] == 0
    assert b["OthValue"] == 0
    assert b["totInvValue"] == 10500
    assert b["transMode"] == 1
    assert b["transDistance"] == 900
    assert b["transDocDate"] == "26/08/2026"
    assert b["vehicleNo"] == "KA01AD3323"
    assert b["vehicleType"] == "R"
    assert b["mainHsnCode"] == 64029990
    assert b["itemList"] == [
        {
            "itemNo": 1,
            "productName": "FOOTWEAR",
            "productDesc": "WOMENS FOOTWEAR",
            "hsnCode": "64029990",
            "quantity": 100,
            "qtyUnit": "PRS",
            "taxableAmount": 10000,
            "sgstRate": -1,
            "cgstRate": -1,
            "igstRate": -1,
            "cessRate": -1,
            "cessNonAdvol": -1,
        }
    ]


def test_generate_eway_bill_data_auto_pincode_extraction():
    """When to_pincode is not provided, it should be extracted from the address."""
    data = generate_eway_bill_data(
        po=SAMPLE_PO,
        line_items=SAMPLE_LINE_ITEMS,
        totals=SAMPLE_TOTALS,
        invoice_no="SSK26-27-020",
        invoice_date="11/09/2026",
    )
    bill = data["billLists"][0]
    assert bill["toPincode"] == 561203


def test_generate_eway_bill_data_defaults():
    """Test sane defaults when optional fields are omitted."""
    data = generate_eway_bill_data(
        po=SAMPLE_PO,
        line_items=SAMPLE_LINE_ITEMS,
        totals=SAMPLE_TOTALS,
        invoice_no="TEST-001",
        invoice_date="01/01/2026",
    )
    bill = data["billLists"][0]
    assert bill["transMode"] == 1
    assert bill["vehicleType"] == "R"
    assert bill["vehicleNo"] == ""
    assert bill["transporterId"] == ""
    assert bill["transDistance"] == 0


def test_generate_eway_bill_bytes_valid_json():
    """Bytes output must be valid JSON."""
    raw = generate_eway_bill_bytes(
        po=SAMPLE_PO,
        line_items=SAMPLE_LINE_ITEMS,
        totals=SAMPLE_TOTALS,
        invoice_no="SSK26-27-020",
        invoice_date="11/09/2026",
    )
    assert isinstance(raw, bytes)
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["version"] == "1.0.0621"
    assert len(parsed["billLists"]) == 1


def test_multiple_line_items():
    """Test with multiple line items in a single bill."""
    items = [
        {"style_code": "A", "po_style_code": "EXT-A", "color": "RED", "hsn_code": "64029990",
         "quantity": 100, "unit_price": 200, "amount": 20000},
        {"style_code": "B", "po_style_code": "EXT-B", "color": "BLUE", "hsn_code": "64029990",
         "quantity": 200, "unit_price": 150, "amount": 30000},
    ]
    totals = {
        "subtotal": 50000, "cgst_amount": 0, "sgst_amount": 0, "igst_amount": 2500,
        "cgst_rate": 0, "sgst_rate": 0, "igst_rate": 5, "grand_total": 52500,
    }
    data = generate_eway_bill_data(
        po=SAMPLE_PO, line_items=items, totals=totals,
        invoice_no="TEST-002", invoice_date="15/03/2026",
    )
    bill = data["billLists"][0]
    assert len(bill["itemList"]) == 2
    assert bill["itemList"][0]["itemNo"] == 1
    assert bill["itemList"][1]["itemNo"] == 2
    assert bill["itemList"][0]["productName"] == "EXT-A RED"
    assert bill["itemList"][1]["productName"] == "EXT-B BLUE"
    assert bill["totalValue"] == 50000
    assert bill["totInvValue"] == 52500


def test_normalize_date():
    assert normalize_date("2026-09-11") == "11/09/2026"
    assert normalize_date("2026-09-11T10:30:00Z") == "11/09/2026"
    assert normalize_date("11/09/2026") == "11/09/2026"
    assert normalize_date("11-09-2026") == "11/09/2026"
    assert normalize_date("2026/09/11") == "11/09/2026"
    assert normalize_date("") == ""


def test_client_state_inferred_from_gstin():
    po = dict(SAMPLE_PO)
    po["client_state_code"] = None
    po["client_gstin"] = "29AAACS6995D2ZX"
    data = generate_eway_bill_data(
        po=po, line_items=SAMPLE_LINE_ITEMS, totals=SAMPLE_TOTALS,
        invoice_no="TEST-004", invoice_date="2026-09-11",
    )
    bill = data["billLists"][0]
    assert bill["toStateCode"] == 29
    assert bill["actualToStateCode"] == 29
    assert bill["docDate"] == "11/09/2026"


def test_resilient_totals_keys():
    db_totals = {
        "subtotal": 10000.0,
        "cgst": 0.0,
        "sgst": 0.0,
        "igst": 500.0,
        "grand_total": 10500.0,
    }
    data = generate_eway_bill_data(
        po=SAMPLE_PO, line_items=SAMPLE_LINE_ITEMS, totals=db_totals,
        invoice_no="TEST-005", invoice_date="11/09/2026",
    )
    bill = data["billLists"][0]
    assert bill["igstValue"] == 500.0
    assert bill["cgstValue"] == 0.0
