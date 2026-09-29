"""
Тесты новых полей get_my_sells / get_my_purchases на настоящем парсере.

Страницы: первая — полная (фильтр игр, userId в data-app-data, курсор), вторая и третья —
ответы на ``continue`` без фильтра. Строки последней страницы здесь не проверяются:
их попадание в результат — отдельная правка пагинации.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from fpx._parsers import FpxParser
from fpx.classes.account.subclasses.profile import ProfileManager
from fpx.classes.account.subclasses.purchase import PurchaseManager
from fpx.models.account import Order, Purchase
from fpx.utils.currency import Currency
from fpx.utils.order_status import OrderStatusKind

MY_ID = 2268991


def row(
    order_id: str, row_class: str, user_id: int, subcategory: str, price: str, date: str, status: str = "Оплачен"
) -> str:
    return (
        f'<a href="https://funpay.com/orders/{order_id}/" class="tc-item {row_class}">'
        f'<div class="tc-date"><div class="tc-date-time">{date}</div></div>'
        f'<div class="tc-order">#{order_id}</div>'
        f'<div class="order-desc"><div>Robux, 1 000 шт.</div><div class="text-muted">{subcategory}</div></div>'
        '<div class="tc-user"><div class="media-user-name">'
        f'<span class="pseudo-a" data-href="https://funpay.com/users/{user_id}/">user{user_id}</span></div></div>'
        f'<div class="tc-status">{status}</div><div class="tc-price">{price}</div></a>'
    )


def first_page(rows: str, title: str, cursor: str) -> str:
    return (
        f'<html><body data-app-data=\'{{"locale":"ru","userId":{MY_ID}}}\'>'
        f'<h1 class="page-header page-header-no-hr">{title}</h1>'
        '<select name="game"><option value="">Все</option>'
        """<option value="41" data-data='[["lot-1235","Донат робуксов (паки)"],["chip-99","Робуксы"]]'>"""
        "Roblox</option>"
        f'</select>{rows}<form class="dyn-table-form"><input type="hidden" name="continue" value="{cursor}"></form>'
        "</body></html>"
    )


def fragment(rows: str, cursor: str | None) -> str:
    form = f'<form class="dyn-table-form"><input type="hidden" name="continue" value="{cursor}"></form>'
    return rows + (form if cursor else "")


PAGE_1 = first_page(
    row(
        "PAGE1AAA",
        "info",
        4747678,
        "Roblox, Донат робуксов (паки)",
        '86.81 <span class="unit">₽</span>',
        "сегодня, 1:41",
    )
    + row(
        "PAGE1BBB", "warning", 100, "Roblox, Робуксы", '2 <span class="unit">$</span>', "12 сентября, 12:00", "Возврат"
    ),
    "Мои продажи",
    "CURSOR-2",
)
PAGE_2 = fragment(
    row("PAGE2CCC", "", 30000000, "Roblox, Робуксы", '5 <span class="unit">€</span>', "5 января 2025, 9:30", "Закрыт"),
    "CURSOR-3",
)
PAGE_3 = fragment(row("PAGE3DDD", "info", 7, "Roblox, Робуксы", "1 ₽", "вчера, 10:00"), None)


def make_account(user_id=None):
    acc = MagicMock()
    acc.data.user_id = user_id
    acc._parser = FpxParser()
    acc._client.get_my_sells = AsyncMock(return_value=PAGE_1)
    acc._client.get_next_sells = AsyncMock(side_effect=[PAGE_2, PAGE_3])
    acc._client.get_my_purchases = AsyncMock(return_value=PAGE_1.replace("Мои продажи", "Мои покупки"))
    acc._client.get_next_purchases = AsyncMock(side_effect=[PAGE_2, PAGE_3])
    return acc


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock())


class TestGetMySellsFields:
    @pytest.mark.asyncio
    async def test_rows_carry_new_fields(self):
        account = make_account()
        orders = {order.order_id: order for order in await ProfileManager(account).get_my_sells()}
        assert {"PAGE1AAA", "PAGE1BBB", "PAGE2CCC"} <= set(orders)
        assert all(isinstance(order, Order) for order in orders.values())

        paid = orders["PAGE1AAA"]
        assert paid.buyer_id == 4747678
        assert paid.currency is Currency.RUB
        assert (paid.subcategory_type, paid.subcategory_id) == ("lot", 1235)
        assert paid.status_kind is OrderStatusKind.PAID
        assert paid.status == "Оплачен"
        assert paid.amount == 1000
        assert (paid.created_at.hour, paid.created_at.minute) == (1, 41)
        assert paid.chat_name == f"users-{MY_ID}-4747678"

        refunded = orders["PAGE1BBB"]
        assert refunded.status_kind is OrderStatusKind.REFUNDED
        assert refunded.currency is Currency.USD
        assert refunded.chat_name == f"users-100-{MY_ID}"

    @pytest.mark.asyncio
    async def test_continue_page_gets_subcategory_from_first_page(self):
        account = make_account()
        orders = {order.order_id: order for order in await ProfileManager(account).get_my_sells()}
        second = orders["PAGE2CCC"]
        assert (second.subcategory_type, second.subcategory_id) == ("chip", 99)
        assert second.currency is Currency.EUR
        assert second.status_kind is OrderStatusKind.CLOSED
        assert second.created_at.year == 2025
        assert second.chat_name == f"users-{MY_ID}-30000000"
        assert account._client.get_next_sells.await_args_list[0].args == ("CURSOR-2",)

    @pytest.mark.asyncio
    async def test_own_id_is_learned_from_page(self):
        account = make_account(user_id=None)
        await ProfileManager(account).get_my_sells()
        assert account.data.user_id == str(MY_ID)

    @pytest.mark.asyncio
    async def test_known_own_id_wins(self):
        account = make_account(user_id="5")
        orders = {order.order_id: order for order in await ProfileManager(account).get_my_sells()}
        assert account.data.user_id == "5"
        assert orders["PAGE1AAA"].chat_name == "users-5-4747678"


class TestGetMyPurchasesFields:
    @pytest.mark.asyncio
    async def test_rows_carry_new_fields(self):
        account = make_account()
        purchases = {p.order_id: p for p in await PurchaseManager(account).get_my_purchases()}
        assert {"PAGE1AAA", "PAGE1BBB", "PAGE2CCC"} <= set(purchases)
        purchase = purchases["PAGE1AAA"]
        assert isinstance(purchase, Purchase)
        assert purchase.seller_id == 4747678
        assert purchase.chat_name == f"users-{MY_ID}-4747678"
        assert purchase.status_kind is OrderStatusKind.PAID
        assert purchase.currency is Currency.RUB
        assert purchases["PAGE2CCC"].subcategory_id == 99
