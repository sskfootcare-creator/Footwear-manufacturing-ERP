import pytest
import httpx

BASE_URL = "http://localhost:8000/api"
TIMEOUT = 10.0


def test_material_component_sync(admin_requests_session):
    admin_session = admin_requests_session
    # 1. Create a raw material marked as a component (e.g. Sole EVA-M100)
    mat_payload = {
        "code": "TEST-SOLE-M100",
        "name": "EVA Sole Premium M100",
        "category": "sole",
        "unit": "pair",
        "rate": 150.0,
        "reorder_level": 50,
        "is_component": True,
        "component_category": "Sole",
        "image_url": "http://example.com/sole_thumb.jpg",
        "image_display_url": "http://example.com/sole_disp.jpg",
        "image_thumbnail_url": "http://example.com/sole_thumb.jpg",
    }
    
    # Cleanup if pre-existing
    r = admin_session.get(f"{BASE_URL}/materials")
    assert r.status_code == 200
    for m in r.json():
        if m.get("code") == "TEST-SOLE-M100":
            admin_session.delete(f"{BASE_URL}/materials/{m['id']}")
            
    res = admin_session.post(f"{BASE_URL}/materials", json=mat_payload)
    assert res.status_code == 200, res.text
    mat_doc = res.json()
    assert mat_doc["is_component"] is True

    # 2. Verify component inventory list includes the synced component
    c_res = admin_session.get(f"{BASE_URL}/components?code=TEST-SOLE-M100")
    assert c_res.status_code == 200, c_res.text
    comps = c_res.json()
    assert len(comps) >= 1
    comp = comps[0]
    assert comp["component_code"] == "TEST-SOLE-M100"
    assert comp["component_category"] == "Sole"
    assert comp["image_url"] == "http://example.com/sole_thumb.jpg"
    assert comp["material_id"] == mat_doc["id"]

    # 3. Update component image via PUT /components/{id}
    put_res = admin_session.put(
        f"{BASE_URL}/components/{comp['id']}",
        json={
            "image_url": "http://example.com/sole_updated.jpg",
            "image_display_url": "http://example.com/sole_updated.jpg",
            "image_thumbnail_url": "http://example.com/sole_updated.jpg",
        }
    )
    assert put_res.status_code == 200, put_res.text

    # 4. Verify material image was synced back
    m_check = admin_session.get(f"{BASE_URL}/materials")
    target_mat = next((m for m in m_check.json() if m["code"] == "TEST-SOLE-M100"), None)
    assert target_mat is not None
    assert target_mat["image_url"] == "http://example.com/sole_updated.jpg"

    # Cleanup
    admin_session.delete(f"{BASE_URL}/materials/{mat_doc['id']}")
