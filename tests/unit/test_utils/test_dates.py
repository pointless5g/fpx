"""Тесты parse_funpay_datetime — даты со страниц FunPay по Москве."""

from datetime import datetime, timedelta, timezone

import pytest

from fpx.utils.dates import MOSCOW_TZ, parse_funpay_datetime

# 1 сентября 2026, 00:30 по Москве: «вчера» — уже август.
NOW = datetime(2026, 9, 1, 0, 30, tzinfo=MOSCOW_TZ)


def msk(*args: int) -> datetime:
    return datetime(*args, tzinfo=MOSCOW_TZ)


class TestParseFunpayDatetime:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("сегодня, 1:41", msk(2026, 9, 1, 1, 41)),
            ("Сегодня, 12:00", msk(2026, 9, 1, 12, 0)),
            ("сьогодні, 08:05", msk(2026, 9, 1, 8, 5)),
            ("Today, 23:59", msk(2026, 9, 1, 23, 59)),
            ("вчера, 23:10", msk(2026, 8, 31, 23, 10)),
            ("Вчора, 0:00", msk(2026, 8, 31, 0, 0)),
            ("yesterday, 7:07", msk(2026, 8, 31, 7, 7)),
            ("12 сентября, 12:00", msk(2026, 9, 12, 12, 0)),
            ("1 мая, 9:30", msk(2026, 5, 1, 9, 30)),
            ("5 января 2025, 9:30", msk(2025, 1, 5, 9, 30)),
            ("31 грудня 2024, 23:45", msk(2024, 12, 31, 23, 45)),
            ("3 September, 10:00", msk(2026, 9, 3, 10, 0)),
            ("  12 сентября,  12:00 ", msk(2026, 9, 12, 12, 0)),
        ],
    )
    def test_forms(self, text, expected):
        parsed = parse_funpay_datetime(text, now=NOW)
        assert parsed == expected
        assert parsed.utcoffset() == timedelta(hours=3)

    def test_now_in_other_timezone_is_converted_to_moscow(self):
        """22:30 UTC 31 августа — это уже 1 сентября в Москве."""
        now_utc = datetime(2026, 8, 31, 22, 30, tzinfo=timezone.utc)
        assert parse_funpay_datetime("сегодня, 1:41", now=now_utc) == msk(2026, 9, 1, 1, 41)

    def test_default_now_is_moscow_today(self):
        parsed = parse_funpay_datetime("сегодня, 0:00")
        assert parsed is not None
        assert parsed.date() == datetime.now(MOSCOW_TZ).date()

    @pytest.mark.parametrize(
        "text",
        [None, "", "   ", "12:00", "завтра, 12:00", "31 февраля, 12:00", "12 брюмера, 12:00", "сегодня, 25:00", "abc"],
    )
    def test_unrecognized_is_none(self, text):
        assert parse_funpay_datetime(text, now=NOW) is None
