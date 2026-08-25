"""Test bounded memory reading in POST /api/upload/image to prevent memory exhaustion."""
import pytest
import io
from fastapi import UploadFile, HTTPException
from PIL import Image
import server
from server import upload_image


class DummyRequest:
    state = type("State", (), {"user": {"email": "admin@sskfootcare.com", "role": "admin"}})()
    headers = {}
    cookies = {}


class MonitoredBytesIO(io.BytesIO):
    """BytesIO that tracks the total number of bytes read."""
    def __init__(self, initial_bytes):
        super().__init__(initial_bytes)
        self.total_bytes_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.total_bytes_read += len(chunk)
        return chunk


@pytest.mark.anyio
async def test_upload_image_bounded_read_rejects_without_full_read(monkeypatch):
    """Verify that uploading a large file (e.g. 20MB) only reads up to MAX_UPLOAD_BYTES + 1
    (8,388,609 bytes) and rejects with HTTP 413, without buffering the entire 20MB into memory.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    # 1. Create a 20 MB buffer
    twenty_mb = 20 * 1024 * 1024
    raw_buffer = MonitoredBytesIO(b"X" * twenty_mb)

    upload_file = UploadFile(
        file=raw_buffer,
        filename="oversized_photo.jpg",
        headers={"content-type": "image/jpeg"},
    )

    # 2. Attempt upload -> must raise HTTP 413
    with pytest.raises(HTTPException) as exc_info:
        await upload_image(file=upload_file, request=DummyRequest())

    assert exc_info.value.status_code == 413
    assert "Image too large" in exc_info.value.detail

    # 3. Assert that ONLY 8MB + 1 byte was read from the stream, NOT the full 20MB!
    max_expected_read = (8 * 1024 * 1024) + 1
    assert raw_buffer.total_bytes_read == max_expected_read
    assert raw_buffer.total_bytes_read < twenty_mb


@pytest.mark.anyio
async def test_upload_image_valid_small_image(monkeypatch):
    """Verify that a valid small image passes and encodes variants correctly."""
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    # Create a small 50x50 PNG
    img = Image.new("RGB", (50, 50), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    upload_file = UploadFile(
        file=buf,
        filename="test_blue_shoe.png",
        headers={"content-type": "image/png"},
    )

    result = await upload_image(file=upload_file, request=DummyRequest())
    assert "url" in result
    assert "display_url" in result
    assert "thumbnail_url" in result

