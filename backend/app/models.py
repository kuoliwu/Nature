"""資料庫 Schema（SQLAlchemy 2.0 ORM）

分區：
  1. 人員與權限        users, user_permissions
  2. 建案與戶別        projects, units
  3. 預約批次與時段    booking_batches, batch_services, time_slots, bookings
  4. 預約頁面設定      batch_faqs, batch_attachments,
                       custom_forms, custom_form_fields, form_submissions, form_submission_files
  5. 檢查項目          inspection_categories, inspection_items, inspection_check_points, inspection_results
  6. 線上授權          authorizations
  7. 報告與提醒        reports, report_reminders
"""

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def enum_col(enum_cls: type[enum.Enum]) -> Enum:
    """以字串值（而非 Python 名稱）存入 DB，SQLite / PostgreSQL 皆可用"""
    return Enum(
        enum_cls,
        native_enum=False,
        length=30,
        values_callable=lambda e: [m.value for m in e],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"  # 擁有全部權限
    STAFF = "staff"  # 依 user_permissions 決定可做什麼


class ServiceType(str, enum.Enum):
    INSPECTION = "inspection"  # 驗屋
    HEALTH_CHECK = "health_check"  # 健檢


class QuotaMode(str, enum.Enum):
    SHARED = "shared"  # 同時段所有服務項目共用 time_slots.capacity
    INDEPENDENT = "independent"  # 每個服務項目各自用 batch_services.capacity_per_slot


class BookingStatus(str, enum.Enum):
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class FormFieldType(str, enum.Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    DATE = "date"
    SELECT = "select"
    CHECKBOX = "checkbox"
    FILE = "file"


class CheckResult(str, enum.Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    NA = "na"


class AuthorizationStatus(str, enum.Enum):
    PENDING_OWNER = "pending_owner"  # 等待屋主簽名
    PENDING_TRUSTEE = "pending_trustee"  # 已寄邀請，等待受託人簽名
    COMPLETED = "completed"  # 雙方簽署完成、PDF 已產生
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# 權限代碼（存在 user_permissions.permission）
PERMISSIONS: dict[str, str] = {
    "project.manage": "建案 / 戶別管理",
    "batch.manage": "預約批次與頁面設定",
    "booking.view": "檢視預約時間表",
    "booking.manage": "新增 / 修改 / 取消預約",
    "inspection.edit": "填寫檢查結果",
    "report.manage": "管理驗屋報告",
    "user.manage": "人員與權限管理",
}


# ---------------------------------------------------------------------------
# 1. 人員與權限
# ---------------------------------------------------------------------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # 手機號碼登入
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(enum_col(UserRole), default=UserRole.STAFF)
    is_active: Mapped[bool] = mapped_column(default=True)

    permissions: Mapped[list["UserPermission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "permission", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permission: Mapped[str] = mapped_column(String(50))  # 見 PERMISSIONS
    # NULL = 所有建案皆適用；有值 = 只限該建案
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))

    user: Mapped[User] = relationship(back_populates="permissions")


# ---------------------------------------------------------------------------
# 2. 建案與戶別
# ---------------------------------------------------------------------------
class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)  # 案名
    phone: Mapped[str | None] = mapped_column(String(30))  # 電話
    community_address: Mapped[str | None] = mapped_column(String(255))  # 社區地址
    community_manager: Mapped[str | None] = mapped_column(String(50))  # 社區經理
    note: Mapped[str | None] = mapped_column(Text)

    units: Mapped[list["Unit"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    batches: Mapped[list["BookingBatch"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Unit(TimestampMixin, Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("project_id", "unit_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    building: Mapped[str | None] = mapped_column(String(20))  # 棟別
    floor: Mapped[str | None] = mapped_column(String(10))
    unit_no: Mapped[str] = mapped_column(String(30))  # 戶別，如 A-5F-1
    address: Mapped[str | None] = mapped_column(String(255))  # 住家地址

    owner_name: Mapped[str | None] = mapped_column(String(50))
    owner_phone: Mapped[str | None] = mapped_column(String(20))
    owner_email: Mapped[str | None] = mapped_column(String(255))
    # 身分證只存雜湊（SHA-256 + 鹽），用於預約時「強制身分證驗證」防選錯戶別
    owner_id_hash: Mapped[str | None] = mapped_column(String(64))

    # 報告上傳開關：上傳成功後自動關閉，避免重複上傳
    report_upload_enabled: Mapped[bool] = mapped_column(default=True)

    project: Mapped[Project] = relationship(back_populates="units")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="unit")

    @property
    def has_id_verification(self) -> bool:
        return self.owner_id_hash is not None


# ---------------------------------------------------------------------------
# 3. 預約批次與時段
# ---------------------------------------------------------------------------
class BookingBatch(TimestampMixin, Base):
    """一個建案的一次預約活動，例如「2026 交屋驗屋」或「一年保固健檢」"""

    __tablename__ = "booking_batches"
    __table_args__ = (
        CheckConstraint("slot_minutes > 0", name="ck_batch_slot_minutes"),
        CheckConstraint("slot_capacity > 0", name="ck_batch_slot_capacity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    service_type: Mapped[ServiceType] = mapped_column(enum_col(ServiceType))

    # 排程規則：每時段 30 分鐘、同時段最多 3 組
    slot_minutes: Mapped[int] = mapped_column(default=30)
    slot_capacity: Mapped[int] = mapped_column(default=3)  # 產生時段時的預設名額
    quota_mode: Mapped[QuotaMode] = mapped_column(enum_col(QuotaMode), default=QuotaMode.SHARED)

    # 前端預約頁面設定
    booking_open_at: Mapped[datetime | None]  # 自動開放時間
    booking_close_at: Mapped[datetime | None]  # 自動關閉時間
    require_id_verification: Mapped[bool] = mapped_column(default=True)
    description: Mapped[str | None] = mapped_column(Text)  # 預約說明文字
    is_active: Mapped[bool] = mapped_column(default=True)

    project: Mapped[Project] = relationship(back_populates="batches")
    services: Mapped[list["BatchService"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="BatchService.sort_order"
    )
    slots: Mapped[list["TimeSlot"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    faqs: Mapped[list["BatchFAQ"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="BatchFAQ.sort_order"
    )
    attachments: Mapped[list["BatchAttachment"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="BatchAttachment.sort_order"
    )
    forms: Mapped[list["CustomForm"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class BatchService(Base):
    """批次內可預約的服務項目（例：驗屋、健檢、複驗）。
    quota_mode=independent 時，各項目用自己的 capacity_per_slot 計算名額。"""

    __tablename__ = "batch_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("booking_batches.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    capacity_per_slot: Mapped[int] = mapped_column(default=3)
    sort_order: Mapped[int] = mapped_column(default=0)

    batch: Mapped[BookingBatch] = relationship(back_populates="services")


class TimeSlot(Base):
    __tablename__ = "time_slots"
    __table_args__ = (
        UniqueConstraint("batch_id", "slot_date", "start_time"),
        CheckConstraint("capacity > 0", name="ck_slot_capacity"),
        CheckConstraint("end_time > start_time", name="ck_slot_time_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("booking_batches.id", ondelete="CASCADE"), index=True)
    slot_date: Mapped[date] = mapped_column(index=True)  # 健檢日期
    start_time: Mapped[time]
    end_time: Mapped[time]
    capacity: Mapped[int] = mapped_column(default=3)  # 共用名額模式下的上限
    is_open: Mapped[bool] = mapped_column(default=True)

    batch: Mapped[BookingBatch] = relationship(back_populates="slots")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="slot")


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_slot_status", "slot_id", "status"),
        # 同一戶在同一批次只能有一筆「有效」預約（取消的不算）
        Index(
            "uq_bookings_unit_batch_active",
            "unit_id",
            "batch_id",
            unique=True,
            sqlite_where=text("status != 'cancelled'"),
            postgresql_where=text("status != 'cancelled'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("booking_batches.id", ondelete="CASCADE"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("time_slots.id", ondelete="RESTRICT"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("batch_services.id", ondelete="SET NULL"))

    contact_name: Mapped[str] = mapped_column(String(50))
    contact_phone: Mapped[str] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[BookingStatus] = mapped_column(enum_col(BookingStatus), default=BookingStatus.BOOKED)
    is_delegated: Mapped[bool] = mapped_column(default=False)  # 委託代驗 → 需走線上授權
    note: Mapped[str | None] = mapped_column(Text)

    slot: Mapped[TimeSlot] = relationship(back_populates="bookings")
    unit: Mapped[Unit] = relationship(back_populates="bookings")
    service: Mapped[BatchService | None] = relationship()
    results: Mapped[list["InspectionResult"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    authorizations: Mapped[list["Authorization"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    report: Mapped["Report | None"] = relationship(back_populates="booking", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 4. 預約頁面設定：FAQ、附件、客戶回傳表單
# ---------------------------------------------------------------------------
class BatchFAQ(Base):
    __tablename__ = "batch_faqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("booking_batches.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(String(255))
    answer: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(default=0)

    batch: Mapped[BookingBatch] = relationship(back_populates="faqs")


class BatchAttachment(Base):
    """預約頁面上供下載的附件"""

    __tablename__ = "batch_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("booking_batches.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    file_path: Mapped[str] = mapped_column(String(500))  # 相對於 storage_dir
    original_filename: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    batch: Mapped[BookingBatch] = relationship(back_populates="attachments")


class CustomForm(TimestampMixin, Base):
    """客戶回傳功能：管理員動態建立的表單"""

    __tablename__ = "custom_forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("booking_batches.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)

    batch: Mapped[BookingBatch] = relationship(back_populates="forms")
    fields: Mapped[list["CustomFormField"]] = relationship(
        back_populates="form", cascade="all, delete-orphan", order_by="CustomFormField.sort_order"
    )
    submissions: Mapped[list["FormSubmission"]] = relationship(
        back_populates="form", cascade="all, delete-orphan"
    )


class CustomFormField(Base):
    __tablename__ = "custom_form_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("custom_forms.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    field_type: Mapped[FormFieldType] = mapped_column(enum_col(FormFieldType))
    required: Mapped[bool] = mapped_column(default=False)
    options: Mapped[list | None] = mapped_column(JSON)  # select / checkbox 的選項
    sort_order: Mapped[int] = mapped_column(default=0)

    form: Mapped[CustomForm] = relationship(back_populates="fields")


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("custom_forms.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # {field_id: value}
    submitted_at: Mapped[datetime] = mapped_column(default=datetime.now)

    form: Mapped[CustomForm] = relationship(back_populates="submissions")
    files: Mapped[list["FormSubmissionFile"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class FormSubmissionFile(Base):
    __tablename__ = "form_submission_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("form_submissions.id", ondelete="CASCADE"), index=True
    )
    field_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_form_fields.id", ondelete="SET NULL")
    )
    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int]

    submission: Mapped[FormSubmission] = relationship(back_populates="files")


# ---------------------------------------------------------------------------
# 5. 檢查項目
#   類別(窗類) → 項目(陽台窗) → 檢查點(膠條 / 密合度 / 五金)
#   類別(水電類) → 項目(給水) → 檢查點(浴室 / 陽台 / 廚房)
# ---------------------------------------------------------------------------
class InspectionCategory(Base):
    __tablename__ = "inspection_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(default=0)

    items: Mapped[list["InspectionItem"]] = relationship(
        back_populates="category", cascade="all, delete-orphan", order_by="InspectionItem.sort_order"
    )


class InspectionItem(Base):
    __tablename__ = "inspection_items"
    __table_args__ = (UniqueConstraint("category_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_categories.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

    category: Mapped[InspectionCategory] = relationship(back_populates="items")
    check_points: Mapped[list["InspectionCheckPoint"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="InspectionCheckPoint.sort_order"
    )


class InspectionCheckPoint(Base):
    __tablename__ = "inspection_check_points"
    __table_args__ = (UniqueConstraint("item_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inspection_items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(default=0)

    item: Mapped[InspectionItem] = relationship(back_populates="check_points")


class InspectionResult(Base):
    """某筆預約對某個檢查點的結果"""

    __tablename__ = "inspection_results"
    __table_args__ = (UniqueConstraint("booking_id", "check_point_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    check_point_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_check_points.id", ondelete="RESTRICT")
    )
    result: Mapped[CheckResult] = mapped_column(enum_col(CheckResult), default=CheckResult.PENDING)
    note: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(500))
    inspected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    inspected_at: Mapped[datetime | None]

    booking: Mapped[Booking] = relationship(back_populates="results")
    check_point: Mapped[InspectionCheckPoint] = relationship()


# ---------------------------------------------------------------------------
# 6. 線上授權（委託代驗）
# ---------------------------------------------------------------------------
class Authorization(TimestampMixin, Base):
    __tablename__ = "authorizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    status: Mapped[AuthorizationStatus] = mapped_column(
        enum_col(AuthorizationStatus), default=AuthorizationStatus.PENDING_OWNER
    )

    owner_name: Mapped[str] = mapped_column(String(50))
    owner_email: Mapped[str | None] = mapped_column(String(255))
    owner_signature_path: Mapped[str | None] = mapped_column(String(500))  # 簽名 PNG
    owner_signed_at: Mapped[datetime | None]

    trustee_name: Mapped[str | None] = mapped_column(String(50))
    trustee_email: Mapped[str] = mapped_column(String(255))
    trustee_signature_path: Mapped[str | None] = mapped_column(String(500))
    trustee_signed_at: Mapped[datetime | None]

    # 簽署邀請連結用的一次性 token
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    invite_sent_at: Mapped[datetime | None]
    invite_expires_at: Mapped[datetime | None]

    pdf_path: Mapped[str | None] = mapped_column(String(500))  # 產生的授權書 PDF
    completed_at: Mapped[datetime | None]

    booking: Mapped[Booking] = relationship(back_populates="authorizations")


# ---------------------------------------------------------------------------
# 7. 報告與自動提醒
# ---------------------------------------------------------------------------
class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("file_size > 0 AND file_size <= 31457280", name="ck_report_size_30mb"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 一筆預約只對應一份 PDF 報告
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), unique=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int]
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(default=datetime.now)

    booking: Mapped[Booking] = relationship(back_populates="report")


class ReportReminder(Base):
    """預約日後 7 / 14 天未上傳報告的提醒紀錄；唯一鍵確保同一階段只寄一次"""

    __tablename__ = "report_reminders"
    __table_args__ = (UniqueConstraint("booking_id", "reminder_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    reminder_day: Mapped[int]  # 7 或 14
    recipient_email: Mapped[str] = mapped_column(String(255))
    sent_at: Mapped[datetime] = mapped_column(default=datetime.now)
    success: Mapped[bool] = mapped_column(default=True)
    error_message: Mapped[str | None] = mapped_column(Text)
