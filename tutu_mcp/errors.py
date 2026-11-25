import os
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


class TutuError(Exception):
    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code, self.details = code, details


def checked_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_date(value: str, now: datetime | None = None) -> None:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        departure = date.fromisoformat(value)
    except ValueError:
        raise TutuError("INVALID_DATE", "Нужна существующая дата YYYY-MM-DD") from None
    today = (now or datetime.now(timezone.utc)).astimezone(
        ZoneInfo(os.environ.get("USER_TIMEZONE", "Europe/Moscow"))
    ).date()
    if departure < today:
        raise TutuError("PAST_DATE", "Дата отправления уже прошла")
