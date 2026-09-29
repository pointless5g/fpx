import asyncio
from dataclasses import asdict, fields
from typing import Any

from fpx.classes.account.subclasses.order import OrderManager
from fpx.classes.account.subclasses.profile import order_row_fields
from fpx.models.account import Order, Purchase
from fpx.utils import errors as fpx_err

# Поля, которые принимает Purchase: у Order есть свои (buyer_id), которых у покупки нет.
_PURCHASE_INIT_FIELDS = frozenset(f.name for f in fields(Purchase) if f.init)


class PurchaseManager:
    def __init__(self, account: Any):
        self._account = account

    async def get_purchase_details(self, order_id: str | int) -> Purchase:
        """
        Функция запрашивает детали покупки из /orders/{order_id}/.

        Args:
            order_id (str | int): ID заказа
        Returns:
            Purchase: Объект с данными:
                - order_id (str): ID заказа
                - status (str): Статус заказа.
                - review (dict): Словарь с данными отзыва, который оставили к заказу.
                - description (str): Строка с подробным описанием заказа
                - chat_id (str): ID чата
        Raises:
            FpxGetPurchaseInfoError: Ошибка запроса данных покупки
        """
        try:
            order_manager = OrderManager(self._account)
            order: Order = await order_manager.get_order_details(order_id)
            order_args = {key: value for key, value in asdict(order).items() if key in _PURCHASE_INIT_FIELDS}
            purchase = Purchase(**order_args)
        except Exception as e:
            raise fpx_err.FpxGetPurchaseInfoError(str(e)) from e
        return purchase

    async def get_my_purchases(self, limit: int = 0) -> list[Order]:
        """
        Запрашивает страницу покупок юзера.

        Args:
            limit (int): Лимит заказов, которые нужно вернуть(если 0, то вернёт все заказы).
        Returns:
            list: Список объектов, каждый содержит в себе:
                - order_id (str): ID заказа.
                - order_time (str): Время создания заказа.
                - client_name (str): Имя клиента.
                - price (float): Сумма заказа.
                - amount (int): Кол-во штук заказа (1 по дефолту).
                - topup_nickname (str): Данные, на которые отправлять пополнение. (ник, ссылка игрока и тд.)
                - status (str): Статус заказа.
                - name (str): Название заказа.
                - category (str): Категория заказа.
                - seller_id (int | None): ID продавца.
                - currency (Currency | None): Валюта цены.
                - subcategory_id (int | None), subcategory_type (str | None): Подкатегория (``lot``/``chip``).
                - created_at (datetime | None): Дата покупки по Москве.
                - status_kind (OrderStatusKind): Статус независимо от языка аккаунта.
                - chat_name (str | None): Имя чата с продавцом ``users-<ID>-<ID>``.
        Raises:
            FpxGetUserPurchasesError: Ошибка запроса покупок
        """
        counter = 0
        subcategories: dict[str, tuple[str, int]] | None = None
        page_user_id: str | None = None
        try:
            next_stage = True
            count_of_sells = 0
            data = []
            stage = "запроса данных FunPay"
            html = await self._account._client.get_my_purchases()
            next_page_id = ""
            while next_stage:
                if next_page_id:
                    html = await self._account._client.get_next_purchases(next_page_id)
                stage = "парсинга данных"
                # Фильтр игр (карта подкатегорий) есть только на первой странице.
                new_data = self._account._parser.parse_my_sells(html, subcategories=subcategories)
                subcategories = new_data.get("subcategories") or subcategories
                page_user_id = page_user_id or new_data.get("user-id")
                for i in new_data["sells"]:
                    data.append(i)
                count_of_sells += len(new_data["sells"])
                next_page_id = new_data.get("next_page")
                if not next_page_id:
                    next_stage = False
                    break
                if limit != 0 and count_of_sells >= limit:
                    next_stage = False
                    break
                await asyncio.sleep(3)
        except Exception as e:
            raise fpx_err.FpxGetUserPurchasesError(f"При выполнении {stage} произошла ошибка: {e}") from e
        if page_user_id and not self._account.data.user_id:
            self._account.data.user_id = page_user_id
        my_user_id = self._account.data.user_id or page_user_id
        if limit > 0:
            counter += 1
        result: list[Order] = []
        for i in data:
            if limit != 0 and counter > limit:
                break
            order = Purchase(
                order_id=i["order-id"],
                order_time=i["order-time"],
                client_name=i["client-name"],
                price=i["price"],
                status=i["status"],
                name=i["name"],
                category=i["category"],
                amount=i["amount"],
                topup_data=i.get("topup_data"),
                seller_id=i.get("client-id"),
                **order_row_fields(i, my_user_id),
            )
            result.append(order)
            counter += 1
        return result
