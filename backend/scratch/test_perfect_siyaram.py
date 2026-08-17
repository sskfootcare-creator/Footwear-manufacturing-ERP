import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "tests"))
import re, pdfplumber, io
from po_extractor_free import _norm, _to_number, _HSN_CODES_FOOTWEAR

_SIYARAM_NUMERIC_RE = re.compile(
    r'^(?:(\d+)\s+)?(?:([A-Z0-9_-]{4,25})\s+)?(\d+)\s+PCS\s+([\d.,]+)\s+(?:\d+\s+)?([\d.,]+)\s+\d+\s+\d+\s+([\d,]+(?:\.\d+)?)\s*$',
    re.I,
)
_SIYARAM_HSN_RE = re.compile(r'HSN[:\s]+(\d{4,10})', re.I)

_SIYARAM_JUNK_LINES = {
    'ITEM', 'MATERIAL', 'MATERIAL DESCRIPTION', 'QTY', 'UOM', 'RATE', 'DISC',
    'CGST/IGST', 'SGST/UGST', 'TOTAL NET VALUE', 'PCS', 'INR', 'PURCHASE ORDER',
    'VENDOR', 'BROKER', 'SIYARAM', 'MILLS', 'LTD', 'LIMITED', 'DATE', 'PO', 'P.O.',
    'REGISTERED', 'OFFICE', 'CORPORATE', 'DELIVERY', 'BILLING', 'ADDRESS', 'GST'
}

COLOR_MODIFIERS = {'OFF', 'DARK', 'LIGHT', 'NAVY', 'OLIVE', 'DEEP', 'BRIGHT'}
COLOR_NAMES = {'WHITE', 'BLACK', 'BROWN', 'GOLD', 'SILVER', 'TAN', 'CREAM', 'BLUE', 'RED', 'GREY', 'GRAY', 'YELLOW', 'GREEN', 'BEIGE', 'MAROON', 'PINK', 'ORANGE'}

def siyaram_parse_perfect(text: str) -> list[dict]:
    lines = [_norm(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    n = len(lines)

    numeric_idx = [i for i, ln in enumerate(lines) if _SIYARAM_NUMERIC_RE.match(ln)]
    items: list[dict] = []
    used_lines: set[int] = set()

    for slot, i in enumerate(numeric_idx):
        nm = _SIYARAM_NUMERIC_RE.match(lines[i])
        if not nm:
            continue
        inline_mat = nm.group(2) or ''
        qty = int(nm.group(3))
        rate = _to_number(nm.group(4))
        amount = _to_number(nm.group(6))
        if qty <= 0 or rate <= 0:
            continue

        prev_i = numeric_idx[slot - 1] if slot > 0 else -1
        next_i = numeric_idx[slot + 1] if slot + 1 < len(numeric_idx) else n
        lo = max(prev_i + 1, i - 10)
        hi = min(next_i, i + 8)

        # 1. Detect Description (Style, Color, Size)
        desc_style = ''
        color = ''
        size = ''
        desc_line_indices = []

        for dj in range(i - 1, lo - 1, -1):
            if dj in used_lines:
                continue
            ln = lines[dj]
            if 'DLVRQTY' in ln.upper() or 'HSN:' in ln.upper():
                continue

            # Check for: <STYLE> <COLOR> <SIZE> (e.g. 'ZP125WWFLT117 BROWN 4')
            m1 = re.match(r'^([A-Z0-9_-]{4,25})\s+([A-Z][A-Z\s]{0,20}[A-Z])\.?\s+(\d{1,2}(?:\.\d)?)$', ln, re.I)
            if m1:
                desc_style = m1.group(1).strip()
                color = m1.group(2).strip().rstrip('.')
                size = m1.group(3).strip()
                desc_line_indices.append(dj)
                break

            # Check for: <COLOR> <SIZE> (e.g. 'BROWN. 4', 'WHITE 4', 'GOLD 4', 'SILVER 9')
            m2 = re.match(r'^([A-Z][A-Z\s]{0,20}[A-Z])\.?\s+(\d{1,2}(?:\.\d)?)$', ln, re.I)
            if m2 and (m2.group(1).upper().strip().rstrip('.') in COLOR_NAMES or any(c in m2.group(1).upper() for c in COLOR_NAMES)):
                color = m2.group(1).strip().rstrip('.')
                size = m2.group(2).strip()
                desc_line_indices.append(dj)

                # Check preceding line for style and/or color modifier (e.g. '5ZE1026WFFLT-0-0445' or '5ZE1026WFFLT-0-0445 OFF')
                if dj > lo and (dj - 1) not in used_lines:
                    prev_ln = lines[dj - 1].strip()
                    m_prev = re.match(r'^(?:([A-Z0-9_-]{4,25})\s+)?([A-Z]+)$', prev_ln, re.I)
                    if m_prev and m_prev.group(2).upper() in COLOR_MODIFIERS:
                        color = f"{m_prev.group(2).upper()} {color}"
                        if m_prev.group(1):
                            desc_style = m_prev.group(1).strip()
                        desc_line_indices.append(dj - 1)
                    elif re.match(r'^[A-Z0-9_-]{4,25}$', prev_ln, re.I):
                        desc_style = prev_ln
                        desc_line_indices.append(dj - 1)
                break

        for dli in desc_line_indices:
            used_lines.add(dli)

        # 2. Detect Material Chunks (Top-to-Bottom in physical order)
        mat_chunks = []
        if inline_mat:
            mat_chunks.append(inline_mat)

        for dj in range(lo, i):
            if dj in used_lines or dj in desc_line_indices:
                continue
            ln = lines[dj]
            if ln.upper() in _SIYARAM_JUNK_LINES or 'DLVRQTY' in ln.upper() or 'HSN:' in ln.upper() or ln.isdigit():
                continue
            cleaned = re.sub(r'^\d+\s+', '', ln).strip()
            if re.match(r'^[A-Z0-9][A-Z0-9_-]{1,24}$', cleaned, re.I):
                if cleaned.upper() in COLOR_NAMES or cleaned.upper() in COLOR_MODIFIERS:
                    continue
                if cleaned == desc_style and len(mat_chunks) > 0:
                    continue
                if cleaned not in mat_chunks:
                    mat_chunks.append(cleaned)
                    used_lines.add(dj)
                    if sum(len(c) for c in mat_chunks) >= 20 and len(mat_chunks) >= 2:
                        if sum(len(c) for c in mat_chunks) >= 24 or len(mat_chunks) >= 3:
                            break

        # 3. Detect HSN
        hsn = ''
        for dj in range(lo, hi):
            hm = _SIYARAM_HSN_RE.search(lines[dj])
            if hm:
                hsn = hm.group(1)
                break

        style_code = ''.join(mat_chunks) if mat_chunks else desc_style
        full_desc = f'{desc_style} {color} {size}'.strip() if desc_style else f'{color} {size}'.strip()
        items.append({
            'style_code': style_code,
            'description': full_desc,
            'color': color,
            'size': size,
            'hsn_code': hsn or _HSN_CODES_FOOTWEAR,
            'quantity': qty,
            'unit_price': rate,
            'amount': amount if amount > 0 else round(qty * rate, 2),
            'mrp': '',
        })

    return items

# Test on 2220011189 text
from test_iteration14_siyaram import SIYARAM_2220011189_TEXT
items = siyaram_parse_perfect(SIYARAM_2220011189_TEXT)
print(f'2220011189 items: {len(items)}')
for idx, it in enumerate(items, 1):
    print(f'[{idx:2d}] Style: {it["style_code"]:26} | Desc: {it["description"]:32} | Color: {it["color"]:10} | Size: {it["size"]:2} | Qty: {it["quantity"]:3d} | Rate: {it["unit_price"]:3.0f}')

# Test on PDF fixture
fixture = os.path.join(os.path.dirname(__file__), "..", "backend", "tests", "fixtures", "siyaram_2220008835.pdf")
with open(fixture, 'rb') as fh:
    full_text_parts = []
    with pdfplumber.open(io.BytesIO(fh.read())) as pdf:
        for page in pdf.pages:
            full_text_parts.append(page.extract_text() or '')
    fixture_text = '\n'.join(full_text_parts)

fix_items = siyaram_parse_perfect(fixture_text)
print(f'\nFixture items: {len(fix_items)}')
assert len(fix_items) == 32
assert sum(x['quantity'] for x in fix_items) == 2088
print('Fixture Item 1:', fix_items[0])
print('Fixture Item 32:', fix_items[-1])
