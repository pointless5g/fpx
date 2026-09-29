"""Тесты parse_currency и private_chat_name."""

import pytest

from fpx.utils.currency import Currency, parse_currency
from fpx.utils.formatting import private_chat_name


class TestParseCurrency:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("₽", Currency.RUB),
            ("$", Currency.USD),
            ("€", Currency.EUR),
            ("¤", Currency.RUB),
            ("RUB", Currency.RUB),
            ("usd", Currency.USD),
            (" EUR ", Currency.EUR),
            ("₿", Currency.UNKNOWN),
            ("", None),
            (None, None),
        ],
    )
    def test_symbols_and_codes(self, raw, expected):
        assert parse_currency(raw) == expected

    def test_value_is_iso_code_and_symbol_is_available(self):
        assert Currency.RUB == "RUB"
        assert Currency.USD.symbol == "$"
        assert Currency.UNKNOWN.symbol == "¤"


class TestPrivateChatName:
    def test_sorted_numerically(self):
        assert private_chat_name("19903068", 8778502) == "users-8778502-19903068"
        assert private_chat_name(8778502, "19903068") == "users-8778502-19903068"

    @pytest.mark.parametrize(("first", "second"), [(None, 1), (1, None), ("abc", 1), (True, 1), ("", 1)])
    def test_unknown_id_gives_none(self, first, second):
        assert private_chat_name(first, second) is None
