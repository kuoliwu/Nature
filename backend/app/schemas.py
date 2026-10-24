from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HealthOut(BaseModel):
    status: str
    app: str
    db_initialized: bool
    server_time: datetime


class InitDBIn(BaseModel):
    reset: bool = Field(False, description="True = 刪除所有資料表後重建（資料全清）")
    confirm: str | None = Field(None, description='reset=True 時必須填 "RESET"')
    seed_checklist: bool = Field(True, description="寫入預設的窗類 / 水電類檢查項目")


class InitDBOut(BaseModel):
    message: str
    was_initialized: bool
    tables: list[str]
    seeded: dict[str, int] | None


class TableCount(BaseModel):
    table: str
    rows: int


class DBStatusOut(BaseModel):
    db_initialized: bool
    database: str
    tables: list[TableCount]


# --- 建案 / 戶別 -----------------------------------------------------------
class ProjectIn(BaseModel):
    name: str = Field(..., max_length=100)
    phone: str | None = Field(None, max_length=30)
    community_address: str | None = Field(None, max_length=255)
    community_manager: str | None = Field(None, max_length=50)
    note: str | None = None


class ProjectOut(ProjectIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class UnitIn(BaseModel):
    unit_no: str = Field(..., max_length=30, description="戶別，例如 A-5F-1")
    building: str | None = None
    floor: str | None = None
    address: str | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_email: EmailStr | None = None
    owner_id_number: str | None = Field(None, description="身分證字號，只會以雜湊值儲存")


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    unit_no: str
    building: str | None
    floor: str | None
    address: str | None
    owner_name: str | None
    owner_phone: str | None
    owner_email: str | None
    has_id_verification: bool
    report_upload_enabled: bool


# --- 檢查項目 -------------------------------------------------------------
class CheckPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class InspectionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    check_points: list[CheckPointOut]


class InspectionCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    items: list[InspectionItemOut]
