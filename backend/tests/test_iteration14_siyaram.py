"""Iteration 14: Siyaram multi-page PO extraction regression.

Siyaram POs span multiple pages without repeating the table header row, and
page 3 of the sample has no extractable table at all. The fix adds a
text-block parser (`_siyaram_text_block_parse`) that walks the entire text
stream and pairs each numeric row with its description / material code /
HSN by scanning neighbouring lines. This test pins the expected output for
the sample PO so the behaviour doesn't regress.
"""
from __future__ import annotations

import os
import pytest

from po_extractor_free import extract_po_from_pdf_local, _split_color_size_from_desc

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "siyaram_2220008835.pdf")


@pytest.fixture(scope="module")
def siyaram():
    if not os.path.exists(FIXTURE):
        pytest.skip("Siyaram fixture missing")
    with open(FIXTURE, "rb") as fh:
        return extract_po_from_pdf_local(fh.read())


class TestSiyaramMeta:
    def test_po_number(self, siyaram):
        assert siyaram["po_number"] == "2220008835"

    def test_po_date(self, siyaram):
        assert siyaram["po_date"] == "2026-05-21"

    def test_client_name(self, siyaram):
        assert siyaram["client_name"] == "SIYARAM SILK MILLS LTD."

    def test_vendor_name(self, siyaram):
        # Must NOT pick up the address fragment that follows ``Vendor Code:``
        assert siyaram["vendor_name"] == "SSK FOOTCARE MANUFACTURING LLP"

    def test_currency(self, siyaram):
        assert siyaram["currency"] == "INR"


class TestSiyaramLineItems:
    def test_total_count(self, siyaram):
        """All 32 line items must be parsed (was 10 before the fix)."""
        assert len(siyaram["line_items"]) == 32

    def test_total_quantity(self, siyaram):
        assert sum(li["quantity"] for li in siyaram["line_items"]) == 2088
        assert siyaram["total_quantity"] == 2088

    def test_grand_total(self, siyaram):
        assert siyaram["grand_total"] == 333440.0

    def test_every_item_has_qty_rate(self, siyaram):
        for li in siyaram["line_items"]:
            assert li["quantity"] > 0
            assert li["unit_price"] > 0
            assert li["amount"] > 0

    def test_every_item_has_color_size(self, siyaram):
        """Color/Size must be extracted from space-separated description."""
        for li in siyaram["line_items"]:
            assert li["color"], f"missing color for {li}"
            assert li["size"], f"missing size for {li}"

    def test_every_item_has_style_code(self, siyaram):
        """Material chunks (5ZEZP125WW + FLT11719888) must be joined."""
        for li in siyaram["line_items"]:
            assert li["style_code"], f"missing style_code for {li}"
            # Material code is alphanumeric, length 10..25
            assert 10 <= len(li["style_code"]) <= 25

    def test_first_item(self, siyaram):
        first = siyaram["line_items"][0]
        assert first["quantity"] == 72
        assert first["unit_price"] == 160.0
        assert first["amount"] == 11520.0
        assert first["color"] == "BROWN"
        assert first["size"] == "4"
        assert first["style_code"] == "5ZEZP125WWFLT11719888"

    def test_last_item(self, siyaram):
        last = siyaram["line_items"][-1]
        assert last["quantity"] == 64
        assert last["unit_price"] == 155.0
        assert last["amount"] == 9920.0
        assert last["color"] == "CREAM"
        assert last["size"] == "9"
        assert last["style_code"] == "5ZEZFLWWWFLTM7128465"


class TestSplitColorSize:
    def test_comma_separated_still_works(self):
        """SHEIN-style comma-separated must continue working unchanged."""
        assert _split_color_size_from_desc("SHEINWOMENBLOUSE,BLACK,3") == (
            "SHEINWOMENBLOUSE", "BLACK", "3",
        )
        assert _split_color_size_from_desc("STYLE001,RED") == ("STYLE001", "RED", "")

    def test_space_separated_siyaram(self):
        assert _split_color_size_from_desc("ZP125WWFLT117 BROWN 4") == (
            "ZP125WWFLT117", "BROWN", "4",
        )
        assert _split_color_size_from_desc("ZFLWWWFLTM71 CREAM 9") == (
            "ZFLWWWFLTM71", "CREAM", "9",
        )

    def test_half_size(self):
        assert _split_color_size_from_desc("ZP125WWFLT104 TAN 7.5") == (
            "ZP125WWFLT104", "TAN", "7.5",
        )

    def test_no_structure(self):
        assert _split_color_size_from_desc("") == ("", "", "")
        d, c, s = _split_color_size_from_desc("JUST PLAIN TEXT")
        assert s == ""


SIYARAM_2220011189_TEXT = """
SIYARAM SILK MILLS LTD.
Purchase Order
Registered Office: H3/2 M. I. D. C, Tarapur, Boisar, Tal& Dist- Palghar, Maharashtra,401506
Corporate Office: B-5 Trade World, Kamla City, Lower Parel Mumbai-400013 Maharashtra
Vendor Name & Address: 
SSK FOOTCARE MANUFACTURING LLP 
CHEMBUR MUMBAI - 400071 H 43 , NARAYAN NIWAS, OPP JETVAN 
GARDEN MUMBAI MUMBAI 400071 MAHARASHTRA
P.O. No: 2220011189 Date: 05.08.2026
Vendor Code: 140266
CIN: L17116MH1978PLC020451
Vendor's GST No: 27AFKFS4410F1Z2
Our GST No: 29AAACS6995D2ZX
Billing Address: 
SIYARAM SILK MILLS LIMITED ZECODE BANGLORE 
PLOT NO. 2J/2K, 3RD PHASE KIADB OBEDENAHALLI INDUSTRIAL AREA 
BANGLORE, KARNATAKA DODDABALLAPUR 561
Delivery Address: 
ZECODE-BANGLORE-2220 ZECODE-BANGLORE-2220
PLOT NO. 2J/2K, 3RD PHASE KIADB OBEDENAHALLI INDUSTRIAL 
AREA BANGLORE, KARNATAKA DODDABALLAPUR 561
GST No: Place of Supply: / 
Item Material Material Description Qty UOM Rate Disc CGST/IGST % SGST/UGST % Total Net Value 
(INR)
10
5ZE1026WFF
LT-0-0445BR
WN4
5ZE1026WFFLT-0-0445 
BROWN. 4
DlvrQty: 65.000 Dt: 
15.09.2026 HSN: 64029990
65 PCS 164 0 533 5 0 10,660
20
5ZE1026WFF
LT-0-0445BR
WN5
5ZE1026WFFLT-0-0445 
BROWN. 5
DlvrQty: 130.000 Dt: 
15.09.2026 HSN: 64029990
130 PCS 164 0 1,066 5 0 21,320
30
5ZE1026WFF
LT-0-0445BR
WN6
5ZE1026WFFLT-0-0445 
BROWN. 6
DlvrQty: 130.000 Dt: 
15.09.2026 HSN: 64029990
130 PCS 164 0 1,066 5 0 21,320
40
5ZE1026WFF
LT-0-0445BR
WN7
5ZE1026WFFLT-0-0445 
BROWN. 7
DlvrQty: 130.000 Dt: 
15.09.2026 HSN: 64029990
130 PCS 164 0 1,066 5 0 21,320
50
5ZE1026WFF
LT-0-0445BR
WN8
5ZE1026WFFLT-0-0445 
BROWN. 8
DlvrQty: 65.000 Dt: 
15.09.2026 HSN: 64029990
65 PCS 164 0 533 5 0 10,660
60
5ZE1026WFF
LT-0-0445OF
WT4
5ZE1026WFFLT-0-0445 OFF 
WHITE 4
DlvrQty: 65.000 Dt: 
15.09.2026 HSN: 64029990
65 PCS 164 0 533 5 0 10,660
70
5ZE1026WFF
LT-0-0445OF
WT5
5ZE1026WFFLT-0-0445 OFF 
WHITE 5
DlvrQty: 130.000 Dt: 
15.09.2026 HSN: 64029990
130 PCS 164 0 1,066 5 0 21,320
80
5ZE1026WFF
LT-0-0445OF
WT6
5ZE1026WFFLT-0-0445 OFF 
WHITE 6
DlvrQty: 130.000 Dt: 
15.09.2026 HSN: 64029990
130 PCS 164 0 1,066 5 0 21,320
90
5ZE1026WFF
LT-0-0445OF
WT7
5ZE1026WFFLT-0-0445 OFF 
WHITE 7
DlvrQty: 130.000 Dt: 
15.09.2026 HSN: 64029990
130 PCS 164 0 1,066 5 0 21,320
100
5ZE1026WFF
LT-0-0445OF
WT8
5ZE1026WFFLT-0-0445 OFF 
WHITE 8
DlvrQty: 65.000 Dt: 
15.09.2026 HSN: 64029990
65 PCS 164 0 533 5 0 10,660
110
5ZE1026WFF
LT-0-0446GOL
D4
5ZE1026WFFLT-0-0446 
GOLD 4
DlvrQty: 58.000 Dt: 
15.09.2026 HSN: 64029990
58 PCS 198 0 574.2 5 0 11,484
120
5ZE1026WFF
LT-0-0446GOL
D5
5ZE1026WFFLT-0-0446 
GOLD 5
DlvrQty: 116.000 Dt: 
15.09.2026 HSN: 64029990
116 PCS 198 0 1,148.4 5 0 22,968
130
5ZE1026WFF
LT-0-0446GOL
D6
5ZE1026WFFLT-0-0446 
GOLD 6
DlvrQty: 116.000 Dt: 
15.09.2026 HSN: 64029990
116 PCS 198 0 1,148.4 5 0 22,968
140
5ZE1026WFF
LT-0-0446GOL
D7
5ZE1026WFFLT-0-0446 
GOLD 7
DlvrQty: 116.000 Dt: 
15.09.2026 HSN: 64029990
116 PCS 198 0 1,148.4 5 0 22,968
150
5ZE1026WFF
LT-0-0446GOL
D8
5ZE1026WFFLT-0-0446 
GOLD 8
DlvrQty: 58.000 Dt: 
15.09.2026 HSN: 64029990
58 PCS 198 0 574.2 5 0 11,484
160
5ZE1026WFF
LT-0-0446GOL
D9
5ZE1026WFFLT-0-0446 
GOLD 9
DlvrQty: 58.000 Dt: 
15.09.2026 HSN: 64029990
58 PCS 198 0 574.2 5 0 11,484
170
5ZE1026WFF
LT-0-0446SIL
R4
5ZE1026WFFLT-0-0446 
SILVER 4
DlvrQty: 58.000 Dt: 
15.09.2026 HSN: 64029990
58 PCS 198 0 574.2 5 0 11,484
180
5ZE1026WFF
LT-0-0446SIL
R5
5ZE1026WFFLT-0-0446 
SILVER 5
DlvrQty: 116.000 Dt: 
15.09.2026 HSN: 64029990
116 PCS 198 0 1,148.4 5 0 22,968
190
5ZE1026WFF
LT-0-0446SIL
R6
5ZE1026WFFLT-0-0446 
SILVER 6
DlvrQty: 116.000 Dt: 
15.09.2026 HSN: 64029990
116 PCS 198 0 1,148.4 5 0 22,968
200
5ZE1026WFF
LT-0-0446SIL
R7
5ZE1026WFFLT-0-0446 
SILVER 7
DlvrQty: 116.000 Dt: 
15.09.2026 HSN: 64029990
116 PCS 198 0 1,148.4 5 0 22,968
210
5ZE1026WFF
LT-0-0446SIL
R8
5ZE1026WFFLT-0-0446 
SILVER 8
DlvrQty: 58.000 Dt: 
15.09.2026 HSN: 64029990
58 PCS 198 0 574.2 5 0 11,484
5ZE1026WFF
5ZE1026WFFLT-0-0446
220 LT-0-0446SIL
R9
SILVER 9
DlvrQty: 58.000 Dt: 
15.09.2026 HSN: 64029990
58 PCS 198 0 574.2 5 0 11,484
NET TOTAL 2,084 18,863.6 0 377,272
GROSS TOTAL 396,135.6
AMOUNT IN WORDS Three Lakh Ninety Six Thousand One Hundred Thirty Five Rupees Sixty Paise Only
1. Rates are: 
2. Payment Terms: Payment Within 45 DAYS
3. Delivery From: SSK FOOTCARE MANUFACTURING LLP
4. Person Involved: 
5. Packing & Forwarding: 0
6. Brokerage %: 0
7. Freight: 0
8. Insurance Charges: 0
9. Delivery Date: 15.09.2026
"""


class TestSiyaram2220011189Layout:
    @pytest.fixture(scope="class")
    @classmethod
    def parsed(cls):
        from po_extractor_free import _parse_meta, _siyaram_text_block_parse, _finalise_totals
        data = _parse_meta(SIYARAM_2220011189_TEXT)
        data["line_items"] = _siyaram_text_block_parse(SIYARAM_2220011189_TEXT)
        _finalise_totals(data, SIYARAM_2220011189_TEXT)
        return data

    def test_meta_fields(self, parsed):
        assert parsed["po_number"] == "2220011189"
        assert parsed["po_date"] == "2026-08-05"
        assert parsed["client_name"] == "SIYARAM SILK MILLS LTD."
        assert parsed["vendor_name"] == "SSK FOOTCARE MANUFACTURING LLP"

    def test_item_count_and_quantities(self, parsed):
        items = parsed["line_items"]
        assert len(items) == 22
        assert sum(li["quantity"] for li in items) == 2084
        assert parsed["total_quantity"] == 2084

    def test_financial_totals(self, parsed):
        assert parsed["subtotal"] == 377272.0
        assert parsed["igst_amount"] == 18863.6
        assert parsed["total_tax"] == 18863.6

    def test_colors_and_styles(self, parsed):
        items = parsed["line_items"]
        # Items 1-5 Brown
        for li in items[:5]:
            assert li["color"] == "BROWN"
            assert "5ZE1026WFFLT-0-0445" in li["style_code"]
        # Items 6-10 Off White
        for li in items[5:10]:
            assert li["color"] == "OFF WHITE"
            assert "5ZE1026WFFLT-0-0445" in li["style_code"]
        # Items 11-16 Gold
        for li in items[10:16]:
            assert li["color"] == "GOLD"
            assert "5ZE1026WFFLT-0-0446" in li["style_code"]
        # Items 17-22 Silver
        for li in items[16:]:
            assert li["color"] == "SILVER"
            assert "5ZE1026WFFLT-0-0446" in li["style_code"]

