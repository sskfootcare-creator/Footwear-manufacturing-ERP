"""Standardized Identifier Handling & ObjectId Conversion Utilities (P1-013).

Provides canonical ID validation, conversion, and MongoDB query construction
to eliminate mixed ObjectId/string references and silent broken links.
"""

from typing import Any, Optional, Union, Dict, List
from bson import ObjectId


def is_valid_object_id(val: Any) -> bool:
    """Return True if val is an ObjectId or a valid 24-char hex ObjectId string."""
    if val is None:
        return False
    if isinstance(val, ObjectId):
        return True
    if isinstance(val, str) and ObjectId.is_valid(val):
        return True
    return False


def to_object_id(val: Any) -> Optional[ObjectId]:
    """Convert string or ObjectId to ObjectId. Returns None if invalid or None."""
    if val is None or val == "":
        return None
    if isinstance(val, ObjectId):
        return val
    try:
        val_str = str(val).strip()
        if ObjectId.is_valid(val_str):
            return ObjectId(val_str)
    except Exception:
        pass
    return None


def to_str_id(val: Any) -> Optional[str]:
    """Convert ObjectId or int/str to canonical string. Returns None if None."""
    if val is None or val == "":
        return None
    return str(val).strip()


def query_entity_id(val: Any, id_field: str = "_id") -> Dict[str, Any]:
    """Build a MongoDB filter that matches either ObjectId or string representation.

    Prevents broken lookups when legacy collections contain mixed ID representations.
    Example: query_entity_id("60c72b2f9b1d8b3a4c8b4567") ->
             {"$or": [{"_id": ObjectId("...")}, {"_id": "60c72b2f9b1d8b3a4c8b4567"}]}
    """
    if val is None:
        return {id_field: None}

    oid = to_object_id(val)
    sid = to_str_id(val)

    if oid is not None and sid is not None and str(oid) == sid:
        return {"$or": [{id_field: oid}, {id_field: sid}]}
    elif oid is not None:
        return {id_field: oid}
    else:
        return {id_field: sid}


def normalize_document_ids(doc: Any) -> Any:
    """Recursively convert `_id` to string `id` and all nested ObjectIds to strings.

    Ensures consistent API JSON responses and no raw ObjectIds leaking to clients.
    """
    if doc is None:
        return None
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, list):
        return [normalize_document_ids(item) for item in doc]
    if isinstance(doc, dict):
        d = dict(doc)
        if "_id" in d:
            d["id"] = str(d.pop("_id"))
        for k, v in d.items():
            if isinstance(v, (ObjectId, dict, list)):
                d[k] = normalize_document_ids(v)
        return d
    return doc
