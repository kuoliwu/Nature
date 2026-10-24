from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HealthOut(BaseModel):
    status: str
    app: str
    db_initialized: bool
    needs_setup: bool  # 資料庫已建立但還沒有任何管理者帳號
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
    name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255, description="建案地址")
    community_address: str | None = Field(None, max_length=255, description="社區地址")
    community_manager: str | None = Field(None, max_length=50)
    note: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255, description="建案地址")
    community_address: str | None = Field(None, max_length=255, description="社區地址")
    community_manager: str | None = Field(None, max_length=50)
    note: str | None = None


class ProjectOut(ProjectIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    unit_count: int = 0
    batch_count: int = 0


class UnitIn(BaseModel):
    unit_no: str = Field(..., min_length=1, max_length=30, description="戶別，例如 A-5F-1")
    building: str | None = Field(None, max_length=20)
    floor: str | None = Field(None, max_length=10)
    address: str | None = Field(None, max_length=255)
    owner_name: str | None = Field(None, max_length=50)
    owner_phone: str | None = Field(None, max_length=20)
    owner_email: EmailStr | None = None
    area_ping: float | None = Field(None, ge=0, le=100000, description="坪數")
    handover_date: date | None = None
    note: str | None = None
    owner_id_number: str | None = Field(None, description="身分證字號，只會以雜湊值儲存（選填）")


class UnitUpdate(BaseModel):
    """只更新有傳的欄位；要清空某欄請傳 null"""

    unit_no: str | None = Field(None, min_length=1, max_length=30)
    building: str | None = Field(None, max_length=20)
    floor: str | None = Field(None, max_length=10)
    address: str | None = Field(None, max_length=255)
    owner_name: str | None = Field(None, max_length=50)
    owner_phone: str | None = Field(None, max_length=20)
    owner_email: EmailStr | None = None
    area_ping: float | None = Field(None, ge=0, le=100000)
    handover_date: date | None = None
    note: str | None = None


class UnitBulkItem(BaseModel):
    unit_no: str = Field(..., max_length=30)
    building: str | None = Field(None, max_length=20)
    floor: str | None = Field(None, max_length=10)


class UnitBulkIn(BaseModel):
    """unit_nos：只有戶別（手動貼上清單）；units：連同棟別、樓層（依棟別 × 樓層自動產生）"""

    unit_nos: list[str] | None = Field(None, max_length=2000, description="戶別清單，一個元素一戶")
    units: list[UnitBulkItem] | None = Field(None, max_length=2000)
    building: str | None = Field(None, max_length=20, description="套用到 unit_nos 每一戶的棟別")


class UnitBulkOut(BaseModel):
    created: list[str]
    skipped: list[str]  # 已存在或重複


class DownloadLinkOut(BaseModel):
    url: str
    filename: str
    expires_at: datetime


class ImportRowError(BaseModel):
    row: int  # Excel 列號
    message: str


class UnitImportOut(BaseModel):
    dry_run: bool  # True：只檢查、沒有寫入
    created: list[str]
    updated: list[str]
    unchanged: int
    errors: list[ImportRowError]


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
    area_ping: float | None
    handover_date: date | None
    note: str | None
    has_id_verification: bool
    report_upload_enabled: bool


# --- 健檢日期（預約批次）與時段 -------------------------------------------
class TimeRange(BaseModel):
    start: time
    end: time


class BatchIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    service_type: str = Field("health_check", pattern="^(inspection|health_check)$")
    start_date: date
    end_date: date
    day_start: time = Field(time(9, 0), description="每天第一個時段開始")
    day_end: time = Field(time(17, 0), description="每天最後一個時段結束")
    slot_minutes: int = Field(30, ge=10, le=240)
    slot_capacity: int = Field(3, ge=1, le=50, description="每個時段最多幾組")
    breaks: list[TimeRange] = Field([], max_length=10, description="每天的屏蔽區段，例如午休 12:00–13:00")


class BatchDatesIn(BaseModel):
    start_date: date
    end_date: date
    day_start: time = time(9, 0)
    day_end: time = time(17, 0)
    breaks: list[TimeRange] = Field([], max_length=10)


class BatchUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None


class SlotOut(BaseModel):
    id: int
    start_time: time
    end_time: time
    capacity: int
    booked: int
    is_open: bool


class BatchDayOut(BaseModel):
    date: date
    slots: list[SlotOut]


class BatchOut(BaseModel):
    id: int
    project_id: int
    name: str
    service_type: str
    slot_minutes: int
    slot_capacity: int
    quota_mode: str
    is_active: bool
    first_date: date | None
    last_date: date | None
    day_count: int
    slot_count: int
    open_slot_count: int
    booked_count: int


class BatchDetailOut(BatchOut):
    days: list[BatchDayOut]


class SlotUpdate(BaseModel):
    is_open: bool | None = None
    capacity: int | None = Field(None, ge=1, le=50)


class DayUpdate(BaseModel):
    is_open: bool


# --- 檢查項目清單（每個建案一份）------------------------------------------
class NameIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class ChecklistItemIn(NameIn):
    check_points: list[str] | None = Field(
        None, description="檢查點名稱；不傳時沿用同類別第一個項目的檢查點（例如窗戶的膠條 / 密合度 / 五金）"
    )


class ChecklistUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    is_active: bool | None = None
    sort_order: int | None = None


class ChecklistPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool
    sort_order: int


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool
    sort_order: int
    check_points: list[ChecklistPointOut]


class ChecklistCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool
    sort_order: int
    items: list[ChecklistItemOut]


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


# --- 線上授權 -------------------------------------------------------------
class OwnerAuthorizationIn(BaseModel):
    owner_name: str = Field(..., min_length=1, max_length=50)
    owner_email: EmailStr | None = Field(None, description="填寫後授權書 PDF 也會寄給屋主")
    owner_id_number: str | None = Field(None, description="批次要求身分證驗證時必填")
    trustee_name: str = Field(..., min_length=1, max_length=50)
    trustee_email: EmailStr
    owner_signature: str = Field(..., description="Base64 PNG，可含 data:image/png;base64, 開頭")


class TrusteeSignIn(BaseModel):
    trustee_signature: str = Field(..., description="Base64 PNG，可含 data:image/png;base64, 開頭")


class OwnerLinkOut(BaseModel):
    token: str
    expires_at: datetime
    public_url: str | None = Field(None, description="對外網址（外網可開啟）；未啟動通道時為 null")
    lan_url: str = Field(..., description="區網網址，只有同網路或 Tailscale 能開啟")


class BookingSummary(BaseModel):
    project_name: str
    unit_no: str
    inspection_date: str
    require_id_verification: bool


class SignInviteInfo(BaseModel):
    status: str
    owner_name: str
    trustee_name: str
    trustee_email: str
    project_name: str
    unit_no: str
    inspection_date: str
    expires_at: datetime | None


class AuthorizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    status: str
    owner_name: str
    owner_email: str | None
    owner_signed_at: datetime | None
    trustee_name: str | None
    trustee_email: str
    trustee_signed_at: datetime | None
    invite_sent_at: datetime | None
    invite_expires_at: datetime | None
    has_pdf: bool
    completed_at: datetime | None


# --- 登入與人員 -----------------------------------------------------------
PhoneStr = Field(..., min_length=8, max_length=20, description="手機號碼，登入帳號")
PasswordStr = Field(..., min_length=8, max_length=72, description="至少 8 碼")


class SetupIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    phone: str = PhoneStr
    password: str = PasswordStr


class LoginIn(BaseModel):
    phone: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    phone: str
    role: str
    is_active: bool
    permissions: list[str]
    created_at: datetime


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class UserCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    phone: str = PhoneStr
    password: str = PasswordStr
    role: str = Field("staff", pattern="^(staff|super_admin)$")
    permissions: list[str] = []


class UserUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    phone: str | None = Field(None, min_length=8, max_length=20)
    role: str | None = Field(None, pattern="^(staff|super_admin)$")
    is_active: bool | None = None
    permissions: list[str] | None = None
    password: str | None = Field(None, min_length=8, max_length=72, description="填寫時重設密碼")


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = PasswordStr


class PermissionOut(BaseModel):
    code: str
    label: str
