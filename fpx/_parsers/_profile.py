from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from fpx.models.account import Balance, Transaction, TransactionsPage
from fpx.utils import errors as fpx_err
from fpx.utils.currency import Currency, parse_currency
from fpx.utils.dates import parse_funpay_datetime
from fpx.utils.order_status import OrderStatusKind, classify_order_status

from ._base import BaseParser

logger = logging.getLogger("fpx.profile_parser")


_AMOUNT_RE = re.compile(r"([+\-−–—]?\s*\d+(?:[.,]\d+)?)")
_PAYMENT_METHOD_RE = re.compile(r"payment-method-([a-zA-Z0-9_]+)")
_ORDER_TYPE_MARKERS = ("заказ", "order", "замовлення")
_WITHDRAW_TYPE_MARKERS = ("вывод", "withdraw", "виведен", "вивід", "виводу")
_PAYMENT_TYPE_MARKERS = ("пополнен", "payment", "поповнен")

# Таблица заказов (/orders/trade, /orders/).
_USER_HREF_RE = re.compile(r"/users/(\d+)")
_ORDER_HREF_RE = re.compile(r"/orders/(?!trade(?:[/?#]|$))[A-Za-z0-9]+/?(?:[?#]|$)")
_TRAILING_SYMBOL_RE = re.compile(r"([^\d\s.,]+)\s*$")
# FunPayAPI RegularExpressions.PRODUCTS_AMOUNT: «…, 1 000 шт.» в описании строки заказа.
_SALE_PIECES_RE = re.compile(r",\s(\d{1,3}(?:\s?\d{3})*)\s(?:шт|pcs)\.")
_PIECES_WITH_DATA_RE = re.compile(r"(\d{1,3}(?:\s?\d{3})*)\s*(?:шт\.?|pcs\.?)\s*,\s*(.+)$", re.IGNORECASE)
_PIECES_RE = re.compile(r"(\d{1,3}(?:\s?\d{3})*)\s*(?:шт\.?|pcs\.?)", re.IGNORECASE)
_ORDERS_PAGE_TITLES = ("мои продажи", "мої продажі", "my sales", "мои покупки", "мої покупки", "my purchases")


def _normalize_space(text: str) -> str:
    return " ".join(text.split())


def _to_int(number: str) -> int:
    return int("".join(number.split()))


class ProfileParser(BaseParser):
    @classmethod
    def parse_2fa_status(cls, html_content: str) -> bool:
        """
        Парсит https://funpay.com/security/twoFactorSetting
        Чекает хайден инпуты /security/twoFactorSetting: если 2FA выключена, isEnabled value=,
        если включена - value=1.
        """
        if not html_content or not str(html_content).strip():
            raise fpx_err.FpxNullDataError("Страница настроек 2FA пустая")

        soup = BeautifulSoup(html_content, "html.parser")

        input_tag = soup.find("input", attrs={"name": "isEnabled"})
        if input_tag is None:
            raise fpx_err.FpxParseError("Не удалось определить статус 2FA: input 'isEnabled' не найден на странице.")
        return input_tag.get("value") == "1"

    @classmethod
    def parse_finanses(cls, html_content: str) -> Balance:
        """Парсит https://funpay.com/account/balance"""
        soup = BeautifulSoup(html_content, "html.parser")
        balances_container = soup.find("span", class_="balances-list")
        if not balances_container:
            raise fpx_err.FpxNullDataError("На странице финансов не найдено модуля баланса")
        values = balances_container.find_all("span", class_="balances-value")
        if not values:
            raise fpx_err.FpxNullDataError("На странице финансов не найдено баланса")
        clean_values = [cls.clean_text(v) for v in values]
        data: dict[str, float] = {}
        for i in clean_values:
            try:
                value = i.replace("₽", "").replace("$", "").replace("€", "").replace(",", ".").strip()
                num = float(value)
                if "₽" in i:
                    data["rub"] = num
                elif "$" in i:
                    data["usd"] = num
                elif "€" in i:
                    data["eur"] = num
            except Exception as e:
                logger.debug(f"Ошибка парсинга отдельной валюты: {e}. Пропускаем")
                continue
        if not data:
            raise fpx_err.FpxParseError(
                "Не удалось распарсить ни одну валюту, верстка полностью изменилась или что-то сломалось."
            )
        return Balance(**data)

    @classmethod
    def parse_profile(cls, html_content: str) -> dict[str, Any]:
        """Парсит https://funpay.com/users/.../"""
        soup = BeautifulSoup(html_content, "html.parser")
        offer_list = soup.find_all("div", class_="offer") or soup.find_all("div", attrs={"data-id": True})
        review_list = soup.find_all("div", class_="review-compiled-review") or soup.find_all(
            "div", class_="review-item"
        )
        if not offer_list or not review_list:
            logger.debug(
                "На странице профиля не найден блок категорий или блок отзывов."
                "Возможно ошибка или их просто не существует"
            )
        category_ids: set[str] = set()
        lots: list[dict[str, str]] = []
        for offer in offer_list:
            links = offer.find_all("a", href=True)
            if not links:
                logger.debug("В блоке категории не найдено лотов. Возможно ошибка/Их просто не существует")
            for link in links:
                try:
                    href = str(link["href"])
                    if "/lots/" in href and "id=" not in href:
                        cat_id = href.strip("/").split("/")[-1]
                        if cat_id.isdigit():
                            category_ids.add(cat_id)
                    if "id=" in href:
                        lot_id = href.split("id=")[-1].split("&")[0]
                        name_tag = link.find("div", class_="tc-desc-text")
                        name = name_tag.get_text(strip=True) if name_tag else "Unknown"
                        lots.append({"name": name, "id": lot_id})
                except Exception as e:
                    logger.debug(f"Ошибка парсинга отдельной категории: {e}")
                    continue
        if not lots:
            logger.debug("Не удалось распарсить ни один лот. Возможно изменилась вёрстка/у вас просто нет лотов.")
        reviews: list[dict[str, Any]] = []
        for review in review_list:
            try:
                rev: dict[str, Any] = {}
                text_tag = review.find("div", class_="review-item-text") or review.find("div")
                rev["text"] = cls.clean_text(text_tag)
                rate_div = review.find("div", class_="rating")
                if rate_div:
                    inner_div = rate_div.find("div", class_=True)
                    if inner_div:
                        classes_str = cls._get_str_attr(inner_div, "class")
                        match = re.search(r"\d+", classes_str)
                        rev["stars"] = int(match.group()) if match else 0
                    else:
                        rev["stars"] = 0
                else:
                    rev["stars"] = 0
                author_tag = review.find("div", class_="media-user-name") or review.find("span", class_="pseudo-a")
                rev["author"] = cls.clean_text(author_tag) if author_tag else "Unknown"
                detail_tag = review.find("div", class_="review-item-detail")
                rev["detail"] = cls.clean_text(detail_tag)
                order_div = review.find("div", class_="review-item-order")
                if order_div:
                    a_tag = order_div.find("a", href=True)
                    rev["order_id"] = cls._get_str_attr(a_tag, "href").strip("/").split("/")[-1] if a_tag else ""
                else:
                    rev["order_id"] = ""
                reviews.append(rev)
            except Exception as e:
                logger.debug(f"При парсинге конкретного отзыва возникла ошибка: {e}")
                continue
        if not reviews:
            logger.debug("Не удалось распарсить ни один отзыв, возможно их просто нет/возникла какая-то ошибка")
        return {"category-ids": list(category_ids), "lots": lots, "reviews": reviews}

    @classmethod
    def parse_my_sells(
        cls,
        html_content: str,
        subcategories: dict[str, tuple[str, int]] | None = None,
    ) -> dict[str, Any]:
        """
        Парсит таблицу заказов: продажи https://funpay.com/orders/trade и покупки https://funpay.com/orders/.

        Разбор строки повторяет ``FunPayAPI.Account.get_sales``: статус по классу строки
        (``warning`` — возврат, ``info`` — оплачен, иначе закрыт), ID собеседника из ``data-href``,
        валюта по знаку, подкатегория по фильтру игр ``select[name=game]``, дата по Москве.

        Args:
            html_content: HTML страницы (или ответа на ``continue``).
            subcategories: Карта «Игра, Подкатегория» → (тип, ID) с первой страницы. Нужна для
                следующих страниц: фильтр игр есть только на первой.
        Returns:
            dict:
                - sells (list[dict]): строки таблицы, у каждой: order-id, order-time, status,
                  status-kind, client-name, client-id, price, currency, name, category,
                  subcategory-type, subcategory-id, created-at, amount, topup_data;
                - next_page (str | None): курсор ``continue`` следующей страницы, если он есть в разметке;
                - subcategories (dict): карта подкатегорий, если на странице есть фильтр игр;
                - user-id (str): ID владельца сессии из ``data-app-data``, если он есть.
        Raises:
            FpxNullDataError: на странице нет ни строк, ни признаков таблицы заказов.
            FpxParseError: строки есть, но ни одну не удалось разобрать.
        """
        result: dict[str, Any] = {}
        result["sells"] = []
        soup = BeautifulSoup(html_content, "html.parser")
        page_subcategories = cls._parse_game_filter(soup)
        if page_subcategories is not None:
            result["subcategories"] = page_subcategories
            subcategories = page_subcategories or subcategories
        user_id = cls._parse_app_user_id(soup)
        if user_id:
            result["user-id"] = user_id
        tc_items = soup.find_all("a", class_="tc-item")
        if not tc_items:
            # Только ссылки на сами заказы: «/orders/» и «/orders/trade» из шапки сайта строками не являются.
            tc_items = soup.find_all("a", href=lambda h: bool(h and _ORDER_HREF_RE.search(h)))
        if not tc_items:
            if not cls._is_orders_page(soup):
                raise fpx_err.FpxNullDataError("На странице продаж не найдено объектов(tc-item)")
            # Продавец без продаж (или покупатель без покупок): таблица пустая, это не ошибка.
            logger.debug("Таблица заказов пуста")
        for item in tc_items:
            try:
                result["sells"].append(cls._parse_sale_row(item, subcategories))
            except Exception as e:
                logger.debug(f"При парсинге конкретного объекта произошла ошибка: {e}")
                continue
        if tc_items and not result["sells"]:
            raise fpx_err.FpxParseError("При парсинге не найдено ни одной продажи")
        form_class = soup.find("form", class_="dyn-table-form")
        continue_input = soup.find("input", attrs={"name": "continue"})
        if form_class or continue_input:
            input_tag = continue_input if isinstance(continue_input, Tag) else None
            if input_tag is None and isinstance(form_class, Tag):
                first_input = form_class.find("input")
                input_tag = first_input if isinstance(first_input, Tag) else None
            result["next_page"] = cls._get_str_attr(input_tag, "value") if input_tag else None
        return result

    @classmethod
    def _parse_sale_row(cls, item: Tag, subcategories: dict[str, tuple[str, int]] | None) -> dict[str, Any]:
        """Одна строка таблицы заказов (``a.tc-item``)."""
        pre_result: dict[str, Any] = {}
        order_tag = item.find("div", class_="tc-order") or item.find("div", class_=lambda c: c and "order" in c)
        pre_result["order-id"] = order_tag.get_text(strip=True).replace("#", "") if order_tag else "Unknown"
        time_tag = item.find("div", class_="tc-date-time")
        pre_result["order-time"] = time_tag.get_text(strip=True) if time_tag else ""
        pre_result["created-at"] = parse_funpay_datetime(time_tag.get_text(" ", strip=True) if time_tag else None)
        status_tag = item.find("div", class_="tc-status")
        pre_result["status"] = status_tag.get_text(strip=True) if status_tag else "Unknown"
        pre_result["status-kind"] = cls._sale_status_kind(item, pre_result["status"])
        client_tag = (
            item.find("span", class_="pseudo-a")
            or item.find("div", class_="tc-user")
            or item.find("div", class_=lambda c: c and "user" in c)
        )
        pre_result["client-name"] = client_tag.get_text(strip=True) if client_tag else "Unknown"
        pre_result["client-id"] = cls._sale_client_id(item, client_tag)
        price_tag = item.find("div", class_="tc-price")
        if isinstance(price_tag, Tag):
            raw_price = price_tag.get_text(strip=True).replace(",", ".")
            cleaned_price = "".join(c for c in raw_price if c.isdigit() or c == ".")
            pre_result["price"] = float(cleaned_price) if cleaned_price else 0.0
            pre_result["currency"] = cls._sale_currency(price_tag)
        else:
            pre_result["price"] = 0.0
            pre_result["currency"] = None
        order_desc = item.find("div", class_="order-desc")
        if isinstance(order_desc, Tag):
            divs: list[Any] = order_desc.find_all(["div", "span", "p"], recursive=False)
            if not divs:
                divs = [order_desc]
            raw_name = divs[0].get_text(strip=True) if len(divs) > 0 else "Unknown"
            pre_result["name"] = raw_name
            pre_result["category"] = divs[1].get_text(strip=True) if len(divs) > 1 else "Unknown"
            pre_result["amount"], pre_result["topup_data"] = cls._sale_amount(raw_name)
        else:
            pre_result["name"] = "Unknown"
            pre_result["category"] = "Unknown"
            pre_result["amount"] = 1
            pre_result["topup_data"] = None
        # Как FunPayAPI: «Игра, Подкатегория» из div.text-muted ищется в фильтре игр.
        muted = item.find("div", class_="text-muted")
        subcategory_name = cls.clean_text(muted) if muted else pre_result["category"]
        subcategory = (subcategories or {}).get(_normalize_space(subcategory_name))
        pre_result["subcategory-type"] = subcategory[0] if subcategory else None
        pre_result["subcategory-id"] = subcategory[1] if subcategory else None
        return pre_result

    @classmethod
    def _sale_status_kind(cls, item: Tag, status_text: str) -> OrderStatusKind:
        """Статус по классу строки, как FunPayAPI; без класса — по подписи, по умолчанию «закрыт»."""
        classes = cls._get_class_list(item)
        if "warning" in classes:
            return OrderStatusKind.REFUNDED
        if "info" in classes:
            return OrderStatusKind.PAID
        return classify_order_status(status_text) or OrderStatusKind.CLOSED

    @classmethod
    def _sale_client_id(cls, item: Tag, client_tag: Any) -> int | None:
        """ID собеседника из ``data-href="https://funpay.com/users/<id>/"`` у его ника или аватара."""
        candidates = (
            item.select_one("div.media-user-name [data-href]"),
            client_tag,
            item.select_one("[data-href*='/users/']"),
        )
        for candidate in candidates:
            if not isinstance(candidate, Tag):
                continue
            match = _USER_HREF_RE.search(cls._get_str_attr(candidate, "data-href"))
            if match:
                return int(match.group(1))
        return None

    @classmethod
    def _sale_currency(cls, price_tag: Tag) -> Currency | None:
        """Валюта по знаку: ``<span class="unit">₽</span>`` или последний символ суммы."""
        unit = price_tag.find("span", class_="unit")
        symbol = cls.clean_text(unit) if unit else ""
        if not symbol:
            match = _TRAILING_SYMBOL_RE.search(price_tag.get_text(" ", strip=True))
            symbol = match.group(1) if match else ""
        return parse_currency(symbol)

    @classmethod
    def _sale_amount(cls, raw_name: str) -> tuple[int, str | None]:
        """
        Количество и данные для пополнения из описания заказа.

        Количество сначала ищется как в FunPayAPI (``…, 1 000 шт.``), затем в форме
        ``N шт., данные``. Разделители тысяч учитываются, по умолчанию — 1.
        """
        amount: int | None = None
        match = _SALE_PIECES_RE.search(raw_name)
        if match:
            amount = _to_int(match.group(1))
        topup_data = None
        with_data = _PIECES_WITH_DATA_RE.search(raw_name)
        if with_data:
            if amount is None:
                amount = _to_int(with_data.group(1))
            topup_data = with_data.group(2).strip() or None
        elif amount is None:
            plain = _PIECES_RE.search(raw_name)
            if plain:
                amount = _to_int(plain.group(1))
        return (amount if amount is not None else 1), topup_data

    @classmethod
    def _parse_game_filter(cls, soup: BeautifulSoup) -> dict[str, tuple[str, int]] | None:
        """
        Карта подкатегорий из фильтра игр ``select[name=game]``, как в FunPayAPI.

        У каждой ``option`` игры в ``data-data`` лежит JSON ``[["lot-256", "Аккаунты"], ...]``.
        Ключ карты — ``"Игра, Подкатегория"`` (так подкатегория подписана в строке заказа),
        значение — (``lot`` | ``chip``, ID).

        Returns:
            Карта или ``None``, если фильтра на странице нет (ответ на ``continue``).
        """
        select = soup.find("select", attrs={"name": "game"})
        if not isinstance(select, Tag):
            return None
        result: dict[str, tuple[str, int]] = {}
        for option in select.find_all("option"):
            if not isinstance(option, Tag) or not option.get("value"):
                continue
            game_name = _normalize_space(option.get_text())
            try:
                sections = json.loads(cls._get_str_attr(option, "data-data", "[]"))
                for key, section_name in sections:
                    section_type, section_id = str(key).split("-", 1)
                    result[f"{game_name}, {_normalize_space(str(section_name))}"] = (section_type, int(section_id))
            except Exception as e:
                logger.debug(f"Не удалось разобрать подкатегории игры {game_name!r}: {e}")
                continue
        return result

    @classmethod
    def _parse_app_user_id(cls, soup: BeautifulSoup) -> str | None:
        """ID владельца сессии из ``body[data-app-data]`` (``userId``)."""
        body = soup.find("body")
        if not isinstance(body, Tag):
            return None
        try:
            app_data = json.loads(cls._get_str_attr(body, "data-app-data", "{}"))
        except ValueError:
            return None
        user_id = app_data.get("userId") if isinstance(app_data, dict) else None
        return str(user_id) if user_id else None

    @classmethod
    def _is_orders_page(cls, soup: BeautifulSoup) -> bool:
        """Страница — таблица продаж или покупок (а не вход, ошибка или чужая вёрстка)."""
        header = soup.select_one("h1.page-header")
        if header is not None:
            # В заголовке бывают кнопки («Выгрузить»), поэтому ищем подстроку.
            text = _normalize_space(header.get_text(" ")).lower()
            if any(title in text for title in _ORDERS_PAGE_TITLES):
                return True
        return (
            soup.find("select", attrs={"name": "game"}) is not None
            or soup.find("form", class_="dyn-table-form") is not None
            or soup.find("input", attrs={"name": "continue"}) is not None
        )

    @classmethod
    def parse_main_menu(cls, html_content: str) -> dict[str, Any]:
        """Парсит funpay.com"""
        soup = BeautifulSoup(html_content, "html.parser")
        user_link = soup.find("a", class_="user-link-dropdown")
        if not user_link and not soup.find("div", class_="user-link-name"):
            # Без блока пользователя FunPay показывает страницу гостю: ссылки на чужие
            # профили на ней есть, но это не мы.
            raise fpx_err.FpxUnauthorizedError("На главной странице нет блока пользователя: FunPay не узнаёт аккаунт")
        if not user_link:
            user_link = soup.find("a", href=lambda h: h and "/users/" in h)
        result: dict[str, Any] = {}
        if user_link:
            href = cls._get_str_attr(user_link, "href")
            user_id = href.strip("/").split("/")[-1] if href else None
            if user_id and user_id.isdigit():
                result["user-id"] = user_id
                name_tag = soup.find("div", class_="user-link-name") or user_link.find("div") or user_link
                result["username"] = cls.clean_text(name_tag) if name_tag else "Unknown"
            else:
                raise fpx_err.FpxParseError(
                    "Не удалось извлечь цифровой ID юзера, возможно слетела сессия или изменилась вёрстка"
                )
        else:
            raise fpx_err.FpxNullDataError("На главной странице не найдено информации о юзере. Возможно слетела сессия")
        body = soup.find("body")
        if not body:
            raise fpx_err.FpxNullDataError("Тело главной страницы (body) не найдено")
        try:
            app_data_str = cls._get_str_attr(body, "data-app-data", "{}")
            app_data = json.loads(app_data_str)
            result["csrf-token"] = app_data.get("csrf-token", "")
        except Exception as e:
            raise fpx_err.FpxParseError("Не удалось распарсить csrf_token из data-app-data.") from e
        return result

    @classmethod
    def parse_transactions(cls, html_content: str) -> TransactionsPage:
        """Парсит историю транзакций с /account/balance или POST /users/transactions."""
        soup = BeautifulSoup(html_content, "html.parser")
        items = soup.find_all("div", class_="tc-item")
        if not items:
            items = soup.find_all("a", class_="tc-item")
        if not items:
            items = soup.find_all(attrs={"data-transaction": True})

        transactions: list[Transaction] = []
        for item in items:
            try:
                parsed = cls._parse_transaction_item(item)
                if parsed is not None:
                    transactions.append(parsed)
            except Exception as e:
                logger.debug(f"Ошибка парсинга отдельной транзакции: {e}. Пропускаем")
                continue

        if items and not transactions:
            raise fpx_err.FpxParseError("При парсинге не найдено ни одной транзакции")

        return TransactionsPage(
            transactions=transactions,
            next_transaction_id=cls._hidden_input_value(soup, "continue"),
            user_id=cls._hidden_input_value(soup, "user_id"),
            filter=cls._hidden_input_value(soup, "filter", allow_empty=True),
        )

    @classmethod
    def _parse_transaction_item(cls, item: Any) -> Transaction | None:
        tx_id = cls._get_str_attr(item, "data-transaction").strip()
        if not tx_id:
            href = cls._get_str_attr(item, "href")
            if "id=" in href:
                tx_id = href.split("id=")[-1].split("&")[0].strip()
        if not tx_id:
            return None

        date_tag = item.find("span", class_="tc-date-time") or item.find("div", class_="tc-date-time")
        title_tag = item.find("span", class_="tc-title") or item.find("div", class_="tc-title")
        price_tag = item.find("div", class_="tc-price") or item.find("span", class_="tc-price")
        status_tag = item.find("div", class_="tc-status") or item.find("span", class_="tc-status")
        number_tag = item.find("span", class_="tc-payment-number") or item.find("div", class_="tc-payment-number")

        description = cls.clean_text(title_tag)
        amount, currency = cls._parse_transaction_amount(cls.clean_text(price_tag))
        classes = " ".join(cls._get_class_list(item))
        withdrawal = cls.clean_text(number_tag) or None

        return Transaction(
            transaction_id=tx_id,
            type=cls._infer_transaction_type(description),
            amount=amount,
            date=cls.clean_text(date_tag),
            description=description,
            status=cls._parse_transaction_status(classes, cls.clean_text(status_tag)),
            currency=currency,
            payment_method=cls._parse_payment_method(item),
            withdrawal_number=withdrawal,
        )

    @classmethod
    def _parse_transaction_amount(cls, raw: str) -> tuple[float, str]:
        currency = ""
        for symbol in ("₽", "$", "€"):
            if symbol in raw:
                currency = symbol
                break
        compact = raw.replace(" ", "")
        match = _AMOUNT_RE.search(compact)
        token = match.group(1) if match else compact
        token = token.replace(",", ".").replace("−", "-").replace("–", "-").replace("—", "-").replace("+", "")
        token = "".join(c for c in token if c.isdigit() or c in ".-")
        try:
            amount = float(token) if token not in ("", "-", ".", "-.") else 0.0
        except ValueError:
            amount = 0.0
        return amount, currency

    @classmethod
    def _infer_transaction_type(cls, description: str) -> str:
        text = description.lower()
        if any(marker in text for marker in _ORDER_TYPE_MARKERS):
            return "order"
        if any(marker in text for marker in _WITHDRAW_TYPE_MARKERS):
            return "withdraw"
        if any(marker in text for marker in _PAYMENT_TYPE_MARKERS):
            return "payment"
        return "other"

    @classmethod
    def _parse_transaction_status(cls, classes: str, status_text: str = "") -> str:
        if "transaction-status-complete" in classes:
            return "completed"
        if "transaction-status-cancel" in classes:
            return "cancelled"
        if "transaction-status-waiting" in classes:
            return "pending"
        text = status_text.lower()
        if any(token in text for token in ("заверш", "complete")):
            return "completed"
        if any(token in text for token in ("отмен", "cancel", "скасов")):
            return "cancelled"
        if any(token in text for token in ("ожид", "wait", "pending", "очік")):
            return "pending"
        return "unknown"

    @classmethod
    def _parse_payment_method(cls, item: Any) -> str | None:
        logo = item.find("span", class_="payment-logo")
        if logo is None:
            logo = item.find(class_=lambda c: c and "payment-method-" in " ".join(c if isinstance(c, list) else [c]))
        if logo is None:
            return None
        classes = " ".join(cls._get_class_list(logo))
        match = _PAYMENT_METHOD_RE.search(classes)
        return match.group(1) if match else None

    @classmethod
    def _hidden_input_value(cls, soup: BeautifulSoup, name: str, *, allow_empty: bool = False) -> str | None:
        tag = soup.find("input", attrs={"name": name})
        if tag is None:
            return None
        value = cls._get_str_attr(tag, "value")
        if allow_empty:
            return value
        stripped = value.strip()
        return stripped or None
