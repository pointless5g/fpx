from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Union, cast

from fpx.models.lots import LotInfo
from fpx.utils import errors as fpx_err
from fpx.utils.currency import Currency
from fpx.utils.formatting import safe_format
from fpx.utils.order_status import OrderStatusKind


@dataclass
class Balance:
    rub: float = 0.0
    usd: float = 0.0
    eur: float = 0.0


@dataclass
class Calc:
    type_name: str
    price: str
    unit: str
    pos: str


@dataclass
class CurReview:
    text: str
    stars: int
    author: str
    order_id: str
    order: Optional[Order] = None
    _client: Any = field(init=False, repr=False, default=None)

    async def answer(self, answer_text: str) -> bool:
        """Ответить на отзыв"""
        if not self._client:
            raise fpx_err.FpxClientNotAttachedError("Объект CurReview не привязан к клиенту fpx")
        if not self.order:
            raise fpx_err.FpxAttributeError("В объект не передан аттрибут Order")
        formatted_reply = safe_format(
            answer_text,
            author=self.author,
            order_id=self.order_id,
            order_name=self.order.name,
            order_time=self.order.order_time,
            stars=self.stars,
        )
        return cast(bool, await self._client._account.review.review_answer(self.order_id, formatted_reply))

    async def message_author(self, message_text: str) -> bool:
        """Ответить на отзыв в чате"""
        if not self._client:
            raise fpx_err.FpxClientNotAttachedError("Объект CurReview не привязан к клиенту fpx")
        if not self.order:
            raise fpx_err.FpxAttributeError("В объект не передан аттрибут Order")
        formatted_reply = safe_format(
            message_text,
            author=self.author,
            order_id=self.order_id,
            order_name=self.order.name,
            order_time=self.order.order_time,
            stars=self.stars,
        )
        return cast(bool, await self._client._account.chat.send_message(self.order.chat_id, formatted_reply))

    async def delete(self) -> bool:
        """Удалить отзыв или ответ на отзыв"""
        if not self._client:
            raise fpx_err.FpxClientNotAttachedError("Объект CurReview не привязан к клиенту fpx")
        return cast(bool, await self._client._account.review.delete_review(self.order_id))


@dataclass
class Transaction:
    """Одна операция из истории баланса FunPay."""

    transaction_id: str
    type: str
    amount: float
    date: str
    description: str = ""
    status: str = "unknown"
    currency: str = ""
    payment_method: Optional[str] = None
    withdrawal_number: Optional[str] = None


@dataclass
class TransactionsPage:
    """Одна пачка истории транзакций и курсор пагинации."""

    transactions: list[Transaction] = field(default_factory=list)
    next_transaction_id: Optional[str] = None
    user_id: Optional[str] = None
    filter: Optional[str] = None


@dataclass
class Profile:
    category_ids: list[str]
    lots: list[LotInfo] = field(default_factory=list)
    reviews: list[CurReview] = field(default_factory=list)


@dataclass
class UserData:
    csrf_token: str
    user_id: str


@dataclass
class Order:
    order_id: Optional[str] = None
    chat_id: Optional[str] = None
    order_time: Optional[str] = None
    description: Optional[str] = None
    client_name: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[int] = None
    topup_data: Optional[str] = None
    finded_mapping: Optional[str] = None
    status: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    review: Optional[dict[str, Any]] = None
    # Поля ниже заполняет таблица продаж /orders/trade (ProfileManager.get_my_sells).
    buyer_id: Optional[int] = None
    """ID покупателя (из ссылки на его профиль)."""
    currency: Optional[Currency] = None
    """Валюта цены."""
    subcategory_id: Optional[int] = None
    """ID подкатегории FunPay (``/lots/<id>/`` или ``/chips/<id>/``)."""
    subcategory_type: Optional[str] = None
    """Тип подкатегории: ``lot`` (обычные лоты) или ``chip`` (игровая валюта)."""
    created_at: Optional[datetime] = None
    """Дата заказа по Москве (``order_time`` — тот же момент текстом FunPay)."""
    status_kind: Optional[OrderStatusKind] = None
    """Статус, не зависящий от языка аккаунта (``status`` — подпись FunPay)."""
    chat_name: Optional[str] = None
    """Имя личного чата с покупателем ``users-<ID>-<ID>``."""
    _client: Any = field(init=False, repr=False, default=None)

    async def answer(self, answer_text: str) -> bool:
        """Ответить в этот же чат"""
        if not self._client:
            raise fpx_err.FpxClientNotAttachedError("Объект Order не привязан к клиенту fpx")
        formatted_reply = safe_format(
            answer_text,
            order_id=self.order_id,
            order_time=self.order_time,
            client_name=self.client_name,
            order_name=self.name,
        )
        return cast(bool, await self._client._account.chat.send_message(self.chat_id, formatted_reply))

    async def refund(self) -> bool:
        """Вернуть заказ"""
        if not self._client:
            raise fpx_err.FpxClientNotAttachedError("Объект Order не привязан к клиенту fpx")
        return cast(bool, await self._client._account.order.refund_order(self.order_id))


@dataclass
class Purchase:
    order_id: Optional[str] = None
    chat_id: Optional[str] = None
    order_time: Optional[str] = None
    description: Optional[str] = None
    client_name: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[int] = None
    topup_data: Optional[str] = None
    finded_mapping: Optional[str] = None
    status: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    review: Optional[dict[str, Any]] = None
    # Поля ниже заполняет таблица покупок /orders/ (PurchaseManager.get_my_purchases).
    seller_id: Optional[int] = None
    """ID продавца (из ссылки на его профиль)."""
    currency: Optional[Currency] = None
    """Валюта цены."""
    subcategory_id: Optional[int] = None
    """ID подкатегории FunPay (``/lots/<id>/`` или ``/chips/<id>/``)."""
    subcategory_type: Optional[str] = None
    """Тип подкатегории: ``lot`` (обычные лоты) или ``chip`` (игровая валюта)."""
    created_at: Optional[datetime] = None
    """Дата покупки по Москве (``order_time`` — тот же момент текстом FunPay)."""
    status_kind: Optional[OrderStatusKind] = None
    """Статус, не зависящий от языка аккаунта (``status`` — подпись FunPay)."""
    chat_name: Optional[str] = None
    """Имя личного чата с продавцом ``users-<ID>-<ID>``."""
    _client: Any = field(init=False, repr=False, default=None)

    async def answer(self, answer_text: str) -> bool:
        """Ответить в этот же чат"""
        if not self._client:
            raise fpx_err.FpxClientNotAttachedError("Объект Purchase не привязан к клиенту fpx")
        formatted_reply = safe_format(
            answer_text,
            order_id=self.order_id,
            order_time=self.order_time,
            client_name=self.client_name,
            order_name=self.name,
        )
        return cast(bool, await self._client._account.chat.send_message(self.chat_id, formatted_reply))


@dataclass
class OrderServer:
    """Сервер, выбранный в заказе."""

    id: int
    name: Optional[str] = None


@dataclass
class OrderSide:
    """Сторона (платформа), выбранная в заказе."""

    id: int
    name: Optional[str] = None


@dataclass
class OrderField:
    """Поле оплаченного лота из JSON API заказа.

    ``value`` — строка или словарь по локалям (``{"ru": "...", "en": "..."}``).
    """

    id: str
    value: Union[str, dict[str, Any], None]
    name: Optional[str] = None
    field_type_id: Optional[str] = None


@dataclass
class OrderReview:
    """Отзыв к заказу из JSON API заказа."""

    stars: Optional[int] = None
    text: Optional[str] = None
    reply: Optional[str] = None
    hidden: bool = False


# Служебные поля лота: у них свои свойства, в параметры лота они не входят.
_SERVICE_FIELD_KEYS = ("payment_msg", "desc", "summary")


@dataclass
class OrderInfo:
    """Заказ из JSON API FunPay (``POST /api/orders/get``), см. ``OrderManager.get_order``.

    Имена полей повторяют ``FunPayAPI.types.Order``: ``sum`` — сумма заказа,
    ``amount`` — количество товара.
    """

    order_id: str
    status: OrderStatusKind
    buyer_id: int
    seller_id: int
    chat_name: str
    """Имя личного чата покупателя и продавца ``users-<ID>-<ID>``."""
    sum: float
    """Сумма заказа."""
    currency: Currency
    subcategory_id: Optional[int] = None
    subcategory_type: Optional[str] = None
    """``lot`` (обычные лоты) или ``chip`` (игровая валюта)."""
    subcategory_name: Optional[str] = None
    """Название подкатегории, если FunPay прислал его в ``section``."""
    buyer_username: Optional[str] = None
    seller_username: Optional[str] = None
    amount: Union[int, float, None] = None
    """Количество товара (``type_data.amount``)."""
    player: Optional[str] = None
    server: Optional[OrderServer] = None
    side: Optional[OrderSide] = None
    fields: dict[str, OrderField] = field(default_factory=dict)
    order_secrets: list[str] = field(default_factory=list)
    """Товары автовыдачи FunPay."""
    review: Optional[OrderReview] = None
    locale: str = "ru"
    """Язык значений полей по умолчанию: ``ru`` или ``en``."""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """Исходный объект заказа из ответа FunPay."""

    def get_field(self, key: str) -> Optional[OrderField]:
        """Поле лота по ключу."""
        return self.fields.get(key)

    def get_field_value(self, key: str, locale: str = "ru") -> Optional[str]:
        """Значение поля лота на нужном языке."""
        order_field = self.get_field(key)
        if order_field is None:
            return None
        if isinstance(order_field.value, dict):
            value = order_field.value.get(locale)
            return None if value is None else str(value)
        return order_field.value

    def get_field_value_any(self, key: str) -> Optional[str]:
        """Значение поля лота: сначала на языке заказа, затем на остальных."""
        locales = [self.locale] + [loc for loc in ("ru", "en") if loc != self.locale]
        for locale in locales:
            value = self.get_field_value(key, locale)
            if value:
                return value
        return None

    @property
    def short_description(self) -> Optional[str]:
        """Краткое описание лота."""
        return self.get_field_value_any("summary")

    @property
    def title(self) -> Optional[str]:
        """То же, что ``short_description``."""
        return self.short_description

    @property
    def full_description(self) -> Optional[str]:
        """Подробное описание лота."""
        return self.get_field_value_any("desc")

    @property
    def payment_msg(self) -> Optional[str]:
        """Сообщение покупателю после оплаты."""
        return self.get_field_value_any("payment_msg")

    @property
    def character_name(self) -> Optional[str]:
        """Имя персонажа, то же, что ``player``."""
        return self.player

    @property
    def lot_params(self) -> list[tuple[Optional[str], Optional[str]]]:
        """Параметры лота парами (название поля, значение), без служебных полей."""
        return [
            (order_field.name, self.get_field_value_any(key))
            for key, order_field in self.fields.items()
            if key not in _SERVICE_FIELD_KEYS
        ]

    @property
    def lot_params_text(self) -> Optional[str]:
        """Параметры лота одной строкой: ``1000 Робуксов, Roblox``."""
        result: Optional[str] = None
        for key, order_field in self.fields.items():
            if key in _SERVICE_FIELD_KEYS:
                continue
            value = self.get_field_value_any(key)
            if not value:
                continue
            part = f"{value} {order_field.name}" if str(value).isdigit() else value
            result = f"{result}, {part}" if result else part
        return result

    @property
    def lot_params_dict(self) -> dict[Optional[str], Optional[str]]:
        """Параметры лота словарём по названию поля (одинаковые названия перезаписываются)."""
        return {
            order_field.name: self.get_field_value_any(key)
            for key, order_field in self.fields.items()
            if key not in _SERVICE_FIELD_KEYS
        }


@dataclass
class Review:
    text: str
    stars: int
    answer: str


@dataclass
class GameTitle:
    id: int
    name: str


@dataclass
class GameSubCategory:
    id: int
    sub_name: str


@dataclass
class Game:
    title: GameTitle
    subcategories: list[GameSubCategory] = field(default_factory=list)
