"""Тесты RequestEngine — обёртка над httpx с ретраями, csrf и антифлудом."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from fpx.middlewares._request_engine import RequestEngine
from fpx.utils import errors as fpx_err


def make_response(status_code=200, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    return resp


@pytest.fixture
def account():
    acc = MagicMock()
    acc.data._csrf_token = "known_token"
    acc.profile.get_user_data = AsyncMock()
    return acc


@pytest.fixture
def http_client():
    return MagicMock()


class TestRequestEngineGet:
    @pytest.mark.asyncio
    async def test_get_success_returns_response(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)
        response = await engine.execute("GET", "/chat/")
        assert response.status_code == 200
        http_client.request.assert_awaited_once_with("GET", "/chat/")

    @pytest.mark.asyncio
    async def test_get_does_not_inject_csrf(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)
        await engine.execute("GET", "/chat/")
        _, kwargs = http_client.request.call_args
        assert "data" not in http_client.request.call_args.args
        assert http_client.request.call_args.kwargs == {}


class TestRequestEngineCsrf:
    @pytest.mark.asyncio
    async def test_post_injects_csrf_token_into_data_and_headers(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)
        await engine.execute("POST", "/runner/", data={"foo": "bar"})
        _, kwargs = http_client.request.call_args
        assert kwargs["data"]["csrf_token"] == "known_token"
        assert kwargs["headers"]["X-Cp-Csrf-Token"] == "known_token"
        assert kwargs["data"]["foo"] == "bar"

    @pytest.mark.asyncio
    async def test_post_does_not_override_existing_csrf(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)
        await engine.execute("POST", "/runner/", data={"csrf_token": "custom"})
        _, kwargs = http_client.request.call_args
        assert kwargs["data"]["csrf_token"] == "custom"

    @pytest.mark.asyncio
    async def test_post_fetches_user_data_when_token_missing(self, account, http_client):
        account.data._csrf_token = None

        async def fake_get_user_data():
            account.data._csrf_token = "fresh_token"

        account.profile.get_user_data = AsyncMock(side_effect=fake_get_user_data)
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)
        await engine.execute("POST", "/runner/", data={})
        account.profile.get_user_data.assert_awaited_once()
        _, kwargs = http_client.request.call_args
        assert kwargs["data"]["csrf_token"] == "fresh_token"

    @pytest.mark.asyncio
    async def test_put_and_delete_also_inject_csrf(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)
        for method in ("PUT", "DELETE"):
            http_client.request.reset_mock()
            await engine.execute(method, "/x", data={})
            _, kwargs = http_client.request.call_args
            assert kwargs["data"]["csrf_token"] == "known_token"

    @pytest.mark.asyncio
    async def test_concurrent_posts_fetch_csrf_token_once(self, account, http_client):
        account.data._csrf_token = None
        fetch_started = asyncio.Event()
        release_fetch = asyncio.Event()
        in_flight = 0
        max_in_flight = 0

        async def fake_get_user_data():
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            fetch_started.set()
            await release_fetch.wait()
            account.data._csrf_token = "fresh_token"
            in_flight -= 1

        account.profile.get_user_data = AsyncMock(side_effect=fake_get_user_data)
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)

        tasks = [asyncio.create_task(engine.execute("POST", "/runner/", data={})) for _ in range(10)]
        await fetch_started.wait()
        for _ in range(10):
            await asyncio.sleep(0)
        assert account.profile.get_user_data.await_count == 1
        assert max_in_flight == 1
        release_fetch.set()
        responses = await asyncio.gather(*tasks)

        assert all(response.status_code == 200 for response in responses)
        assert account.profile.get_user_data.await_count == 1
        assert max_in_flight == 1
        assert http_client.request.await_count == 10
        for call in http_client.request.await_args_list:
            assert call.kwargs["data"]["csrf_token"] == "fresh_token"
            assert call.kwargs["headers"]["X-Cp-Csrf-Token"] == "fresh_token"

        await asyncio.gather(*[engine.execute("POST", "/runner/", data={}) for _ in range(5)])
        assert account.profile.get_user_data.await_count == 1
        assert http_client.request.await_count == 15

    @pytest.mark.asyncio
    async def test_cached_csrf_token_skips_fetch_for_concurrent_posts(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)

        await asyncio.gather(*[engine.execute("POST", "/runner/", data={}) for _ in range(5)])

        account.profile.get_user_data.assert_not_awaited()
        assert http_client.request.await_count == 5

    @pytest.mark.asyncio
    async def test_csrf_fetch_retries_after_first_failure(self, account, http_client):
        account.data._csrf_token = None
        calls = 0

        async def fake_get_user_data():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("csrf fetch failed")
            account.data._csrf_token = "fresh_token"

        account.profile.get_user_data = AsyncMock(side_effect=fake_get_user_data)
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)

        with pytest.raises(RuntimeError, match="csrf fetch failed"):
            await engine.execute("POST", "/runner/", data={})
        http_client.request.assert_not_awaited()

        response = await engine.execute("POST", "/runner/", data={})
        assert response.status_code == 200
        assert account.profile.get_user_data.await_count == 2
        _, kwargs = http_client.request.call_args
        assert kwargs["data"]["csrf_token"] == "fresh_token"

    @pytest.mark.asyncio
    async def test_concurrent_mixed_methods_share_single_csrf_fetch(self, account, http_client):
        account.data._csrf_token = None
        release_fetch = asyncio.Event()

        async def fake_get_user_data():
            await release_fetch.wait()
            account.data._csrf_token = "fresh_token"

        account.profile.get_user_data = AsyncMock(side_effect=fake_get_user_data)
        http_client.request = AsyncMock(return_value=make_response(200))
        engine = RequestEngine(account, http_client)

        tasks = [
            asyncio.create_task(engine.execute(method, "/x", data={}))
            for method in ("POST", "PUT", "DELETE", "POST", "PUT")
        ]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release_fetch.set()
        await asyncio.gather(*tasks)

        assert account.profile.get_user_data.await_count == 1
        assert http_client.request.await_count == 5


class TestRequestEngineFlood:
    @pytest.mark.asyncio
    async def test_429_retries_and_eventually_succeeds(self, account, http_client, monkeypatch):
        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)
        responses = [make_response(429, {"Retry-After": "1"}), make_response(200)]
        http_client.request = AsyncMock(side_effect=responses)
        engine = RequestEngine(account, http_client)
        response = await engine.execute("GET", "/chat/")
        assert response.status_code == 200
        sleep_mock.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_429_invalid_retry_after_defaults_to_5(self, account, http_client, monkeypatch):
        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)
        responses = [make_response(429, {"Retry-After": "not-a-number"}), make_response(200)]
        http_client.request = AsyncMock(side_effect=responses)
        engine = RequestEngine(account, http_client)
        await engine.execute("GET", "/chat/")
        sleep_mock.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_429_triggers_flood_handlers_via_runner(self, account, http_client, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        create_task_mock = MagicMock()
        monkeypatch.setattr("asyncio.create_task", create_task_mock)
        responses = [make_response(429, {"Retry-After": "1"}), make_response(200)]
        http_client.request = AsyncMock(side_effect=responses)
        engine = RequestEngine(account, http_client)
        flood_handler = AsyncMock()
        engine.runner = MagicMock()
        engine.runner.router._handlers = {"flood": [flood_handler]}
        await engine.execute("GET", "/chat/")
        create_task_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_429_all_attempts_exhausted_raises(self, account, http_client, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        http_client.request = AsyncMock(return_value=make_response(429, {"Retry-After": "1"}))
        engine = RequestEngine(account, http_client)
        with pytest.raises(fpx_err.FpxRequestError):
            await engine.execute("GET", "/chat/")


class TestRequestEngineServerErrors:
    @pytest.mark.asyncio
    async def test_5xx_retries_with_backoff_then_succeeds(self, account, http_client, monkeypatch):
        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)
        responses = [make_response(503), make_response(200)]
        http_client.request = AsyncMock(side_effect=responses)
        engine = RequestEngine(account, http_client)
        response = await engine.execute("GET", "/chat/")
        assert response.status_code == 200
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_5xx_all_attempts_exhausted_raises(self, account, http_client, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        http_client.request = AsyncMock(return_value=make_response(502))
        engine = RequestEngine(account, http_client)
        with pytest.raises(fpx_err.FpxRequestError):
            await engine.execute("GET", "/chat/")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [502, 503, 504])
    async def test_5xx_on_post_is_not_retried(self, account, http_client, monkeypatch, status):
        """FunPay мог выполнить запрос: повтор отправил бы сообщение второй раз."""
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        http_client.request = AsyncMock(side_effect=[make_response(status), make_response(200)])
        engine = RequestEngine(account, http_client)
        with pytest.raises(fpx_err.FpxRequestOutcomeUnknownError):
            await engine.execute("POST", "/runner/", data={})
        assert http_client.request.await_count == 1


class TestRequestEngineTimeouts:
    @pytest.mark.asyncio
    async def test_get_read_timeout_retries_then_raises_original(self, account, http_client, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        http_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        engine = RequestEngine(account, http_client)
        with pytest.raises(httpx.ReadTimeout):
            await engine.execute("GET", "/chat/")
        assert http_client.request.await_count == 3

    @pytest.mark.asyncio
    async def test_post_read_timeout_raises_fpx_request_error_immediately(self, account, http_client):
        http_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        engine = RequestEngine(account, http_client)
        with pytest.raises(fpx_err.FpxRequestError) as exc:
            await engine.execute("POST", "/runner/", data={})
        assert http_client.request.await_count == 1
        assert isinstance(exc.value.__cause__, httpx.ReadTimeout)

    @pytest.mark.asyncio
    async def test_post_read_timeout_is_an_unknown_outcome(self, account, http_client):
        http_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        engine = RequestEngine(account, http_client)
        with pytest.raises(fpx_err.FpxRequestOutcomeUnknownError):
            await engine.execute("POST", "/runner/", data={})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError])
    async def test_a_broken_connection_after_a_post_is_an_unknown_outcome(self, account, http_client, error):
        http_client.request = AsyncMock(side_effect=error("broken"))
        engine = RequestEngine(account, http_client)
        with pytest.raises(fpx_err.FpxRequestOutcomeUnknownError) as exc:
            await engine.execute("POST", "/runner/", data={})
        assert http_client.request.await_count == 1
        assert isinstance(exc.value.__cause__, error)

    @pytest.mark.asyncio
    async def test_a_broken_connection_on_get_is_passed_through(self, account, http_client):
        http_client.request = AsyncMock(side_effect=httpx.ReadError("broken"))
        engine = RequestEngine(account, http_client)
        with pytest.raises(httpx.ReadError):
            await engine.execute("GET", "/chat/")

    @pytest.mark.asyncio
    async def test_connect_error_retries_then_raises(self, account, http_client, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        http_client.request = AsyncMock(side_effect=httpx.ConnectError("no connection"))
        engine = RequestEngine(account, http_client)
        with pytest.raises(httpx.ConnectError):
            await engine.execute("GET", "/chat/")
        assert http_client.request.await_count == 3

    @pytest.mark.asyncio
    async def test_connect_timeout_recovers_on_second_attempt(self, account, http_client, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        http_client.request = AsyncMock(side_effect=[httpx.ConnectTimeout("timeout"), make_response(200)])
        engine = RequestEngine(account, http_client)
        response = await engine.execute("GET", "/chat/")
        assert response.status_code == 200


def make_json_response(body, status_code=200):
    resp = make_response(status_code)
    resp.json = MagicMock(return_value=body)
    return resp


CSRF_ERROR = {"error": -1, "msg": "Обновите страницу и повторите попытку."}


class TestRequestEngineStaleCsrf:
    """csrf-токен привязан к сессии FunPay: если сессия сменилась, токен нужно обновить."""

    @staticmethod
    def _rotating_account(account, tokens):
        """get_user_data по очереди отдаёт токены из ``tokens``."""
        it = iter(tokens)

        async def fake_get_user_data():
            account.data._csrf_token = next(it)

        account.profile.get_user_data = AsyncMock(side_effect=fake_get_user_data)

    @pytest.mark.asyncio
    async def test_stale_token_is_refreshed_and_request_retried_once(self, account, http_client):
        account.data._csrf_token = "old_token"
        self._rotating_account(account, ["new_token"])
        http_client.request = AsyncMock(side_effect=[make_json_response(CSRF_ERROR), make_json_response({"ok": 1})])
        engine = RequestEngine(account, http_client)

        response = await engine.execute("POST", "/orders/review", data={"text": "hi"})

        assert response.json() == {"ok": 1}
        account.profile.get_user_data.assert_awaited_once()
        first, second = http_client.request.await_args_list
        assert first.kwargs["data"]["csrf_token"] == "old_token"
        assert first.kwargs["headers"]["X-Cp-Csrf-Token"] == "old_token"
        assert second.kwargs["data"]["csrf_token"] == "new_token"
        assert second.kwargs["headers"]["X-Cp-Csrf-Token"] == "new_token"
        assert second.kwargs["data"]["text"] == "hi"

    @pytest.mark.asyncio
    async def test_retry_happens_only_once(self, account, http_client):
        account.data._csrf_token = "old_token"
        self._rotating_account(account, ["new_token", "newer_token"])
        http_client.request = AsyncMock(return_value=make_json_response(CSRF_ERROR))
        engine = RequestEngine(account, http_client)

        response = await engine.execute("POST", "/orders/review", data={})

        assert response.json() == CSRF_ERROR
        assert http_client.request.await_count == 2
        assert account.profile.get_user_data.await_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_when_refreshed_token_is_the_same(self, account, http_client):
        """-1 может значить и другую ошибку: если токен не изменился, действие не дублируем."""
        account.data._csrf_token = "same_token"
        self._rotating_account(account, ["same_token"])
        http_client.request = AsyncMock(return_value=make_json_response(CSRF_ERROR))
        engine = RequestEngine(account, http_client)

        response = await engine.execute("POST", "/orders/review", data={})

        assert response.json() == CSRF_ERROR
        assert http_client.request.await_count == 1

    @pytest.mark.asyncio
    async def test_successful_post_does_not_refresh(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_json_response({"content": "ok"}))
        engine = RequestEngine(account, http_client)

        await engine.execute("POST", "/orders/review", data={})

        account.profile.get_user_data.assert_not_awaited()
        assert http_client.request.await_count == 1

    @pytest.mark.asyncio
    async def test_get_is_never_retried_on_csrf_like_body(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_json_response(CSRF_ERROR))
        engine = RequestEngine(account, http_client)

        await engine.execute("GET", "/chat/")

        account.profile.get_user_data.assert_not_awaited()
        assert http_client.request.await_count == 1

    @pytest.mark.asyncio
    async def test_caller_supplied_token_is_not_replaced(self, account, http_client):
        account.data._csrf_token = "engine_token"
        self._rotating_account(account, ["new_token"])
        http_client.request = AsyncMock(return_value=make_json_response(CSRF_ERROR))
        engine = RequestEngine(account, http_client)

        await engine.execute("POST", "/x", data={"csrf_token": "mine"}, headers={"X-Cp-Csrf-Token": "mine"})

        account.profile.get_user_data.assert_not_awaited()
        assert http_client.request.await_count == 1

    @pytest.mark.asyncio
    async def test_callers_data_dict_is_not_mutated(self, account, http_client):
        http_client.request = AsyncMock(return_value=make_json_response({"ok": 1}))
        engine = RequestEngine(account, http_client)
        data, headers = {"text": "hi"}, {"X-Requested-With": "XMLHttpRequest"}

        await engine.execute("POST", "/orders/review", data=data, headers=headers)

        assert data == {"text": "hi"}
        assert headers == {"X-Requested-With": "XMLHttpRequest"}

    @pytest.mark.asyncio
    async def test_concurrent_stale_posts_refresh_token_once(self, account, http_client):
        account.data._csrf_token = "old_token"
        self._rotating_account(account, ["new_token", "should_not_be_used"])

        async def fake_request(method, url, **kwargs):
            await asyncio.sleep(0)
            if kwargs["data"]["csrf_token"] == "old_token":
                return make_json_response(CSRF_ERROR)
            return make_json_response({"ok": 1})

        http_client.request = AsyncMock(side_effect=fake_request)
        engine = RequestEngine(account, http_client)

        responses = await asyncio.gather(*[engine.execute("POST", "/orders/review", data={}) for _ in range(8)])

        assert all(r.json() == {"ok": 1} for r in responses)
        assert account.profile.get_user_data.await_count == 1
        assert http_client.request.await_count == 16
