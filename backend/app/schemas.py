from datetime import datetime

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
