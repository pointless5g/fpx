"""Типы оповещений FunPay: оплата, подтверждение, отзыв, возврат - по тексту оповещения."""

from __future__ import annotations

import re
from enum import Enum


class MessageType(str, Enum):
    """
    Что за сообщение в чате.

    Тип определяется только у оповещений FunPay (автор с ID 0): у покупателя, который
    напишет «Покупатель оплатил заказ #…», сообщение остаётся обычным.
    """

    NON_SYSTEM = "non_system"
    # Покупатель X оплатил заказ #Y. … X, не забудьте потом нажать кнопку «Подтвердить выполнение заказа».
    ORDER_PURCHASED = "order_purchased"
    # Покупатель X подтвердил успешное выполнение заказа #Y и отправил деньги продавцу Z.
    ORDER_CONFIRMED = "order_confirmed"
    # Администратор A подтвердил успешное выполнение заказа #Y и отправил деньги продавцу Z.
    ORDER_CONFIRMED_BY_ADMIN = "order_confirmed_by_admin"
    # Заказ #Y открыт повторно.
    ORDER_REOPENED = "order_reopened"
    # Продавец Z вернул деньги покупателю X по заказу #Y.
    REFUND = "refund"
    # Администратор A вернул деньги покупателю X по заказу #Y.
    REFUND_BY_ADMIN = "refund_by_admin"
    # Часть средств по заказу #Y возвращена покупателю.
    PARTIAL_REFUND = "partial_refund"
    NEW_FEEDBACK = "new_feedback"
    FEEDBACK_CHANGED = "feedback_changed"
    FEEDBACK_DELETED = "feedback_deleted"
    NEW_FEEDBACK_ANSWER = "new_feedback_answer"
    FEEDBACK_ANSWER_CHANGED = "feedback_answer_changed"
    FEEDBACK_ANSWER_DELETED = "feedback_answer_deleted"
    # Вы можете перейти в Discord. …
    DISCORD = "discord"
    # Уважаемые продавцы, не доверяйте сообщениям в чате! … (первое сообщение чата)
    DEAR_VENDORS = "dear_vendors"
    # Оповещение, которое fpx не знает.
    UNKNOWN_SYSTEM = "unknown_system"


# Ник на FunPay - одно слово. Текст сравнивается после схлопывания пробелов и переносов:
# в разметке оповещения ник и номер заказа - ссылки, между ними бывают переносы строк.
_NICK = r"\S+"
_ORDER = r"#[A-Z0-9]{8}"

_PURCHASED = re.compile(rf"(Покупатель|The buyer) {_NICK} (оплатил заказ|has paid for order) {_ORDER}\.")
_PURCHASED_REMINDER = re.compile(
    rf"{_NICK}, (не забудьте потом нажать кнопку («Подтвердить выполнение заказа»|«Подтвердить получение валюты»)\."
    r"|do not forget to press the («Confirm order fulfilment»|«Confirm currency receipt») button once you finish\.)"
)
_CONFIRMED_TAIL = (
    rf"(подтвердил успешное выполнение заказа|has confirmed that order) {_ORDER} "
    rf"(и отправил деньги продавцу|has been fulfilled successfully and that the seller) {_NICK}( has been paid)?\."
)
_REFUND_TAIL = rf"(вернул деньги покупателю|has refunded the buyer) {_NICK} (по заказу|on order) {_ORDER}\."

# В порядке от самых частых к самым редким, как у FunPayCardinal.
_BY_ORDER: tuple[tuple[MessageType, re.Pattern[str]], ...] = (
    (MessageType.ORDER_CONFIRMED, re.compile(rf"(Покупатель|The buyer) {_NICK} {_CONFIRMED_TAIL}")),
    (
        MessageType.NEW_FEEDBACK,
        re.compile(
            rf"(Покупатель|The buyer) {_NICK} "
            rf"(написал отзыв к заказу|has given feedback to the order) {_ORDER}\."
        ),
    ),
    (
        MessageType.NEW_FEEDBACK_ANSWER,
        re.compile(
            rf"(Продавец|The seller) {_NICK} "
            rf"(ответил на отзыв к заказу|has replied to their feedback to the order) {_ORDER}\."
        ),
    ),
    (
        MessageType.FEEDBACK_CHANGED,
        re.compile(
            rf"(Покупатель|The buyer) {_NICK} "
            rf"(изменил отзыв к заказу|has edited their feedback to the order) {_ORDER}\."
        ),
    ),
    (
        MessageType.FEEDBACK_DELETED,
        re.compile(
            rf"(Покупатель|The buyer) {_NICK} "
            rf"(удалил отзыв к заказу|has deleted their feedback to the order) {_ORDER}\."
        ),
    ),
    (MessageType.REFUND, re.compile(rf"(Продавец|The seller) {_NICK} {_REFUND_TAIL}")),
    (
        MessageType.FEEDBACK_ANSWER_CHANGED,
        re.compile(
            rf"(Продавец|The seller) {_NICK} "
            rf"(изменил ответ на отзыв к заказу|has edited a reply to their feedback to the order) {_ORDER}\."
        ),
    ),
    (
        MessageType.FEEDBACK_ANSWER_DELETED,
        re.compile(
            rf"(Продавец|The seller) {_NICK} "
            rf"(удалил ответ на отзыв к заказу|has deleted a reply to their feedback to the order) {_ORDER}\."
        ),
    ),
    (MessageType.ORDER_CONFIRMED_BY_ADMIN, re.compile(rf"(Администратор|The administrator) {_NICK} {_CONFIRMED_TAIL}")),
    (
        MessageType.PARTIAL_REFUND,
        re.compile(
            rf"(Часть средств по заказу|A part of the funds pertaining to the order) {_ORDER} "
            r"(возвращена покупателю|has been refunded)\."
        ),
    ),
    (MessageType.ORDER_REOPENED, re.compile(rf"(Заказ|Order) {_ORDER} (открыт повторно|has been reopened)\.")),
    (MessageType.REFUND_BY_ADMIN, re.compile(rf"(Администратор|The administrator) {_NICK} {_REFUND_TAIL}")),
)

_DISCORD = re.compile(
    r"(You can switch to|Вы можете перейти в) Discord\. "
    r"(However, note that friending someone is considered a violation rules"
    r"|Внимание: общение за пределами сервера FunPay считается нарушением правил)\."
)
_DEAR_VENDORS = re.compile(
    r"(Уважаемые продавцы|Dear vendors), (не доверяйте сообщениям в чате|do not rely on chat messages)! "
    r"(Перед выполнением заказа всегда проверяйте наличие оплаты в разделе «Мои продажи»"
    r"|Before you process an order, you should always check whether you've been paid in «My sales» section)\."
)
_ORDER_ID = re.compile(r"#([A-Z0-9]{8})")


def classify_notice(text: str | None) -> tuple[MessageType, str | None]:
    """
    Тип оповещения FunPay и номер заказа, о котором оно.

    Вызывать только для сообщений автора 0: сверка идёт по тексту, и покупатель
    может написать то же самое.

    Returns:
        tuple: тип и номер заказа без «#» (None, если номера в тексте нет).
    """
    flat = " ".join((text or "").split())
    found = _ORDER_ID.search(flat)
    order_id = found.group(1) if found else None
    if not flat:
        return MessageType.UNKNOWN_SYSTEM, None
    if _DISCORD.search(flat):
        return MessageType.DISCORD, None
    if _DEAR_VENDORS.search(flat):
        return MessageType.DEAR_VENDORS, None
    if _PURCHASED.search(flat) and _PURCHASED_REMINDER.search(flat):
        return MessageType.ORDER_PURCHASED, order_id
    if order_id is None:
        return MessageType.UNKNOWN_SYSTEM, None
    for message_type, pattern in _BY_ORDER:
        if pattern.search(flat):
            return message_type, order_id
    return MessageType.UNKNOWN_SYSTEM, order_id


__all__ = ["MessageType", "classify_notice"]
