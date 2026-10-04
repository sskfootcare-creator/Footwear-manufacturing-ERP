"""
Unit and Integration Tests for ImageKit.io Upload File V2 API Service.
Tests:
- Configuration checks
- V2 JWT client-upload token generation (RFC 7519 / HMAC SHA256)
- URL variants and transformation builder
- Server-to-server V2 upload via async httpx
- Server-to-server delete via async httpx
- POST /api/upload/image route integration with ImageKit
- POST /api/upload/file general document uploader
- POST /api/upload/imagekit-auth token endpoint
"""

import io
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import UploadFile, HTTPException
from PIL import Image
import jwt

from services.imagekit_service import (
    is_imagekit_configured,
    get_basic_auth_header,
    generate_v2_auth_token,
    build_image_variants,
    upload_to_imagekit_async,
    delete_from_imagekit_async,
)
import server


class DummyRequest:
    state = type("State", (), {"user": {"email": "admin@sskfootcare.com", "role": "admin"}})()
    headers = {}
    cookies = {}


def test_is_imagekit_configured(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "")
    assert is_imagekit_configured() is False

    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "private_mock_key_12345678901234567890")
    assert is_imagekit_configured() is True


def test_get_basic_auth_header():
    hdr = get_basic_auth_header("private_test_123")
    assert "Authorization" in hdr
    assert hdr["Authorization"].startswith("Basic ")
    import base64
    decoded = base64.b64decode(hdr["Authorization"].replace("Basic ", "")).decode()
    assert decoded == "private_test_123:"


def test_generate_v2_auth_token_structure(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PUBLIC_KEY", "public_test_xyz")
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "private_secret_32bytes_long_key!!")

    payload = {
        "fileName": "sample_oxford_shoe.jpg",
        "folder": "/ssk-erp/styles",
        "tags": "shoe,formal",
    }

    res = generate_v2_auth_token(payload, expire_seconds=1800)
    assert "token" in res
    assert res["expire"] == 1800
    assert res["publicKey"] == "public_test_xyz"

    # Decode unverified header
    header = jwt.get_unverified_header(res["token"])
    assert header.get("alg") == "HS256"
    assert header.get("typ") == "JWT"
    assert header.get("kid") == "public_test_xyz"

    # Verify signature and decoded payload
    decoded = jwt.decode(
        res["token"],
        "private_secret_32bytes_long_key!!",
        algorithms=["HS256"],
    )
    assert decoded["fileName"] == "sample_oxford_shoe.jpg"
    assert decoded["folder"] == "/ssk-erp/styles"
    assert "iat" in decoded
    assert "exp" in decoded
    assert decoded["exp"] == decoded["iat"] + 1800


def test_build_image_variants():
    # Test ImageKit URL transformations
    ik_url = "https://ik.imagekit.io/ssk_demo/ssk-erp/images/shoe.jpg"
    variants = build_image_variants(ik_url)
    assert variants["original_url"] == ik_url
    assert "tr=w-800,q-85" in variants["display_url"]
    assert "tr=w-150,h-150" in variants["thumbnail_url"]

    # Test non-ImageKit URL fallback
    local_url = "/api/uploads/images/shoe.jpg"
    local_variants = build_image_variants(local_url, default_thumb="/api/uploads/images/thumb.jpg")
    assert local_variants["original_url"] == local_url
    assert local_variants["display_url"] == local_url
    assert local_variants["thumbnail_url"] == "/api/uploads/images/thumb.jpg"


@pytest.mark.anyio
async def test_upload_to_imagekit_async(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "private_mock_key_12345678901234567890")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "fileId": "65bfa1234567",
        "name": "derby_brown_v1.jpg",
        "size": 45000,
        "filePath": "/ssk-erp/images/derby_brown_v1.jpg",
        "url": "https://ik.imagekit.io/ssk/ssk-erp/images/derby_brown_v1.jpg",
        "thumbnailUrl": "https://ik.imagekit.io/ssk/ssk-erp/images/derby_brown_v1.jpg?tr=n-media_library_thumbnail",
        "height": 600,
        "width": 800,
        "fileType": "image",
    }

    with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)) as mock_post:
        res = await upload_to_imagekit_async(
            file_data=b"\xFF\xD8\xFFdummy-jpeg-data",
            file_name="derby_brown.jpg",
            folder="/ssk-erp/images",
        )

        assert res["fileId"] == "65bfa1234567"
        assert res["url"] == "https://ik.imagekit.io/ssk/ssk-erp/images/derby_brown_v1.jpg"
        assert "display_url" in res
        assert "thumbnail_url" in res
        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert call_url == "https://upload.imagekit.io/api/v2/files/upload"


@pytest.mark.anyio
async def test_delete_from_imagekit_async(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "private_mock_key_12345678901234567890")

    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("httpx.AsyncClient.delete", AsyncMock(return_value=mock_resp)) as mock_delete:
        ok = await delete_from_imagekit_async("file_id_999")
        assert ok is True
        assert mock_delete.called
        call_url = mock_delete.call_args[0][0]
        assert "https://api.imagekit.io/v1/files/file_id_999" in call_url


@pytest.mark.anyio
async def test_api_upload_image_with_imagekit(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "private_mock_key_12345678901234567890")

    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    # Mock ImageKit upload
    mock_ik_upload = AsyncMock(return_value={
        "fileId": "ik_file_888",
        "url": "https://ik.imagekit.io/ssk/ssk-erp/images/derby.jpg",
        "original_url": "https://ik.imagekit.io/ssk/ssk-erp/images/derby.jpg",
        "display_url": "https://ik.imagekit.io/ssk/ssk-erp/images/derby.jpg?tr=w-800,q-85",
        "thumbnail_url": "https://ik.imagekit.io/ssk/ssk-erp/images/derby.jpg?tr=w-150,h-150",
        "width": 100,
        "height": 100,
    })
    monkeypatch.setattr(server, "upload_to_imagekit_async", mock_ik_upload)

    # Small test image
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    upload_file = UploadFile(
        file=buf,
        filename="derby.jpg",
        headers={"content-type": "image/jpeg"},
    )

    res = await server.upload_image(file=upload_file, request=DummyRequest())
    assert res["storage"] == "imagekit"
    assert res["file_id"] == "ik_file_888"
    assert "https://ik.imagekit.io" in res["url"]
    assert mock_ik_upload.called


@pytest.mark.anyio
async def test_api_upload_file_endpoint(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "private_mock_key_12345678901234567890")

    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    mock_ik_upload = AsyncMock(return_value={
        "fileId": "dxf_file_456",
        "name": "upper_pattern.dxf",
        "url": "https://ik.imagekit.io/ssk/ssk-erp/documents/upper_pattern.dxf",
        "thumbnailUrl": "https://ik.imagekit.io/ssk/ssk-erp/documents/upper_pattern.dxf",
        "fileType": "non-image",
        "size": 12040,
    })
    monkeypatch.setattr(server, "upload_to_imagekit_async", mock_ik_upload)

    raw_buf = io.BytesIO(b"DXF HEADER DATA ... PATTERN CAD")
    up = UploadFile(
        file=raw_buf,
        filename="upper_pattern.dxf",
        headers={"content-type": "application/dxf"},
    )

    res = await server.upload_file(file=up, folder="/ssk-erp/patterns", request=DummyRequest())
    assert res["ok"] is True
    assert res["file_id"] == "dxf_file_456"
    assert res["storage"] == "imagekit"
    assert "upper_pattern.dxf" in res["url"]


@pytest.mark.anyio
async def test_api_upload_imagekit_auth_endpoint(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PUBLIC_KEY", "public_auth_test_123")
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "private_auth_secret_key_32bytes!!")

    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    payload = {
        "uploadPayload": {"fileName": "cad_spec.pdf", "folder": "/ssk-erp/docs"},
        "expire": 1800,
    }

    res = await server.get_imagekit_auth_endpoint(payload, request=DummyRequest())
    assert "token" in res
    assert res["expire"] == 1800
    assert res["publicKey"] == "public_auth_test_123"
