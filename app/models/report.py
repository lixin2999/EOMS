from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin
from app.utils.datetime import now


class ReportSnapshot(Base, IdMixin):
    __tablename__ = "rpt_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "report_code", "period", "dim_type", "dim_value",
            name="uq_rpt_snapshot_company_report_period_dim",
        ),
        Index("ix_rpt_snapshot_report_period", "report_code", "period"),
    )

    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    report_code: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    dim_type: Mapped[str] = mapped_column(String(32), default="COMPANY", nullable=False)
    dim_value: Mapped[str] = mapped_column(String(64), default="0", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
