import re
from datetime import date, datetime, time
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


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
    batch_counts: dict[str, int] = {}  # 各階段的預約設定數：visit / inspection / health_check


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
    service_type: str = Field("health_check", pattern="^(visit|inspection|health_check)$")
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
    units: list[str] = []  # 已預約的戶別


class BatchDayOut(BaseModel):
    date: date
    slots: list[SlotOut]


class BatchOut(BaseModel):
    id: int
    project_id: int
    name: str
    service_type: str
    description: str | None = None
    booking_open_at: datetime | None = None
    booking_close_at: datetime | None = None
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


def password_problem(password: str) -> str | None:
    """密碼規則（系統可從外網連線，不能太簡單）；符合回傳 None"""
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "密碼至少 8 碼，且需同時包含英文字母與數字"
    return None


def _check_password(password: str) -> str:
    if problem := password_problem(password):
        raise ValueError(problem)
    return password


Password = Annotated[str, Field(min_length=8, max_length=72, description="至少 8 碼，含英文字母與數字"), AfterValidator(_check_password)]


class SetupIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    phone: str = PhoneStr
    password: Password


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
    password: Password
    role: str = Field("staff", pattern="^(staff|super_admin)$")
    permissions: list[str] = []


class UserUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    phone: str | None = Field(None, min_length=8, max_length=20)
    role: str | None = Field(None, pattern="^(staff|super_admin)$")
    is_active: bool | None = None
    permissions: list[str] | None = None
    password: Password | None = Field(None, description="填寫時重設密碼")


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: Password


class PermissionOut(BaseModel):
    code: str
    label: str


# --- 第二階段：預約邀請與屋主預約 ---------------------------------------
class BatchSettingsIn(BaseModel):
    description: str | None = Field(None, max_length=2000, description="預約說明，會顯示在邀請信與預約頁")
    booking_open_at: datetime | None = Field(None, description="開放預約時間；空白代表立即開放")
    booking_close_at: datetime | None = Field(None, description="預約截止時間；空白代表不限")


class InviteSendIn(BaseModel):
    unit_ids: list[int] | None = Field(None, description="指定要寄的戶；不傳代表全部住戶")
    resend: bool = Field(False, description="True：已寄過的也再寄一次")


class InviteSendOut(BaseModel):
    sent: list[str]
    no_email: list[str]  # 沒有屋主 Email，無法寄送
    already_sent: list[str]  # 已寄過（resend=False 時略過）
    already_booked: list[str]  # 已預約，不再寄


class InviteBookingOut(BaseModel):
    id: int
    slot_id: int
    date: date
    start_time: time
    end_time: time
    contact_name: str
    contact_phone: str
    contact_email: str | None


class InviteStatusOut(BaseModel):
    unit_id: int
    unit_no: str
    owner_name: str | None
    owner_email: str | None
    link: str | None  # 已產生邀請時才有，可複製傳給屋主
    sent_at: datetime | None
    send_count: int
    last_opened_at: datetime | None
    booking: InviteBookingOut | None


class PublicSlot(BaseModel):
    id: int
    start_time: time
    end_time: time
    remaining: int


class PublicDay(BaseModel):
    date: date
    slots: list[PublicSlot]


class PublicCurrentBooking(BaseModel):
    slot_id: int
    date: date
    start_time: time
    end_time: time
    contact_name: str
    contact_phone: str
    contact_email: str | None
    can_change: bool


class PublicBookingInfo(BaseModel):
    project_name: str
    unit_no: str
    place: str
    batch_name: str
    service_label: str
    description: str | None
    closed_reason: str | None  # 非 None 代表目前不能預約
    close_at: datetime | None
    defaults: dict  # 聯絡資料預設值（屋主姓名 / 電話 / Email）
    current: PublicCurrentBooking | None
    days: list[PublicDay]


class PublicBookIn(BaseModel):
    slot_id: int
    contact_name: str = Field(..., min_length=1, max_length=50)
    contact_phone: str = Field(..., min_length=6, max_length=20)
    contact_email: EmailStr
    note: str | None = Field(None, max_length=500)


class PublicBookOut(BaseModel):
    message: str
    current: PublicCurrentBooking


# --- 第三階段：驗屋 -------------------------------------------------------
class ScheduleItem(BaseModel):
    booking_id: int
    project_id: int
    project_name: str
    unit_no: str
    place: str
    date: date
    start_time: time
    end_time: time
    contact_name: str
    contact_phone: str
    status: str  # not_started / in_progress / signed / approved / sent；參觀為 not_started / checked_in
    checked: int
    total: int
    fail_count: int
    service_type: str = "inspection"  # visit / inspection / health_check
    checked_in_at: datetime | None = None


class InspectionPhotoOut(BaseModel):
    id: int
    check_point_id: int | None
    url: str  # 已含短效 token，可直接給 <Image> 顯示
    caption: str | None


class InspectionPointOut(BaseModel):
    id: int
    name: str
    result: str  # pending / pass / fail / na
    note: str | None
    photos: list[InspectionPhotoOut]


class InspectionItemOut(BaseModel):
    id: int
    name: str
    points: list[InspectionPointOut]


class InspectionCategoryBlock(BaseModel):
    id: int
    name: str
    items: list[InspectionItemOut]


class InspectionOut(BaseModel):
    booking_id: int
    unit_id: int
    project_name: str
    unit_no: str
    place: str
    date: date
    start_time: time
    end_time: time
    contact_name: str
    contact_phone: str
    status: str
    service_type: str
    checked_in_at: datetime | None
    general_note: str | None
    inspector_name: str | None
    signer_name: str | None
    signed_at: datetime | None
    signature_url: str | None
    approved_at: datetime | None
    approver_name: str | None
    sent_at: datetime | None
    sent_to: str | None
    default_email: str | None  # 寄送報告預設的收件人（預約聯絡 Email，否則屋主 Email）
    external_report: "ExternalReportOut | None" = None  # 上傳的外部報告 PDF
    upload_enabled: bool = True  # 該戶的報告上傳開關（上傳後自動關閉）
    checked: int
    total: int
    fail_count: int
    categories: list[InspectionCategoryBlock]
    general_photos: list[InspectionPhotoOut]


class ResultIn(BaseModel):
    result: str | None = Field(None, pattern="^(pending|pass|fail|na)$")
    note: str | None = Field(None, max_length=1000)


class InspectionNoteIn(BaseModel):
    general_note: str | None = Field(None, max_length=3000)


class SignIn(BaseModel):
    signer_name: str = Field(..., min_length=1, max_length=50)
    strokes: list[list[tuple[float, float]]] = Field(..., min_length=1, max_length=500)
    width: float = Field(..., gt=0, le=5000)
    height: float = Field(..., gt=0, le=5000)


class ReportSendIn(BaseModel):
    to: EmailStr | None = Field(None, description="收件人；不填則用預約聯絡 Email")


class ReportLinkOut(BaseModel):
    url: str
    filename: str


# --- 外部報告、報告追蹤、備份 ---------------------------------------------
class ExternalReportOut(BaseModel):
    filename: str
    size: int
    uploaded_at: datetime
    uploaded_by: str | None
    url: str


class UploadSwitchIn(BaseModel):
    enabled: bool


class OverdueOut(BaseModel):
    booking_id: int
    project_name: str
    unit_no: str
    date: date
    start_time: time
    days: int
    inspection_status: str
    contact_name: str
    contact_phone: str
    reminded: list[int]


class ReminderRunOut(BaseModel):
    sent: int
    day7: list[str]
    day14: list[str]
    error: str | None = None


class BackupRunOut(BaseModel):
    database: str | None
    files_copied: int
    backup_dir: str
