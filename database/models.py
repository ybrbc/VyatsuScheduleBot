"""SQLAlchemy ORM models."""
from __future__ import annotations
from datetime import date, time, datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey,
    Integer, JSON, String, Text, Time, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    periods: Mapped[List["SchedulePeriod"]] = relationship(back_populates="group")
    users: Mapped[List["User"]] = relationship(back_populates="group")
    pdf_hashes: Mapped[List["PdfHash"]] = relationship(back_populates="group")

    def __repr__(self) -> str:
        return f"<Group {self.external_id}>"


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    subjects: Mapped[List["Subject"]] = relationship(back_populates="teacher")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("title", "lesson_type", "teacher_id", "subgroup", name="uq_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(300))
    lesson_type: Mapped[Optional[str]] = mapped_column(String(50))
    teacher_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("teachers.id"))
    subgroup: Mapped[Optional[str]] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    teacher: Mapped[Optional["Teacher"]] = relationship(back_populates="subjects")
    lessons: Mapped[List["Lesson"]] = relationship(back_populates="subject")
    excluded_by: Mapped[List["ExcludedSubject"]] = relationship(back_populates="subject")


class SubjectProgressTarget(Base):
    """Configured total academic hours for a subject/type/subgroup.

    ``subgroup`` is stored as an empty string for lessons common to the whole
    group.  Keeping it non-null makes the uniqueness rule work identically on
    PostgreSQL and SQLite.
    """
    __tablename__ = "subject_progress_targets"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "title", "lesson_type", "subgroup",
            name="uq_subject_progress_target",
        ),
        CheckConstraint("total_hours > 0", name="ck_subject_progress_total_hours"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    lesson_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subgroup: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lessons: Mapped[List["Lesson"]] = relationship(back_populates="room")


class TimeSlot(Base):
    __tablename__ = "time_slots"
    __table_args__ = (
        UniqueConstraint("start_time", "end_time", name="uq_time_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    lessons: Mapped[List["Lesson"]] = relationship(back_populates="time_slot")

    @property
    def label(self) -> str:
        return f"{self.start_time.strftime('%H:%M')}–{self.end_time.strftime('%H:%M')}"


class SchedulePeriod(Base):
    __tablename__ = "schedule_periods"
    __table_args__ = (
        UniqueConstraint("group_id", "start_date", "end_date", name="uq_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    academic_year: Mapped[Optional[str]] = mapped_column(String(10))
    is_session: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    group: Mapped["Group"] = relationship(back_populates="periods")
    days: Mapped[List["ScheduleDay"]] = relationship(
        back_populates="period", cascade="all, delete-orphan", lazy="select"
    )


class ScheduleDay(Base):
    __tablename__ = "schedule_days"
    __table_args__ = (
        UniqueConstraint("period_id", "date", name="uq_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("schedule_periods.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    period: Mapped["SchedulePeriod"] = relationship(back_populates="days")
    lessons: Mapped[List["Lesson"]] = relationship(
        back_populates="day", cascade="all, delete-orphan"
    )


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("schedule_days.id", ondelete="CASCADE"), nullable=False
    )
    time_slot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("time_slots.id"))
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id"))
    room_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rooms.id"))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    day: Mapped["ScheduleDay"] = relationship(back_populates="lessons")
    time_slot: Mapped[Optional["TimeSlot"]] = relationship(back_populates="lessons")
    subject: Mapped[Optional["Subject"]] = relationship(back_populates="lessons")
    room: Mapped[Optional["Room"]] = relationship(back_populates="lessons")


class PdfHash(Base):
    __tablename__ = "pdf_hashes"
    __table_args__ = (
        UniqueConstraint("group_id", "period_start", "period_end", name="uq_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    group: Mapped["Group"] = relationship(back_populates="pdf_hashes")


class ScheduleChange(Base):
    __tablename__ = "schedule_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"), nullable=False)
    lesson_date: Mapped[date] = mapped_column(Date, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    old_data: Mapped[Optional[dict]] = mapped_column(JSON)
    new_data: Mapped[Optional[dict]] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("groups.id"))
    subgroup: Mapped[Optional[str]] = mapped_column(String(10))   # "01","02", None=all

    # Notifications
    change_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_time: Mapped[Optional[time]] = mapped_column(Time)
    # True → send tomorrow's schedule at notification time; False → send today's
    daily_send_tomorrow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_daily_sent: Mapped[Optional[date]] = mapped_column(Date)

    # Display: how to render lessons of the OTHER subgroup
    # hide | strikethrough | spoiler | spoiler_strikethrough
    display_mode: Mapped[str] = mapped_column(String(30), default="hide")

    # Display for OTHER subgroup's diff changes in notifications
    # hide | inline_strikethrough | inline_spoiler | separate
    diff_display_mode: Mapped[str] = mapped_column(String(30), default="hide")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    group: Mapped[Optional["Group"]] = relationship(back_populates="users")
    excluded_subjects: Mapped[List["ExcludedSubject"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ExcludedSubject(Base):
    __tablename__ = "excluded_subjects"
    __table_args__ = (
        UniqueConstraint("user_id", "subject_id", name="uq_excluded"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="excluded_subjects")
    subject: Mapped["Subject"] = relationship(back_populates="excluded_by")


class UserSubjectFilter(Base):
    """Per-user filter for a specific Subject row (keyed by subject_id).

    filter_type:
      always_show — show even if other-subgroup / display_mode would hide it.
      never_show  — always hide, even for the user's own subgroup.

    Because each Subject row encodes title + lesson_type + teacher + subgroup,
    users can independently filter e.g. "Элективные / пд.01 / Полубоярцев"
    without affecting "Элективные / пд.01 / Крестьянинова".
    """
    __tablename__ = "user_subject_filters"
    __table_args__ = (
        UniqueConstraint("user_id", "subject_id", name="uq_usr_sbj_filter"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    filter_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user: Mapped["User"] = relationship(back_populates="subject_filters")
    subject: Mapped["Subject"] = relationship()


# Add back-reference to User
User.subject_filters = relationship(   # type: ignore[attr-defined]
    "UserSubjectFilter", back_populates="user", cascade="all, delete-orphan"
)


class DailyNotificationLog(Base):
    """Tracks which schedule date was sent to each user on each calendar day.

    Used to resend the updated schedule if the target date's lessons change
    after the initial notification was delivered.
    """
    __tablename__ = "daily_notification_logs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "target_date", "notification_date",
            name="uq_daily_log",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The date whose schedule was sent (today or tomorrow at send time)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Calendar date the notification was dispatched
    notification_date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Updated each time we resend; None = never resent
    last_resent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship()
