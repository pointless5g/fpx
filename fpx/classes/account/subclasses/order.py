from collections.abc import Iterable
from typing import Any, cast

from fpx.models.account import Order, OrderInfo
from fpx.utils import errors as fpx_err
from fpx.utils.order_status import is_refunded_status

# Столько заказов FunPay отдаёт за один запрос к /api/orders/get (ограничение из FunPayAPI).
MAX_ORDERS_PER_API_REQUEST = 10


def _order_uid(order_id: str | int) -> str:
    text = str(order_id).strip()
    return text[1:] if text.startswith("#") else text


class OrderManager:
    def __init__(self, account: Any) -> None:
        # account: Account (см. fpx/classes/account/account.py). Оставлен как Any,
        # так как сам класс Account ещё не аннотирован (отдельная задача #20).
        self._account = account

    async def get_order_details(self, order_id: str | int) -> Order:
        """
        Функция запрашивает детали заказа из /orders/{order_id}/.

        Args:
            order_id (str | int): ID заказа
        Returns:
            Order: Объект с данными:
                - order_id (str): ID заказа
                - status (str): Статус заказа.
                - review (dict): Словарь с данными отзыва, который оставили к заказу.
                - description (str): Строка с подробным описанием заказа
                - chat_id (str): ID чата
        Raises:
            FpxGetOrderInfoError: Ошибка запроса данных заказа
        """
        try:
            stage = "запроса данных FunPay"
            html = await self._account._client.get_order_info(order_id)
            stage = "парсинга данных"
            data = self._account._parser.parse_order_page(html)
            stage = "типизации данныз"
            order = Order(
                order_id=str(order_id),
                status=data["status"],
                review=data["review"],
                description=data.get("desc"),
                chat_id=data["chat_id"],
            )
        except Exception as e:
            raise fpx_err.FpxGetOrderInfoError(f"При выполнении {stage} произошла ошибка: {e}") from e
        return order

    async def get_order(self, order_id: str | int, locale: str | None = None) -> OrderInfo:
        """
        Запрашивает заказ через JSON API FunPay (``POST /api/orders/get``), как ``FunPayAPI.Account.get_order``.

        В отличие от ``get_order_details`` (HTML-страница ``/orders/{id}/``) отдаёт ID покупателя и продавца,
        имя чата, подкатегорию, валюту, поля оплаченного лота и товары автовыдачи.

        Args:
            order_id (str | int): ID заказа (``#`` в начале можно оставить).
            locale (str | None): ``ru`` / ``en`` / ``uk`` для заголовка ``Accept-Language``;
                по умолчанию — язык клиента.
        Returns:
            OrderInfo: Объект с данными:
                - order_id (str), status (OrderStatusKind): ID и статус
                  (paid / closed / refunded / partially_refunded / unpaid).
                - buyer_id, buyer_username, seller_id, seller_username: участники.
                - chat_name (str): Имя чата ``users-<ID>-<ID>``.
                - sum (float), currency (Currency): Сумма и валюта заказа.
                - amount (int | float | None): Количество товара.
                - subcategory_id, subcategory_type, subcategory_name: Подкатегория.
                - fields (dict[str, OrderField]), short_description, full_description, lot_params:
                  Поля оплаченного лота.
                - player, server, side, order_secrets, review, locale.
        Raises:
            FpxGetOrderInfoError: Ошибка запроса или разбора; исходная причина — в ``__cause__``.
        """
        uid = _order_uid(order_id)
        orders = await self.get_orders([uid], locale=locale)
        # FunPayAPI берёт заказ по ключу data; на случай другого ключа — по order_uid самого заказа.
        order = orders.get(uid) or next((info for info in orders.values() if info.order_id == uid), None)
        if order is None:
            raise fpx_err.FpxGetOrderInfoError(f"FunPay не вернул заказ #{uid}")
        return order

    async def get_orders(self, order_ids: Iterable[str | int], locale: str | None = None) -> dict[str, OrderInfo]:
        """
        Запрашивает до 10 заказов одним запросом к JSON API FunPay (``POST /api/orders/get``).

        Args:
            order_ids (Iterable[str | int]): От 1 до 10 ID заказов.
            locale (str | None): ``ru`` / ``en`` / ``uk`` для заголовка ``Accept-Language``.
        Returns:
            dict[str, OrderInfo]: Найденные заказы по ID. Заказов, которых FunPay не вернул, в словаре нет.
        Raises:
            FpxAttributeError: Передано 0 или больше 10 ID.
            FpxGetOrderInfoError: Ошибка запроса или разбора; исходная причина — в ``__cause__``.
        """
        uids = [_order_uid(order_id) for order_id in order_ids]
        if not 1 <= len(uids) <= MAX_ORDERS_PER_API_REQUEST:
            raise fpx_err.FpxAttributeError(
                f"За один запрос можно получить от 1 до {MAX_ORDERS_PER_API_REQUEST} заказов, передано {len(uids)}"
            )
        stage = "запроса данных FunPay"
        try:
            response = await self._account._client.get_orders_api(uids, locale=locale)
            stage = "проверки ответа FunPay"
            # Как FunPayAPI.Account.method: 403 — сессия не принята, любой другой не-200 — сбой запроса.
            if response.status_code == 403:
                raise fpx_err.FpxAuthError("FunPay ответил 403 на запрос заказов: сессия не принята")
            if response.status_code != 200:
                raise fpx_err.FpxRequestError(f"FunPay ответил {response.status_code} на запрос заказов")
            stage = "парсинга данных"
            orders = self._account._parser.parse_orders_api(response.json(), locale=locale or "ru")
        except Exception as e:
            raise fpx_err.FpxGetOrderInfoError(f"При выполнении {stage} произошла ошибка: {e}") from e
        return cast(dict[str, OrderInfo], orders)

    async def find_orders_by_buyer_name(
        self,
        buyer_name: str | None = None,
        order_name: str | None = None,
        search_mode: str = "partial",  # 'exact' полное совпадение, 'partial' по части, 'keywords' по словам
        full_info: bool = True,
    ) -> list[Order]:
        """
        Ищет все заказы по имени покупателя или названию заказа,
            или по названию заказа и имени покупателя.

        Args:
            buyer_name (str | None): Имя покупателя.
            order_name (str | None): Название заказа. Регистр игнорируется
            search_mode (str, optional): Режим поиска для order_name:
                - 'exact': точное совпадение названия;
                - 'partial': поиск по части строки (подстроке);
                - 'keywords': поиск по ключевым словам (все слова должны присутствовать).
                По умолчанию 'partial'.
            full_info (bool): Спрашивает показывать ли полную информацию
                по каждому заказу (требует дополнительный запрос).
                True по дефолту
        Returns:
            list[Order]: Список объектов Order, которые содержат:
                - order_id (str): ID заказа
                - order_time (str): Время заказа
                - client_name (str): Имя покупателя
                - price (float): Сумма заказа
                - status (str): Статус заказа
                - name (str): Название купленного лота
                - category (str): Категория заказа
                - amount (int): Кол-во штук заказа
                - topup_data (str): Данные пополнения (ссылка, ник, тп)
                - review (dict): Словарь с данными отзыва, который оставили к заказу.
                - description (str): Строка с подробным описанием заказа
                - chat_id (str): ID чата
        Raises:
            FpxGetOrderInfoError: Ошибка запроса данных заказа
        """
        stage = "запросе данных"
        good_orders: list[Order] = []
        try:
            orders = await self._account.profile.get_my_sells()
            for order in orders:
                checks = []
                if buyer_name is not None:
                    checks.append(order.client_name == buyer_name)
                if order_name is not None:
                    if search_mode == "exact":
                        checks.append(order.name.lower() == order_name.lower())
                    elif search_mode == "partial":
                        checks.append(order_name.lower() in order.name.lower())
                    elif search_mode == "keywords":
                        parts = order_name.lower().split()
                        checks.append(all(p in order.name.lower() for p in parts))
                if checks and all(checks):
                    good_orders.append(order)
            if buyer_name is None and order_name is None:
                good_orders = []
            if full_info is True:
                for order in good_orders:
                    assert order.order_id is not None, "order_id не может быть None для существующего заказа"
                    full_order = await self.get_order_details(order.order_id)
                    order.chat_id = full_order.chat_id
                    order.description = full_order.description
                    order.review = full_order.review
        except Exception as e:
            raise fpx_err.FpxGetOrderInfoError(f"При {stage} произошла ошибка: {e}") from e
        return good_orders

    async def refund_order(self, order_id: str | int) -> bool | None:
        """
        Делает возврат заказа.

        Args:
            order_id (str | int): Айди заказа
        Returns:
            bool: True если возврат прошёл успешно.
        Raises:
            FpxRefundError: Не удалось сделать возврат.

        """
        response = await self._account._client.refund_order(order_id)
        if response.status_code == 200:
            s = await self.get_order_details(order_id)
            status = s.status
            if is_refunded_status(status):
                return True
            raise fpx_err.FpxRefundError(f"Невозможно сделать возврат, текущий статус: {status}")
        return None
