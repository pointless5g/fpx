"""Тесты PurchaseManager — детали покупки, список покупок.

PurchaseManager — братский класс OrderManager (см. test_order_manager.py):
`get_purchase_details` под капотом переиспользует `OrderManager.get_order_details`
на том же `account`, а `get_my_purchases` пагинируется точно так же, как
`ProfileManager.get_my_sells` (см. test_profile_manager.py::TestGetMySells).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from fpx.classes.account.subclasses.purchase import PurchaseManager
from fpx.models.account import Purchase
from fpx.utils import errors as fpx_err


@pytest.fixture
def account():
    acc = MagicMock()
    acc._client.get_order_info = AsyncMock()
    acc._client.get_my_purchases = AsyncMock()
    acc._client.get_next_purchases = AsyncMock()
    acc._parser.parse_order_page = MagicMock()
    acc._parser.parse_my_sells = MagicMock()
    return acc


@pytest.fixture
def manager(account):
    return PurchaseManager(account)


class TestGetPurchaseDetails:
    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        account._client.get_order_info.return_value = "<html></html>"
        account._parser.parse_order_page.return_value = {
            "status": "Оплачен",
            "review": {"text": "", "stars": 0, "answer": ""},
            "desc": "Описание",
            "chat_id": "chat-1",
        }
        result = await manager.get_purchase_details("order-1")
        assert isinstance(result, Purchase)
        assert result.status == "Оплачен"
        assert result.chat_id == "chat-1"
        assert result.description == "Описание"

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account._client.get_order_info.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxGetPurchaseInfoError):
            await manager.get_purchase_details("order-1")


class TestGetMyPurchases:
    @pytest.mark.asyncio
    async def test_single_page_without_next_page_marker_returns_its_purchases(self, manager, account):
        """Как и в ProfileManager.get_my_sells: единственная страница без 'next_page' попадает в результат."""
        account._client.get_my_purchases.return_value = "<html></html>"
        account._parser.parse_my_sells.return_value = {
            "sells": [
                {
                    "order-id": "1",
                    "order-time": "10:00",
                    "client-name": "Продавец",
                    "price": 10.0,
                    "status": "Оплачен",
                    "name": "Товар",
                    "category": "Cat",
                    "amount": 1,
                    "topup_data": None,
                }
            ]
        }
        result = await manager.get_my_purchases()
        assert [order.order_id for order in result] == ["1"]
        account._client.get_next_purchases.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multiple_pages_include_last_page(self, manager, account, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        account._client.get_my_purchases.return_value = "<html></html>"
        page1 = {
            "sells": [
                {
                    "order-id": "1",
                    "order-time": "t",
                    "client-name": "Продавец",
                    "price": 1.0,
                    "status": "s",
                    "name": "A",
                    "category": "c",
                    "amount": 1,
                    "topup_data": None,
                }
            ],
            "next_page": "page-2",
        }
        page2 = {
            "sells": [
                {
                    "order-id": "2",
                    "order-time": "t",
                    "client-name": "Продавец",
                    "price": 2.0,
                    "status": "s",
                    "name": "B",
                    "category": "c",
                    "amount": 1,
                    "topup_data": None,
                }
            ]
        }
        account._parser.parse_my_sells.side_effect = [page1, page2]
        result = await manager.get_my_purchases()
        assert [order.order_id for order in result] == ["1", "2"]
        assert all(isinstance(order, Purchase) for order in result)
        account._client.get_next_purchases.assert_awaited_once_with("page-2")

    @pytest.mark.asyncio
    async def test_limit_stops_pagination(self, manager, account, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        account._client.get_my_purchases.return_value = "<html></html>"
        sells = [
            {
                "order-id": str(i),
                "order-time": "t",
                "client-name": "Продавец",
                "price": 1.0,
                "status": "s",
                "name": "A",
                "category": "c",
                "amount": 1,
                "topup_data": None,
            }
            for i in range(5)
        ]
        account._parser.parse_my_sells.return_value = {"sells": sells, "next_page": "p2"}
        result = await manager.get_my_purchases(limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account._client.get_my_purchases.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxGetUserPurchasesError):
            await manager.get_my_purchases()
