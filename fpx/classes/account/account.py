import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import aiofiles
import httpx

from fpx._api._client import FunPayClient
from fpx._parsers import FpxParser
from fpx.classes.account.subclasses.addons import AddonsManager
from fpx.classes.account.subclasses.category import CategoryManager
from fpx.classes.account.subclasses.chat import ChatManager
from fpx.classes.account.subclasses.editor import FunPayEditor
from fpx.classes.account.subclasses.lot import LotManager
from fpx.classes.account.subclasses.order import OrderManager
from fpx.classes.account.subclasses.profile import ProfileManager
from fpx.classes.account.subclasses.purchase import PurchaseManager
from fpx.classes.account.subclasses.review import ReviewManager
from fpx.middlewares._request_engine import RequestEngine
from fpx.utils import errors as fpx_err
from fpx.utils.errors import FpxRefreshCookieError


@dataclass
class AccountData:
    """Хранит данные аккаунта"""

    username: Optional[str] = None
    user_id: Optional[str] = None
    _csrf_token: Optional[str] = None
    _node_names: dict[str, Any] = field(default_factory=dict)


class Account:
    """
    Взаимодействует с аккаунтом.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._http_client = client
        self._client = FunPayClient(self, self._http_client)
        self._request_engine = RequestEngine(self, self._http_client)
        self._parser = FpxParser()
        self.data = AccountData()
        self.chat = ChatManager(self)
        self.addons = AddonsManager(self)
        self.profile = ProfileManager(self)
        self.order = OrderManager(self)
        self.lot = LotManager(self)
        self.editor = FunPayEditor(self)
        self.review = ReviewManager(self)
        self.category = CategoryManager(self)
        self.purchase = PurchaseManager(self)

    async def upload_image(self, file_path: str) -> int:
        """
        Загрузка изображения на FunPay.
        Args:
            file_path (str): Путь до файла изображения.
        Returns:
            int: ID изображения на FunPay

        Raises:
            FpxRequestError: Ошибка загрузки.
        """
        async with aiofiles.open(file_path, mode="rb") as f:
            image_data = await f.read()

        result = await self._client.upload_image(image_data)
        return int(result["fileId"])

    async def upload_image_bytes(self, image: bytes, file_name: str = "image.png") -> int:
        """
        Загрузка изображения на FunPay из памяти.

        Returns:
            int: ID изображения на FunPay, для chat.send(chat_id, image_id=...).

        Raises:
            FpxImageUploadError: FunPay не принял картинку.
        """
        result = await self._client.upload_image(image, file_name)
        try:
            return int(result["fileId"])
        except (KeyError, TypeError, ValueError) as e:
            raise fpx_err.FpxImageUploadError(f"FunPay не вернул ID картинки: {result!r:.200}") from e

    async def _refresh_cookies(self) -> Optional[int]:
        cookies = await self._client.refresh_session_cookies()
        headers = cookies.headers
        MAX_AGE_RE = re.compile(r"max-age=(\d+)", re.IGNORECASE)
        for raw_cookie in headers.get_list("set-cookie"):
            if raw_cookie.startswith("PHPSESSID="):
                # так как csrf токен привязан к сессии надо новый
                self.data._csrf_token = None
            if raw_cookie.startswith("golden_seal="):
                match = MAX_AGE_RE.search(raw_cookie)
                return int(match.group(1)) if match else None
        return None

    async def refresh_cookies_cycle(self) -> None:
        """
        Обновление gseal и PHPSESSID.
        Запускает цикл обновления куков.
        Сам внутри обновляет куки каждую неделю.

        Raises:
            FpxRefreshCookieError: Ошибка обновления куков
        """
        while True:
            ex_time = None
            atts = 0
            while ex_time is None:
                try:
                    ex_time = await self._refresh_cookies()
                except Exception as e:
                    atts += 1
                    if atts > 3:
                        raise FpxRefreshCookieError(f"Ошибка обновления куков: {e}") from e
                if ex_time is None:
                    await asyncio.sleep(15)
            await asyncio.sleep(ex_time)
