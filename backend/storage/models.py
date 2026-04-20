from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    workspace: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="idle", nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    messages: Mapped[list["MessageRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tool_calls_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    session: Mapped[SessionRecord] = relationship(back_populates="messages")


class ProviderRecord(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # TODO: Encrypt provider API keys at rest instead of storing plaintext secrets.
    api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_model: Mapped[str] = mapped_column(String(100), nullable=False)
    available_models_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    extra_headers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MCPServerRecord(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    transport: Mapped[str] = mapped_column(String(10), nullable=False)
    command: Mapped[str] = mapped_column(Text, default="", nullable=False)
    args_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    env_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ScheduledTaskRecord(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    cron: Mapped[str] = mapped_column(String(100), default="0 * * * *", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    spec_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    notify_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    card_scenario: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # TODO: Migrate to datetime.now(UTC) + TIMESTAMP WITH TIME ZONE.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    last_run_output: Mapped[str] = mapped_column(Text, default="", nullable=False)


__all__ = [
    "Base",
    "MCPServerRecord",
    "MessageRecord",
    "ProviderRecord",
    "ScheduledTaskRecord",
    "SessionRecord",
]
