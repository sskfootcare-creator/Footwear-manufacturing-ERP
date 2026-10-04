"""
ImageKit.io Integration Service (Upload File V2 API)
Implements ImageKit Upload File V2 API specifications:
- Server-to-server file/image upload via HTTP Basic Auth
- V2 Secure Client-Side Upload JWT Token Generation
- File Deletion & URL Transformation Helpers
Ref: https://imagekit.io/docs/api-reference/upload-file/upload-file-v2
"""

import os
import time
import base64
import logging
from typing import Optional, Dict, Any, Union, BinaryIO
import httpx
import jwt

logger = logging.getLogger("imagekit_service")

# Environment configurations
IMAGEKIT_PUBLIC_KEY = os.environ.get("IMAGEKIT_PUBLIC_KEY", "").strip()
IMAGEKIT_PRIVATE_KEY = os.environ.get("IMAGEKIT_PRIVATE_KEY", "").strip()
IMAGEKIT_URL_ENDPOINT = os.environ.get("IMAGEKIT_URL_ENDPOINT", "").strip().rstrip("/")

IMAGEKIT_UPLOAD_V2_URL = "https://upload.imagekit.io/api/v2/files/upload"
IMAGEKIT_API_BASE_URL = "https://api.imagekit.io/v1"


def get_imagekit_config() -> Dict[str, str]:
    """Retrieve current ImageKit configuration."""
    return {
        "public_key": os.environ.get("IMAGEKIT_PUBLIC_KEY", IMAGEKIT_PUBLIC_KEY).strip(),
        "private_key": os.environ.get("IMAGEKIT_PRIVATE_KEY", IMAGEKIT_PRIVATE_KEY).strip(),
        "url_endpoint": os.environ.get("IMAGEKIT_URL_ENDPOINT", IMAGEKIT_URL_ENDPOINT).strip().rstrip("/"),
    }


def is_imagekit_configured() -> bool:
    """Return True if ImageKit private key is set."""
    cfg = get_imagekit_config()
    return bool(cfg["private_key"])


def get_basic_auth_header(private_key: Optional[str] = None) -> Dict[str, str]:
    """
    Generate HTTP Basic Auth header for ImageKit Server API:
    Authorization: Basic base64(private_key + ":")
    """
    pk = private_key or get_imagekit_config()["private_key"]
    if not pk:
        raise ValueError("ImageKit private key is not configured.")
    encoded = base64.b64encode(f"{pk}:".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


def generate_v2_auth_token(
    upload_payload: Dict[str, Any],
    expire_seconds: int = 3600,
    public_key: Optional[str] = None,
    private_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate JSON Web Token (JWT) for secure client-side file upload adhering
    strictly to the ImageKit V2 Upload specification:
    - Header: {"alg": "HS256", "typ": "JWT", "kid": public_key}
    - Payload: upload_payload with integer 'iat' and 'exp' (exp <= iat + 3600)
    - Signature: HMAC-SHA256 signed with private_key
    """
    cfg = get_imagekit_config()
    pub_k = public_key or cfg["public_key"]
    priv_k = private_key or cfg["private_key"]

    if not priv_k:
        raise ValueError("ImageKit private key is required to generate upload tokens.")
    if not pub_k:
        raise ValueError("ImageKit public key is required to generate upload tokens.")

    now = int(time.time())
    expire = min(int(expire_seconds or 3600), 3600)

    # Clone payload and inject iat / exp
    payload = dict(upload_payload or {})
    payload["iat"] = now
    payload["exp"] = now + expire

    # Stringify values except iat and exp per ImageKit V2 docs requirement
    stringified_payload = {}
    for k, v in payload.items():
        if k in ("iat", "exp"):
            stringified_payload[k] = int(v)
        elif isinstance(v, (dict, list)):
            import json
            stringified_payload[k] = json.dumps(v)
        elif isinstance(v, bool):
            stringified_payload[k] = "true" if v else "false"
        else:
            stringified_payload[k] = str(v)

    token = jwt.encode(
        payload=stringified_payload,
        key=priv_k,
        algorithm="HS256",
        headers={
            "alg": "HS256",
            "typ": "JWT",
            "kid": pub_k,
        },
    )

    return {
        "token": token,
        "expire": expire,
        "publicKey": pub_k,
    }


def build_image_variants(url: str, default_thumb: Optional[str] = None) -> Dict[str, str]:
    """
    Generate responsive variant URLs using ImageKit real-time transformation parameters.
    - display_url: 800px width web-optimized
    - thumbnail_url: 150x150 square thumbnail with padding
    """
    if not url:
        return {"url": "", "display_url": "", "thumbnail_url": ""}

    if "ik.imagekit.io" in url:
        sep = "&" if "?" in url else "?"
        display_url = f"{url}{sep}tr=w-800,q-85"
        thumbnail_url = default_thumb or f"{url}{sep}tr=w-150,h-150,cm-pad_resize,bg-F3F4F6"
    else:
        display_url = url
        thumbnail_url = default_thumb or url

    return {
        "original_url": url,
        "display_url": display_url,
        "thumbnail_url": thumbnail_url,
    }


async def upload_to_imagekit_async(
    file_data: Union[bytes, BinaryIO, str],
    file_name: str,
    folder: str = "/ssk-erp/images",
    tags: Optional[Union[str, list]] = None,
    use_unique_file_name: bool = True,
    is_private_file: bool = False,
    custom_metadata: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Upload a file/image directly to ImageKit using ImageKit Upload File V2 API.
    Uses async httpx client.
    """
    cfg = get_imagekit_config()
    priv_k = cfg["private_key"]
    if not priv_k:
        raise ValueError("IMAGEKIT_PRIVATE_KEY is not configured.")

    headers = get_basic_auth_header(priv_k)

    form_data: Dict[str, Any] = {
        "fileName": file_name,
        "folder": folder if folder.startswith("/") else f"/{folder}",
        "useUniqueFileName": "true" if use_unique_file_name else "false",
        "isPrivateFile": "true" if is_private_file else "false",
        "responseFields": "tags,isPrivateFile,metadata",
    }

    if tags:
        if isinstance(tags, list):
            form_data["tags"] = ",".join(str(t).strip() for t in tags if t)
        else:
            form_data["tags"] = str(tags)

    if custom_metadata:
        import json
        form_data["customMetadata"] = json.dumps(custom_metadata)

    files = None
    if isinstance(file_data, (bytes, bytearray)):
        files = {"file": (file_name, file_data)}
    elif hasattr(file_data, "read"):
        files = {"file": (file_name, file_data)}
    elif isinstance(file_data, str):
        # Could be URL or base64 data
        form_data["file"] = file_data
    else:
        raise ValueError("Unsupported file_data type for ImageKit upload.")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            IMAGEKIT_UPLOAD_V2_URL,
            headers=headers,
            data=form_data,
            files=files,
        )

    if response.status_code not in (200, 201):
        err_msg = f"ImageKit V2 Upload failed [{response.status_code}]: {response.text}"
        logger.error(err_msg)
        raise RuntimeError(err_msg)

    data = response.json()
    url = data.get("url", "")
    variants = build_image_variants(url, data.get("thumbnailUrl"))

    data["display_url"] = variants["display_url"]
    data["thumbnail_url"] = variants["thumbnail_url"]
    data["original_url"] = url
    return data


def upload_to_imagekit_sync(
    file_data: Union[bytes, BinaryIO, str],
    file_name: str,
    folder: str = "/ssk-erp/images",
    tags: Optional[Union[str, list]] = None,
    use_unique_file_name: bool = True,
    is_private_file: bool = False,
    custom_metadata: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Synchronous version of upload_to_imagekit. Useful for sync worker scripts or tasks.
    """
    import requests

    cfg = get_imagekit_config()
    priv_k = cfg["private_key"]
    if not priv_k:
        raise ValueError("IMAGEKIT_PRIVATE_KEY is not configured.")

    headers = get_basic_auth_header(priv_k)

    form_data: Dict[str, Any] = {
        "fileName": file_name,
        "folder": folder if folder.startswith("/") else f"/{folder}",
        "useUniqueFileName": "true" if use_unique_file_name else "false",
        "isPrivateFile": "true" if is_private_file else "false",
        "responseFields": "tags,isPrivateFile,metadata",
    }

    if tags:
        if isinstance(tags, list):
            form_data["tags"] = ",".join(str(t).strip() for t in tags if t)
        else:
            form_data["tags"] = str(tags)

    if custom_metadata:
        import json
        form_data["customMetadata"] = json.dumps(custom_metadata)

    files = None
    if isinstance(file_data, (bytes, bytearray)):
        files = {"file": (file_name, file_data)}
    elif hasattr(file_data, "read"):
        files = {"file": (file_name, file_data)}
    elif isinstance(file_data, str):
        form_data["file"] = file_data
    else:
        raise ValueError("Unsupported file_data type for ImageKit upload.")

    response = requests.post(
        IMAGEKIT_UPLOAD_V2_URL,
        headers=headers,
        data=form_data,
        files=files,
        timeout=timeout,
    )

    if response.status_code not in (200, 201):
        err_msg = f"ImageKit V2 Upload failed [{response.status_code}]: {response.text}"
        logger.error(err_msg)
        raise RuntimeError(err_msg)

    data = response.json()
    url = data.get("url", "")
    variants = build_image_variants(url, data.get("thumbnailUrl"))

    data["display_url"] = variants["display_url"]
    data["thumbnail_url"] = variants["thumbnail_url"]
    data["original_url"] = url
    return data


async def delete_from_imagekit_async(file_id: str, timeout: float = 15.0) -> bool:
    """
    Delete a file from ImageKit by fileId.
    DELETE https://api.imagekit.io/v1/files/{file_id}
    """
    if not file_id:
        return False

    cfg = get_imagekit_config()
    priv_k = cfg["private_key"]
    if not priv_k:
        return False

    headers = get_basic_auth_header(priv_k)
    url = f"{IMAGEKIT_API_BASE_URL}/files/{file_id}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.delete(url, headers=headers)
            if resp.status_code in (200, 204, 404):
                return True
            logger.warning(f"ImageKit delete file returned unexpected code {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"ImageKit delete error: {e}")
        return False
