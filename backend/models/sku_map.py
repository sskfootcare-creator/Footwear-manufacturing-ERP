"""SKU Map, Marketplace Resolver & Export/Import Format Config Pydantic Models."""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

SourceType = Literal["b2b_client", "online_channel"]
OnlineChannel = Literal["myntra", "flipkart", "nykaa", "website"]
Marketplace = Literal["myntra", "flipkart", "nykaa", "website", "ajio", "amazon", "other"]
Platform = Literal["myntra", "flipkart", "ajio", "nykaa", "website", "other"]
ConfigRole = Literal["order", "dispatch", "monthly_report", "settlement"]


class SkuMapIn(BaseModel):
    style_id: str
    source_type: SourceType
    source_name: str
    external_sku: str
    external_style_name: Optional[str] = ""
    external_style_id: Optional[str] = ""   # Marketplace-assigned per-style-color ID (e.g. Myntra Style Id)
    color_map: Optional[Dict[str, str]] = {}
    size_map:  Optional[Dict[str, str]] = {}
    image_url: Optional[str] = ""
    brand: Optional[str] = ""
    mrp: Optional[float] = None
    price: Optional[float] = None


class SkuMapUpdate(BaseModel):
    external_style_name: Optional[str] = None
    external_style_id: Optional[str] = None  # None = do not update; "" = clear
    color_map: Optional[Dict[str, str]] = None
    size_map:  Optional[Dict[str, str]] = None
    image_url: Optional[str] = None  # None = do not update; "" = clear
    brand: Optional[str] = None
    mrp: Optional[float] = None
    price: Optional[float] = None


class ParserTemplateIn(BaseModel):
    marketplace: Marketplace
    template:    str
    pattern:     str
    separator:   Optional[str] = None
    active:      bool = True
    example:     Optional[str] = None


class StyleColorMappingIn(BaseModel):
    marketplace:            Marketplace
    marketplace_style_code: str
    marketplace_color_code: str
    erp_style_code:         str
    erp_color_code:         str
    active:                 bool = True


class SkuResolveIn(BaseModel):
    marketplace: Marketplace
    sku:         str


class UnresolvedMapIn(BaseModel):
    queue_id:               Optional[str] = None
    marketplace:            Marketplace
    marketplace_style_code: str
    marketplace_color_code: str
    erp_style_id:           Optional[str] = None
    erp_style_code:         str
    erp_color_code:         str


class ExportColumn(BaseModel):
    name: str
    source: Literal[
        "group_sku", "leaf_sku", "style_code", "size",
        "color_name", "color_code",
        "style", "lifecycle", "constant", "blank",
    ]
    key: Optional[str] = None
    value: Optional[Any] = None
    notes: Optional[str] = None
    required: bool = False


class ExportTemplate(BaseModel):
    sheet_name: str = "Sheet1"
    header_row_index: int = 0
    pre_header_rows: Optional[List[List[Any]]] = None
    post_header_rows: Optional[List[List[Any]]] = None
    columns: List[ExportColumn]

    @field_validator("columns")
    @classmethod
    def _cols_non_empty(cls, v):
        if not v or len(v) == 0:
            raise PydanticCustomError(
                "export_columns_empty",
                "export_template.columns must contain at least one column"
            )
        if not any(c.source == "leaf_sku" for c in v):
            raise PydanticCustomError(
                "export_columns_leaf_sku",
                "export_template.columns must include exactly one column with source='leaf_sku'"
            )
        return v


class SheetLocator(BaseModel):
    type: Literal["fixed_name", "name_contains", "first_sheet"]
    name: Optional[str] = None
    substring: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("substring")
    @classmethod
    def _clean_sub(cls, v):
        return v.strip() if isinstance(v, str) else v


class HeaderLocator(BaseModel):
    type: Literal["fixed_row", "scan_for_columns"]
    row: Optional[int] = None
    must_contain_any: Optional[List[str]] = None


class ListingFormatConfigIn(BaseModel):
    platform: Platform
    sheet_locator: SheetLocator
    header_locator: HeaderLocator
    skip_rows_after_header: int = 0
    column_map: Dict[str, Optional[str]]
    has_native_group_id: bool = False
    active: bool = True
    notes: Optional[str] = ""
    export_template: Optional[ExportTemplate] = None

    @field_validator("column_map")
    @classmethod
    def _validate_column_map(cls, v):
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        if not v.get("leaf_sku"):
            raise PydanticCustomError(
                "column_map_leaf_sku",
                "column_map.leaf_sku is required — every platform must expose the per-size unique SKU column"
            )
        return v


class ListingFormatConfigUpdate(BaseModel):
    sheet_locator: Optional[SheetLocator] = None
    header_locator: Optional[HeaderLocator] = None
    skip_rows_after_header: Optional[int] = None
    column_map: Optional[Dict[str, Optional[str]]] = None
    has_native_group_id: Optional[bool] = None
    active: Optional[bool] = None


class CatalogueExportRequest(BaseModel):
    style_id: str
    platform: Platform
    colors: Optional[List[str]] = None
    sizes:  Optional[List[str]] = None


class OrderImportFormatConfigIn(BaseModel):
    platform: Platform
    role: ConfigRole = "order"
    sheet_locator: SheetLocator
    header_locator: HeaderLocator
    skip_rows_after_header: int = 0
    column_map: Dict[str, Optional[str]]
    known_sku_prefixes_to_strip: List[str] = Field(default_factory=list)
    known_sku_prefix_replacements: Dict[str, str] = Field(default_factory=dict)
    is_picklist: bool = False
    active: bool = True
    notes: Optional[str] = ""

    @field_validator("column_map")
    @classmethod
    def _order_column_map_leaf_sku(cls, v, info):
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        role = getattr(info, "data", {}).get("role", "order") if info else "order"
        if role == "settlement":
            if not v.get("order_ref") and not v.get("leaf_sku"):
                raise PydanticCustomError(
                    "column_map_settlement_ref",
                    "column_map must contain either order_ref or leaf_sku for settlement files"
                )
        else:
            if not v.get("leaf_sku"):
                raise PydanticCustomError(
                    "column_map_leaf_sku",
                    "column_map.leaf_sku is required — every order/picklist/dispatch/monthly file must expose our internal SKU column"
                )
        return v


class OrderImportFormatConfigUpdate(BaseModel):
    sheet_locator: Optional[SheetLocator] = None
    header_locator: Optional[HeaderLocator] = None
    skip_rows_after_header: Optional[int] = None
    column_map: Optional[Dict[str, Optional[str]]] = None
    known_sku_prefixes_to_strip: Optional[List[str]] = None
    known_sku_prefix_replacements: Optional[Dict[str, str]] = None
    is_picklist: Optional[bool] = None
    active: Optional[bool] = None


class OrderImportConfiguredRequest(BaseModel):
    pass


class OnlineOrderImportResult(BaseModel):
    channel: str
    imported: int
    unresolved: int
    errors: List[dict]


class ListingImportDecision(BaseModel):
    """A single per-group linking decision made by the user in Stage 2."""
    group_key: str
    style_id: Optional[str] = None   # None = leave unlinked (needs_style_code: true)


class ListingImportCommitIn(BaseModel):
    """Payload sent when committing a listing import session after Stage 2 linking."""
    decisions: List[ListingImportDecision]


class MyntraConfirmedGroupIn(BaseModel):
    """A confirmed group payload from Stage 2 linking for Myntra/marketplace import."""
    group_key: Optional[str] = None
    style_id: Optional[str] = None
    style_code: Optional[str] = None
    external_sku: Optional[str] = None
    external_style_id: Optional[str] = ""   # e.g. Myntra Style Id
    external_style_name: Optional[str] = ""
    color: Optional[str] = ""
    color_map: Optional[Dict[str, str]] = Field(default_factory=dict)
    size_map: Optional[Dict[str, str]] = Field(default_factory=dict)
    image_url: Optional[str] = ""
    brand: Optional[str] = ""
    mrp: Optional[float] = None
    price: Optional[float] = None
    source_type: Optional[SourceType] = "online_channel"
    source_name: Optional[str] = "myntra"
    already_mapped: Optional[bool] = False
    rows: Optional[List[Dict[str, Any]]] = None


class MyntraImportConfirmIn(BaseModel):
    """Payload sent to POST /myntra/import/confirm."""
    groups: Optional[List[MyntraConfirmedGroupIn]] = None
    confirmed_groups: Optional[List[MyntraConfirmedGroupIn]] = None
    session_id: Optional[str] = None

