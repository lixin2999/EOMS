from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

TZ = ZoneInfo(settings.timezone)


def now() -> datetime:
    """统一使用业务时区（Asia/Shanghai）的本地时间，数据库存 naive datetime。"""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def today() -> date:
    return now().date()


def to_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"日期格式不正确: {value}")


def to_datetime(value: date | datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"日期时间格式不正确: {value}")


def period_of(value: date | datetime | None = None) -> str:
    value = value or now()
    return value.strftime("%Y-%m")


def month_start(value: date | datetime | None = None) -> date:
    value = value or today()
    return value.replace(day=1)


def month_end(value: date | datetime | None = None) -> date:
    start = month_start(value)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def add_days(value: datetime, days: int) -> datetime:
    return value + timedelta(days=days)


def is_overlap(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
    return start1 < end2 and start2 < end1


def parse_period(period: str) -> tuple[date, date]:
    try:
        year, month = [int(part) for part in period.split("-")]
        start = date(year, month, 1)
    except (ValueError, AttributeError) as exc:
        raise ValueError("期间格式应为 YYYY-MM") from exc
    return start, month_end(start)
