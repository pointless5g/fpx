"""Валюта заказа FunPay: символ со страницы или код из JSON API → нормализованное значение."""

from __future__ import annotations

from enum import Enum


class Currency(str, Enum):
    """Валюта заказа. Значение — код ISO 4217, так что ``Currency.RUB == "RUB"``."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    UNKNOWN = "UNKNOWN"

    @property
    def symbol(self) -> str:
        """Знак валюты, как его рисует FunPay (``¤`` для неизвестной)."""
        return _SYMBOLS.get(self, "¤")


_SYMBOLS = {Currency.RUB: "₽", Currency.USD: "$", Currency.EUR: "€"}

# Как CURRENCY_MAP в FunPayAPI: страницы отдают знак, JSON API — код.
# «¤» FunPay показывает у рублёвых сумм без явной валюты, FunPayAPI считает его рублём.
_CURRENCY_MAP = {
    "RUB": Currency.RUB,
    "EUR": Currency.EUR,
    "USD": Currency.USD,
    "₽": Currency.RUB,
    "€": Currency.EUR,
    "$": Currency.USD,
    "¤": Currency.RUB,
}


def parse_currency(value: str | None) -> Currency | None:
    """Знак (``₽``) или код (``RUB``/``rub``) → :class:`Currency`.

    Returns:
        ``None`` для пустого значения, ``Currency.UNKNOWN`` для незнакомого.
    """
    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    return _CURRENCY_MAP.get(token) or _CURRENCY_MAP.get(token.upper()) or Currency.UNKNOWN
