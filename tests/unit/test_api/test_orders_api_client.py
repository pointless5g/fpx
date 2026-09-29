"""Тесты FunPayClient.get_orders_api — сырой запрос POST /api/orders/get."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from fpx._api._client import FunPayClient
from fpx.middlewares._request_engine import RequestEngine


class TestGetOrdersApiPayload:
    @pytest.mark.asyncio
    async def test_posts_json_through_request_engine(self):
        account = MagicMock()
        response = MagicMock()
        account._request_engine.execute = AsyncMock(return_value=response)
        client = FunPayClient(account, MagicMock())

        result = await client.get_orders_api(["SW4J186Q"], locale="en")

        assert result is response
        args, kwargs = account._request_engine.execute.call_args
        assert args == ("POST", "/api/orders/get")
        assert json.loads(kwargs["content"]) == {
            "order_uids": ["SW4J186Q"],
            "include": ["details", "users", "review"],
        }
        assert kwargs["headers"] == {"Content-Type": "application/json", "Accept-Language": "en"}

    @pytest.mark.asyncio
    async def test_without_locale_keeps_client_language(self):
        account = MagicMock()
        account._request_engine.execute = AsyncMock()
        client = FunPayClient(account, MagicMock())
        await client.get_orders_api(["A", "B"])
        _, kwargs = account._request_engine.execute.call_args
        assert "Accept-Language" not in kwargs["headers"]


class TestGetOrdersApiOnTheWire:
    @pytest.mark.asyncio
    async def test_body_is_json_and_csrf_goes_in_header(self):
        """execute() кладёт csrf в data=, но на провод уходит ровно JSON из content=."""
        seen: dict = {}

        def handle(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["content_type"] = request.headers.get("content-type")
            seen["csrf"] = request.headers.get("x-cp-csrf-token")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "SUCCESS", "data": []})

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="https://funpay.com")
        account = MagicMock()
        account.data._csrf_token = "tok"
        account._request_engine = RequestEngine(account, http_client)
        client = FunPayClient(account, http_client)
        try:
            response = await client.get_orders_api(["SW4J186Q"])
        finally:
            await http_client.aclose()

        assert response.status_code == 200
        assert seen == {
            "method": "POST",
            "path": "/api/orders/get",
            "content_type": "application/json",
            "csrf": "tok",
            "body": {"order_uids": ["SW4J186Q"], "include": ["details", "users", "review"]},
        }
