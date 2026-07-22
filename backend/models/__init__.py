"""Domain-grouped Pydantic Models package for SSK Footcare Backend."""

from models.auth import (
    LoginInput, UserCreate, UserUpdate, ForgotPasswordInput, ResetPasswordInput
)
from models.styles import (
    OnlineStatus, OnlineStatusEnum, ONLINE_STATUS_SEQUENCE, ONLINE_STATUS_SIDE_BRANCHES,
    PLANNED_COMPONENTS, StyleIn, PlannedComponent, StyleLifecycleUpsert, OnlineStatusPatchIn,
    ColorMasterIn, ColorMasterUpdate
)
from models.materials import (
    MaterialIn, BomItem, LaborItem, QuantityUpdate, InventoryMovement
)
from models.components import (
    ComponentUpdate, ComponentIn, ComponentMasterUpdate, ComponentBulkMatrix,
    ComponentMovementIn, StyleComponentMappingIn, StyleComponentMappingUpdate
)
from models.orders import (
    PRODUCTION_STAGES, POLineItem, POIn, ProductionStageUpdate
)
from models.workers import (
    WorkerIn, AssignmentUpdate, BulkAssign, AdvanceIn
)
from models.vendors import (
    DEFAULT_CREDIT_DAYS, PAYMENT_MODES, GRNLineItem, GRNIn, PaymentIn,
    VendorIn, VendorUpdate, VendorPOLineItem, VendorPOIn, VendorPOUpdate,
    VendorPOReceiveItem, VendorPOReceiveIn, DefectIn
)
from models.invoice_packing import (
    InvoiceGenerate, DispatchCreate, PackingListGenerate, MergedPackingListGenerate,
    PackingTemplateIn
)
from models.inventory import (
    MovementType, ReferenceType, AdjustmentField, SizeMatrixCell,
    FgInventoryIn, FgInventoryUpdate, StockReservation, StockRelease,
    FgStockMovementIn, InventoryReservationIn
)
from models.wms import (
    PicklistItemIn, PicklistIn, PickItemIn, PicklistPatchIn, EanCodeIn,
    CartonIn, EanCodeSimple, CartonRowSimple, QcPackConfirmIn, LocationBlockIn,
    ProduceCellIn, ProductionCardIn
)
from models.sku_map import (
    SourceType, OnlineChannel, Marketplace, Platform, ConfigRole,
    SkuMapIn, SkuMapUpdate, ParserTemplateIn, StyleColorMappingIn, SkuResolveIn,
    UnresolvedMapIn, ExportColumn, ExportTemplate, SheetLocator, HeaderLocator,
    ListingFormatConfigIn, ListingFormatConfigUpdate, CatalogueExportRequest,
    OrderImportFormatConfigIn, OrderImportFormatConfigUpdate, OrderImportConfiguredRequest,
    OnlineOrderImportResult
)
from models.settings import (
    StageDurationsIn
)
from models.expenses import (
    EXPENSE_CATEGORIES, ExpenseIn, ExpenseUpdate, RecurringExpenseIn, RecurringExpenseUpdate
)
from models.online_reconciliation import (
    DailyPaymentRow, DailyPaymentImportIn, SettlementImportIn, NonOrderDeductionRow, NonOrderDeductionIn, MonthlyOrderRow, StyleCostSnapshotIn, ReconciliationRunIn
)


__all__ = [
    # Auth
    "LoginInput", "UserCreate", "UserUpdate", "ForgotPasswordInput", "ResetPasswordInput",
    # Styles
    "OnlineStatus", "OnlineStatusEnum", "ONLINE_STATUS_SEQUENCE", "ONLINE_STATUS_SIDE_BRANCHES",
    "PLANNED_COMPONENTS", "StyleIn", "PlannedComponent", "StyleLifecycleUpsert", "OnlineStatusPatchIn",
    "ColorMasterIn", "ColorMasterUpdate",
    # Materials
    "MaterialIn", "BomItem", "LaborItem", "QuantityUpdate", "InventoryMovement",
    # Components
    "ComponentUpdate", "ComponentIn", "ComponentMasterUpdate", "ComponentBulkMatrix",
    "ComponentMovementIn", "StyleComponentMappingIn", "StyleComponentMappingUpdate",
    # Orders
    "PRODUCTION_STAGES", "POLineItem", "POIn", "ProductionStageUpdate",
    # Workers
    "WorkerIn", "AssignmentUpdate", "BulkAssign", "AdvanceIn",
    # Vendors
    "DEFAULT_CREDIT_DAYS", "PAYMENT_MODES", "GRNLineItem", "GRNIn", "PaymentIn",
    "VendorIn", "VendorUpdate", "VendorPOLineItem", "VendorPOIn", "VendorPOUpdate",
    "VendorPOReceiveItem", "VendorPOReceiveIn", "DefectIn",
    # Invoice & Packing
    "InvoiceGenerate", "DispatchCreate", "PackingListGenerate", "MergedPackingListGenerate",
    "PackingTemplateIn",
    # Inventory
    "MovementType", "ReferenceType", "AdjustmentField", "SizeMatrixCell",
    "FgInventoryIn", "FgInventoryUpdate", "StockReservation", "StockRelease",
    "FgStockMovementIn", "InventoryReservationIn",
    # WMS
    "PicklistItemIn", "PicklistIn", "PickItemIn", "PicklistPatchIn", "EanCodeIn",
    "CartonIn", "EanCodeSimple", "CartonRowSimple", "QcPackConfirmIn", "LocationBlockIn",
    "ProduceCellIn", "ProductionCardIn",
    # SKU Map
    "SourceType", "OnlineChannel", "Marketplace", "Platform", "ConfigRole",
    "SkuMapIn", "SkuMapUpdate", "ParserTemplateIn", "StyleColorMappingIn", "SkuResolveIn",
    "UnresolvedMapIn", "ExportColumn", "ExportTemplate", "SheetLocator", "HeaderLocator",
    "ListingFormatConfigIn", "ListingFormatConfigUpdate", "CatalogueExportRequest",
    "OrderImportFormatConfigIn", "OrderImportFormatConfigUpdate", "OrderImportConfiguredRequest",
    "OnlineOrderImportResult",
    # Settings
    "StageDurationsIn",
    # Expenses
    "EXPENSE_CATEGORIES", "ExpenseIn", "ExpenseUpdate", "RecurringExpenseIn", "RecurringExpenseUpdate",
    # Online Reconciliation
    "DailyPaymentRow", "DailyPaymentImportIn", "SettlementImportIn", "NonOrderDeductionRow", "NonOrderDeductionIn", "MonthlyOrderRow", "StyleCostSnapshotIn", "ReconciliationRunIn",
]
