"""Тесты OrderManager.get_order / get_orders — заказ через JSON API FunPay."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from fpx._parsers import FpxParser
from fpx.classes.account.subclasses.order import OrderManager
from fpx.models.account import OrderInfo
from fpx.utils import errors as fpx_err
from fpx.utils.order_status import OrderStatusKind

API_ORDER = {
    "order_uid": "SW4J186Q",
    "status": "closed",
    "currency": "RUB",
    "amount": 86.81,
    "section": {"type_id": "lot", "local_id": 1235},
    "buyer": {"user_id": 4747678, "name": "meowchik228"},
    "seller": {"user_id": 2268991, "name": "femtorr"},
    "chat": {"node_name": "users-2268991-4747678"},
    "review": {"text": "", "rating": 0, "reply": "", "hidden": False},
    "type_data": {"amount": 1, "fields": {}, "secrets": []},
}


def api_response(body, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    if isinstance(body, Exception):
        response.json = MagicMock(side_effect=body)
    else:
        response.json = MagicMock(return_value=body)
    return response


@pytest.fixture
def account():
    acc = MagicMock()
    acc._client.get_orders_api = AsyncMock()
    acc._parser = FpxParser()
    return acc


@pytest.fixture
def manager(account):
    return OrderManager(account)


class TestGetOrder:
    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        account._client.get_orders_api.return_value = api_response(
            {"status": "SUCCESS", "data": {"SW4J186Q": API_ORDER}}
        )
        info = await manager.get_order("#SW4J186Q")
        assert isinstance(info, OrderInfo)
        assert info.order_id == "SW4J186Q"
        assert info.status is OrderStatusKind.CLOSED
        assert info.buyer_id == 4747678
        assert info.chat_name == "users-2268991-4747678"
        account._client.get_orders_api.assert_awaited_once_with(["SW4J186Q"], locale=None)

    @pytest.mark.asyncio
    async def test_locale_is_passed_through(self, manager, account):
        account._client.get_orders_api.return_value = api_response(
            {"status": "SUCCESS", "data": {"SW4J186Q": API_ORDER}}
        )
        info = await manager.get_order("SW4J186Q", locale="en")
        assert info.locale == "en"
        account._client.get_orders_api.assert_awaited_once_with(["SW4J186Q"], locale="en")

    @pytest.mark.asyncio
    async def test_order_found_by_its_uid_under_another_key(self, manager, account):
        account._client.get_orders_api.return_value = api_response({"status": "SUCCESS", "data": {"0": API_ORDER}})
        info = await manager.get_order("SW4J186Q")
        assert info.order_id == "SW4J186Q"

    @pytest.mark.asyncio
    async def test_order_missing_in_response(self, manager, account):
        account._client.get_orders_api.return_value = api_response({"status": "SUCCESS", "data": []})
        with pytest.raises(fpx_err.FpxGetOrderInfoError, match="SW4J186Q"):
            await manager.get_order("SW4J186Q")

    @pytest.mark.asyncio
    async def test_error_json_is_wrapped_with_cause(self, manager, account):
        account._client.get_orders_api.return_value = api_response({"status": "ERROR", "message": "Forbidden order"})
        with pytest.raises(fpx_err.FpxGetOrderInfoError) as exc:
            await manager.get_order("SW4J186Q")
        assert isinstance(exc.value.__cause__, fpx_err.FpxParseError)
        assert "Forbidden order" in str(exc.value)

    @pytest.mark.asyncio
    async def test_403_is_auth_error_cause(self, manager, account):
        account._client.get_orders_api.return_value = api_response({}, status_code=403)
        with pytest.raises(fpx_err.FpxGetOrderInfoError) as exc:
            await manager.get_order("SW4J186Q")
        assert isinstance(exc.value.__cause__, fpx_err.FpxAuthError)

    @pytest.mark.asyncio
    async def test_non_200_is_request_error_cause(self, manager, account):
        account._client.get_orders_api.return_value = api_response({}, status_code=500)
        with pytest.raises(fpx_err.FpxGetOrderInfoError) as exc:
            await manager.get_order("SW4J186Q")
        assert isinstance(exc.value.__cause__, fpx_err.FpxRequestError)
        assert "500" in str(exc.value)

    @pytest.mark.asyncio
    async def test_non_json_body(self, manager, account):
        account._client.get_orders_api.return_value = api_response(json.JSONDecodeError("Expecting value", "<", 0))
        with pytest.raises(fpx_err.FpxGetOrderInfoError) as exc:
            await manager.get_order("SW4J186Q")
        assert isinstance(exc.value.__cause__, ValueError)

    @pytest.mark.asyncio
    async def test_transport_failure(self, manager, account):
        account._client.get_orders_api.side_effect = fpx_err.FpxRequestError("timeout")
        with pytest.raises(fpx_err.FpxGetOrderInfoError) as exc:
            await manager.get_order("SW4J186Q")
        assert isinstance(exc.value.__cause__, fpx_err.FpxRequestError)


class TestGetOrders:
    @pytest.mark.asyncio
    async def test_batch(self, manager, account):
        second = dict(API_ORDER, order_uid="SECOND01", status="refunded")
        account._client.get_orders_api.return_value = api_response(
            {"status": "SUCCESS", "data": {"SW4J186Q": API_ORDER, "SECOND01": second}}
        )
        result = await manager.get_orders(["SW4J186Q", 1234, "#SECOND01"])
        assert result["SECOND01"].status is OrderStatusKind.REFUNDED
        account._client.get_orders_api.assert_awaited_once_with(["SW4J186Q", "1234", "SECOND01"], locale=None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [0, 11])
    async def test_batch_size_limit(self, manager, account, count):
        with pytest.raises(fpx_err.FpxAttributeError):
            await manager.get_orders([f"ORDER{i:03d}" for i in range(count)])
        account._client.get_orders_api.assert_not_awaited()
