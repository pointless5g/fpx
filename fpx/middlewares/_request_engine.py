import asyncio
from typing import TYPE_CHECKING, Any

import httpx

from fpx.utils import errors as fpx_err

if TYPE_CHECKING:
    from fpx.classes.runner.runner import Runner


_WRITE_METHODS = ("POST", "PUT", "DELETE")
_CSRF_ERROR_CODE = 1
_CSRF_ERROR_HINT = "Обновите страницу"


class RequestEngine:
    def __init__(self, account: Any, client: httpx.AsyncClient) -> None:
        self._account = account
        self._client = client
        self.runner: "Runner | None" = None
        self._csrf_lock = asyncio.Lock()

    async def _ensure_csrf_token(self) -> None:
        if self._account.data._csrf_token is not None:
            return
        async with self._csrf_lock:
            if self._account.data._csrf_token is None:
                await self._account.profile.get_user_data()

    async def _refresh_csrf_token(self, stale_token: str | None) -> bool:
        """Перезапрашивает csrf-токен, если он всё ещё равен ``stale_token``.

        csrf токен фанпея привязан к сессии (PHPSESSID). Сессия может смениться,
        после чего старый токен перестаёт подходить.
        Если параллельный запрос уже обновил токен, повторно
        ходить на главную не нужно - просто берём свежий.

        Returns:
            bool: True, если актуальный токен отличается от ``stale_token``
                (то есть запрос имеет смысл повторить).
        """
        async with self._csrf_lock:
            if self._account.data._csrf_token == stale_token:
                self._account.data._csrf_token = None
                await self._account.profile.get_user_data()
            return self._account.data._csrf_token not in (None, stale_token)

    @staticmethod
    def _is_csrf_error(response: httpx.Response) -> bool:
        try:
            body = response.json()
        except Exception:
            return False
        if not isinstance(body, dict):
            return False
        msg = body.get("msg")
        error_code = int(body.get("error")) if body.get("error") else 0
        return error_code == _CSRF_ERROR_CODE or (isinstance(msg, str) and _CSRF_ERROR_HINT in msg)

    async def execute(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if method.upper() not in _WRITE_METHODS:
            return await self._send(method, url, **kwargs)

        data = dict(kwargs.get("data") or {})
        headers = dict(kwargs.get("headers") or {})
        own_data_token = "csrf_token" in data
        own_header_token = "X-Cp-Csrf-Token" in headers

        def with_csrf(token: str | None) -> dict[str, Any]:
            return {
                **kwargs,
                "data": data if own_data_token else {**data, "csrf_token": token},
                "headers": headers if own_header_token else {**headers, "X-Cp-Csrf-Token": token},
            }

        await self._ensure_csrf_token()
        used_token = self._account.data._csrf_token
        response = await self._send(method, url, **with_csrf(used_token))

        if (own_data_token and own_header_token) or not self._is_csrf_error(response):
            return response
        if not await self._refresh_csrf_token(used_token):
            return response
        return await self._send(method, url, **with_csrf(self._account.data._csrf_token))

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempts = 3
        backoff = 1.5  # множитель времени ожидания
        # Запрос на изменение, который мог дойти до сервера, не повторяется: FunPay мог его
        # выполнить, и повтор отправит сообщение или сохранит лот ещё раз.
        write = method.upper() in _WRITE_METHODS
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, url, **kwargs)
                # флуд контрль
                if response.status_code == 429:
                    if attempt == attempts - 1:
                        raise fpx_err.FpxRequestError(message=f"Превышено кол-во попыток запроса (Flood/429) к {url}")
                    try:
                        sleep_time = int(response.headers.get("Retry-After", 5))
                    except (ValueError, TypeError):
                        sleep_time = 5
                    if self.runner:
                        for handler in self.runner.router._handlers["flood"]:
                            asyncio.create_task(handler(sleep_time))
                    await asyncio.sleep(sleep_time)
                    continue
                # если чето сервер не ответил
                if response.status_code in (502, 503, 504):
                    if write:
                        raise fpx_err.FpxRequestOutcomeUnknownError(
                            f"{method} {url}: сервер ответил {response.status_code}, запрос мог выполниться"
                        )
                    sleep_time = backoff ** float(attempt)
                    await asyncio.sleep(sleep_time)
                    continue
                if response.url == "https://funpay.com/account/login":
                    raise fpx_err.FpxAuthError("Неверный gkey, обнови свои куки.")
                return response
            except httpx.ReadTimeout as e:
                if write:
                    raise fpx_err.FpxRequestOutcomeUnknownError(
                        f"{method} {url} упал по таймауту ответа, запрос мог выполниться: {e}"
                    ) from e
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(backoff**attempt)
            except (httpx.ReadError, httpx.WriteError, httpx.WriteTimeout, httpx.RemoteProtocolError) as e:
                # Соединение оборвалось, когда запрос мог уже уйти.
                if write:
                    raise fpx_err.FpxRequestOutcomeUnknownError(
                        f"{method} {url}: соединение оборвалось, запрос мог выполниться: {e}"
                    ) from e
                raise
            except (httpx.ConnectTimeout, httpx.ConnectError):
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(backoff**attempt)
        raise fpx_err.FpxRequestError(message=f"Превышено количество попыток запроса к {url}")
