"""Invoicing & Packing List Pydantic Models."""

from typing import List, Optional
from pydantic import BaseModel


class InvoiceGenerate(BaseModel):
    po_id: str
    job_ids: Optional[List[str]] = None
    transport_mode: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    supply_date: Optional[str] = ""


class DispatchCreate(BaseModel):
    job_ids: List[str]
    po_id: str
    transport_mode: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    supply_date: Optional[str] = ""
    transporter: Optional[str] = ""
    dispatch_date: Optional[str] = ""
    carton_dim: Optional[str] = "60x50x30 CMS"
    net_wt_per_carton: Optional[float] = None
    gross_wt_per_carton: Optional[float] = None
    template_id: Optional[str] = None
    driver_name: Optional[str] = ""
    driver_phone: Optional[str] = ""
    site_code: Optional[str] = ""
    destination: Optional[str] = ""
    port: Optional[str] = ""
    notes: Optional[str] = ""


class PackingListGenerate(BaseModel):
    po_id: str
    job_ids: Optional[List[str]] = None
    template_id: Optional[str] = None
    carton_dim: Optional[str] = "60x50x30 CMS"
    pcs_per_box: Optional[int] = 20
    net_wt_per_carton: Optional[float] = 10.8
    gross_wt_per_carton: Optional[float] = 12.0
    dispatch_date: Optional[str] = ""
    transporter: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    driver_name: Optional[str] = ""
    driver_phone: Optional[str] = ""
    site_code: Optional[str] = ""
    destination: Optional[str] = ""
    port: Optional[str] = ""
    notes: Optional[str] = ""


class MergedPackingListGenerate(BaseModel):
    job_ids: List[str]
    template_id: Optional[str] = None
    carton_dim: Optional[str] = "60x50x30 CMS"
    pcs_per_box: Optional[int] = 20
    net_wt_per_carton: Optional[float] = 10.8
    gross_wt_per_carton: Optional[float] = 12.0
    sectioned: Optional[bool] = False
    dispatch_date: Optional[str] = ""
    transporter: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    driver_name: Optional[str] = ""
    driver_phone: Optional[str] = ""
    site_code: Optional[str] = ""
    destination: Optional[str] = ""
    port: Optional[str] = ""
    notes: Optional[str] = ""


class PackingTemplateIn(BaseModel):
    client_name: str
    name: str
    aliases: Optional[List[str]] = None
    file_b64: str
