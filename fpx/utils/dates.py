"""Даты, как их пишет FunPay на страницах: «сегодня, 12:00», «12 сентября, 12:00», «5 января 2025, 9:30»."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# FunPay показывает московское время. Москва с 2014 года живёт в UTC+3 без перевода часов,
# поэтому фиксированного смещения достаточно (так же считает FunPayAPI).
MOSCOW_TZ = timezone(timedelta(hours=3), "MSK")

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
    "січня": 1,
    "лютого": 2,
    "березня": 3,
    "квітня": 4,
    "травня": 5,
    "червня": 6,
    "липня": 7,
    "серпня": 8,
    "вересня": 9,
    "жовтня": 10,
    "листопада": 11,
    "грудня": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_TODAY = ("сегодня", "сьогодні", "today")
_YESTERDAY = ("вчера", "вчора", "yesterday")

_RELATIVE_RE = re.compile(r"^(?P<word>\w+),\s*(?P<h>\d{1,2}):(?P<m>\d{2})$")
_ABSOLUTE_RE = re.compile(
    r"^(?P<day>\d{1,2})\s+(?P<month>[^\W\d_]+)(?:\s+(?P<year>\d{4}))?,\s*(?P<h>\d{1,2}):(?P<m>\d{2})$"
)


def parse_funpay_datetime(date_text: str | None, now: datetime | None = None) -> datetime | None:
    """Разбирает дату со страниц FunPay в aware-``datetime`` по Москве.

    Перенос ``FunPayAPI.common.utils.parse_funpay_datetime``: те же формы и те же месяцы
    (ru / uk / en), но регистр не важен, а нераспознанный текст даёт ``None`` вместо исключения.

    Args:
        date_text: Текст вида ``сегодня, 1:41``, ``Вчера, 23:10``, ``12 сентября, 12:00``,
            ``5 января 2025, 9:30``.
        now: Текущий момент (для тестов); по умолчанию — сейчас по Москве.
    Returns:
        ``datetime`` с ``tzinfo=MOSCOW_TZ`` или ``None``, если текст не похож на дату FunPay.
    """
    if not date_text:
        return None
    text = " ".join(date_text.split()).lower()
    if not text:
        return None
    current = (now or datetime.now(MOSCOW_TZ)).astimezone(MOSCOW_TZ)
    try:
        relative = _RELATIVE_RE.match(text)
        if relative:
            word = relative.group("word")
            if word in _TODAY:
                day = current
            elif word in _YESTERDAY:
                day = current - timedelta(days=1)
            else:
                return None
            return datetime(
                day.year, day.month, day.day, int(relative.group("h")), int(relative.group("m")), tzinfo=MOSCOW_TZ
            )
        absolute = _ABSOLUTE_RE.match(text)
        if absolute:
            month = _MONTHS.get(absolute.group("month"))
            if month is None:
                return None
            # Год FunPay пишет только у дат не из текущего года.
            year = int(absolute.group("year")) if absolute.group("year") else current.year
            return datetime(
                year,
                month,
                int(absolute.group("day")),
                int(absolute.group("h")),
                int(absolute.group("m")),
                tzinfo=MOSCOW_TZ,
            )
    except ValueError:
        # «31 февраля», «25:00» и подобное.
        return None
    return None
