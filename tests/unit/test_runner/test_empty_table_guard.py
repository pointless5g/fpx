"""
Пустая таблица продаж/покупок в раннере.

Парсер отдаёт пустой список для продавца без продаж. Раннер принимает его, пока кеш пуст,
но не заменяет им непустой кеш: заказы из таблицы не пропадают, и после такой замены
следующая нормальная страница выдала бы все заказы за новые.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from fpx.classes.runner.subclasses._order import OrderRunner
from fpx.classes.runner.subclasses._purchase import PurchaseRunner
from fpx.utils import errors as fpx_err

CACHED = {
    "order_id": "A1",
    "order_time": "Сегодня, 12:00",
    "client_name": "Bob",
    "price": 100.0,
    "name": "Товар",
    "status": "Оплачен",
}


@pytest.fixture
def runner():
    r = MagicMock()
    r._cache = {"orders": [], "old_orders": [], "purchases": [], "old_purchases": []}
    return r


class TestOrderRunnerEmptyTable:
    @pytest.mark.asyncio
    async def test_empty_first_page_accepted_while_cache_is_empty(self, runner):
        runner._account._client.get_my_sells = AsyncMock(return_value="<html>")
        runner._account._parser.parse_my_sells = MagicMock(return_value={"sells": []})
        await OrderRunner(runner)._update_order_page_cache()
        assert runner._cache["orders"] == []

    @pytest.mark.asyncio
    async def test_empty_first_page_keeps_known_orders(self, runner):
        runner._cache["orders"] = [CACHED]
        runner._cache["old_orders"] = [CACHED]
        runner._account._client.get_my_sells = AsyncMock(return_value="<html>")
        runner._account._parser.parse_my_sells = MagicMock(return_value={"sells": []})
        with pytest.raises(fpx_err.FpxGetUserSellsError):
            await OrderRunner(runner)._update_order_page_cache()
        assert runner._cache["orders"] == [CACHED]
        assert runner._cache["old_orders"] == [CACHED]

    @pytest.mark.asyncio
    async def test_empty_sales_list_keeps_known_orders(self, runner):
        runner._cache["orders"] = [CACHED]
        runner._account.profile.get_my_sells = AsyncMock(return_value=[])
        with pytest.raises(fpx_err.FpxGetUserSellsError):
            await OrderRunner(runner)._update_order_cache()
        assert runner._cache["orders"] == [CACHED]


class TestPurchaseRunnerEmptyTable:
    @pytest.mark.asyncio
    async def test_empty_first_page_accepted_while_cache_is_empty(self, runner):
        runner._account._client.get_my_purchases = AsyncMock(return_value="<html>")
        runner._account._parser.parse_my_sells = MagicMock(return_value={"sells": []})
        await PurchaseRunner(runner)._update_purchase_page_cache()
        assert runner._cache["purchases"] == []

    @pytest.mark.asyncio
    async def test_empty_first_page_keeps_known_purchases(self, runner):
        runner._cache["purchases"] = [CACHED]
        runner._account._client.get_my_purchases = AsyncMock(return_value="<html>")
        runner._account._parser.parse_my_sells = MagicMock(return_value={"sells": []})
        with pytest.raises(fpx_err.FpxGetUserPurchasesError):
            await PurchaseRunner(runner)._update_purchase_page_cache()
        assert runner._cache["purchases"] == [CACHED]

    @pytest.mark.asyncio
    async def test_empty_purchases_list_keeps_known_purchases(self, runner):
        runner._cache["purchases"] = [CACHED]
        runner._account.purchase.get_my_purchases = AsyncMock(return_value=[])
        with pytest.raises(fpx_err.FpxGetUserPurchasesError):
            await PurchaseRunner(runner)._update_purchase_cache()
        assert runner._cache["purchases"] == [CACHED]
