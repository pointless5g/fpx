from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup, Tag

from fpx.models.account import OrderField, OrderInfo, OrderReview, OrderServer, OrderSide
from fpx.utils import errors as fpx_err
from fpx.utils.currency import Currency, parse_currency
from fpx.utils.order_status import OrderStatusKind

from ._base import BaseParser

logger = logging.getLogger("fpx.order_parser")

# Статусы JSON API заказов → OrderStatusKind (как словарь в FunPayAPI.Account.__parse_order).
_API_ORDER_STATUSES = {
    "unpaid": OrderStatusKind.UNPAID,
    "paid": OrderStatusKind.PAID,
    "closed": OrderStatusKind.CLOSED,
    "refunded": OrderStatusKind.REFUNDED,
    "partially_refunded": OrderStatusKind.PARTIALLY_REFUNDED,
}


class OrderParser(BaseParser):
    @classmethod
    def parse_order_page(cls, html_content: str) -> dict[str, Any]:
        """Парсит https://funpay.com/orders/.../"""
        soup = BeautifulSoup(html_content, "html.parser")
        result: dict[str, Any] = {}
        result["review"] = {}
        try:
            languages = ["подробное описание", "detailed description", "докладний опис"]
            # Раньше это было soup.find("h5", string=lambda ...) — совмещение name= и
            # string=<callable> не разрешается перегрузками find() (см. #15), поэтому
            # фильтруем руками по .string, что эквивалентно по поведению.
            desc_h5: Tag | None = None
            for h5 in soup.find_all("h5"):
                text = h5.string
                if text and any(lang in text.lower() for lang in languages):
                    desc_h5 = h5
                    break
            if desc_h5:
                desc_div = desc_h5.find_next(["div", "p", "span"])
                if desc_div:
                    result["desc"] = desc_div.get_text(separator="\n").strip()
            chat_link = soup.select_one("div.chat-float[data-id]")
            if chat_link:
                result["chat_id"] = cls._get_str_attr(chat_link, "data-id")
            else:
                chat_link = soup.select_one('div[data-id][data-name*="users-"]')
                result["chat_id"] = cls._get_str_attr(chat_link, "data-id") if chat_link else None
            header = soup.find("h1", class_="page-header") or soup.find("h1")
            if not header:
                raise fpx_err.FpxNullDataError(
                    "Страница заказа не найдена, возможно, указан неверный ID или слетела сессия."
                )
            spans = header.find_all("span")
            if spans:
                result["status"] = " / ".join([span.get_text(strip=True) for span in spans])
            else:
                full_header_text = header.get_text(separator=" ", strip=True)
                order_langs = ["заказ", "order", "замовлення"]
                if any(word in full_header_text.lower() for word in order_langs):
                    parts = full_header_text.split()
                    idx = next((i for i, part in enumerate(parts) if "#" in part), -1)
                    if idx != -1 and idx + 1 < len(parts):
                        result["status"] = " ".join(parts[idx + 1 :])
                    else:
                        result["status"] = parts[-1] if parts else "Оплачен"
                else:
                    result["status"] = full_header_text or "Оплачен"

            review_container = soup.find("div", class_="review-container")
            if review_container:
                try:
                    text_tag = review_container.find("div", class_="review-item-text") or review_container.find("div")
                    result["review"]["text"] = text_tag.get_text(strip=True) if text_tag else ""
                    raw_stars = cls._get_str_attr(review_container, "data-rating", "0")
                    result["review"]["stars"] = int(raw_stars) if raw_stars.isdigit() else 0
                    answer_div = review_container.find("div", class_="review-item-answer")
                    if answer_div:
                        text_container = answer_div.find("div") or answer_div
                        result["review"]["answer"] = text_container.get_text("\n", strip=True)
                    else:
                        all_divs = review_container.find_all("div", recursive=False)
                        if len(all_divs) > 1:
                            result["review"]["answer"] = all_divs[-1].get_text("\n", strip=True)
                        else:
                            result["review"]["answer"] = ""
                except Exception as e:
                    logger.debug(f"Ошибка парсинга деталей существующего отзыва: {e}")
                    result["review"].update({"text": "", "stars": 0, "answer": ""})
            else:
                result["review"] = {"text": "", "stars": 0, "answer": ""}
        except fpx_err.FpxNullDataError:
            raise
        except fpx_err.FpxParseError:
            raise
        except Exception as e:
            raise fpx_err.FpxParseError(f"Ошибка парсинга страницы заказа: {e}") from e
        return result

    @classmethod
    def parse_category_page(cls, html_content: str) -> list[dict[str, Any]]:
        """Парсит https://funpay.com/lots/.../"""
        soup = BeautifulSoup(html_content, "html.parser")
        lowcoasters: dict[str, dict[str, Any]] = {}
        buttons = soup.select("div.lot-field-radio-box button")
        if not buttons:
            buttons = [btn for btn in soup.find_all("button") if btn.get("value") and btn.get("value") != "Все"]
        filters = [
            value.strip().lower() for btn in buttons if (value := cls._get_str_attr(btn, "value")) and value != "Все"
        ]
        lots = soup.select("a.tc-item:not(.offer-promo)")
        if not lots:
            lots = [
                a
                for a in soup.find_all("a", href=lambda h: h and "/lots/offers/" in h)
                if "promo" not in "".join(cls._get_class_list(a)).lower()
            ]
        if not lots:
            logger.debug("В категории не найдено лотов, возможно их просто нет или страница сломалась")
            return []
        if not filters:
            try:
                lot = lots[0]
                price_div = lot.find("div", class_="tc-price") or lot.find("div", attrs={"data-s": True})
                lot_price = float(cls._get_str_attr(price_div, "data-s", "0")) if price_div else 0.0
                if lot_price in (1.0, 0.0) or not price_div:
                    target_div = price_div or lot
                    raw_text = target_div.get_text(strip=True).replace(",", ".")
                    cleaned = "".join(c for c in raw_text if c.isdigit() or c == ".")
                    lot_price = float(cleaned) if cleaned else 0.0
                username_el = lot.find("span", class_="pseudo-a") or lot.select_one(".media-user-name span")
                owner_username = username_el.get_text(strip=True) if username_el else "Unknown"
                url = cls._get_str_attr(lot, "href")
                offer_id = url.split("=")[-1] if "=" in url else url.rstrip("/").split("/")[-1]
                return [
                    {"filtration": "все", "price": lot_price, "offer_id": offer_id, "owner_username": owner_username}
                ]
            except Exception as e:
                raise fpx_err.FpxParseError("Не удалось распарсить категорию без фильтров.") from e
        for lot in lots:
            lot_f_values = [str(val).strip().lower() for key, val in lot.attrs.items() if key.startswith("data-f-")]
            for f in filters:
                if f in lot_f_values:
                    try:
                        price_div = lot.find("div", class_="tc-price") or lot.find("div", attrs={"data-s": True})
                        lot_price = float(cls._get_str_attr(price_div, "data-s", "0")) if price_div else 0.0
                        if lot_price in (1.0, 0.0) or not price_div:
                            target_div = price_div or lot
                            raw_text = target_div.get_text(strip=True).replace(",", ".")
                            cleaned = "".join(c for c in raw_text if c.isdigit() or c == ".")
                            lot_price = float(cleaned) if cleaned else 0.0
                        if f not in lowcoasters or lot_price < lowcoasters[f]["price"]:
                            username_el = lot.find("span", class_="pseudo-a") or lot.select_one(".media-user-name span")
                            owner_username = username_el.get_text(strip=True) if username_el else "Unknown"
                            url = cls._get_str_attr(lot, "href")
                            offer_id = url.split("=")[-1] if "=" in url else url
                            lowcoasters[f] = {
                                "filtration": f,
                                "price": lot_price,
                                "offer_id": offer_id,
                                "owner_username": owner_username,
                            }
                    except Exception:
                        logger.debug("При парсинге конкретного лота в категории что-то пошло не так")
                        continue
        return list(lowcoasters.values())

    @classmethod
    def parse_orders_api(cls, payload: Any, locale: str = "ru") -> dict[str, OrderInfo]:
        """
        Разбирает ответ ``POST https://funpay.com/api/orders/get``.

        Перенос ``FunPayAPI.Account.get_orders_by_ids`` + ``__parse_order``: ответ без
        ``"status": "SUCCESS"`` или без ``data`` — ошибка, каждый заказ из ``data`` → ``OrderInfo``.

        Args:
            payload: JSON ответа.
            locale: Язык запроса (``Accept-Language``), от него зависит язык полей по умолчанию.
        Returns:
            dict[str, OrderInfo]: заказы по ID в том виде, в каком их вернул FunPay.
        Raises:
            FpxParseError: FunPay ответил ошибкой или заказ не удалось разобрать.
        """
        if not isinstance(payload, dict):
            raise fpx_err.FpxParseError(f"API заказов вернуло не JSON-объект: {type(payload).__name__}")
        data = payload.get("data")
        if payload.get("status") != "SUCCESS" or data is None:
            raise fpx_err.FpxParseError(f"API заказов вернуло ошибку: {cls._describe_api_error(payload)}")
        if isinstance(data, list) and not data:
            # PHP отдаёт пустой словарь как [] — FunPay не нашёл ни одного заказа.
            return {}
        if not isinstance(data, dict):
            raise fpx_err.FpxParseError(f"API заказов вернуло data неожиданного типа: {type(data).__name__}")
        return {str(order_id): cls.parse_order_api_item(item, locale) for order_id, item in data.items()}

    @classmethod
    def parse_order_api_item(cls, order_data: Any, locale: str = "ru") -> OrderInfo:
        """Один заказ из ``data`` ответа ``/api/orders/get`` (``FunPayAPI.Account.__parse_order``)."""
        try:
            status_raw = order_data["status"]
            status = _API_ORDER_STATUSES.get(status_raw)
            if status is None:
                raise fpx_err.FpxParseError(f"Неизвестный статус заказа в API: {status_raw!r}")
            section = order_data["section"]
            buyer = order_data["buyer"]
            seller = order_data["seller"]
            type_data = order_data.get("type_data") or {}
            server = type_data.get("server")
            side = type_data.get("side")
            raw_fields = type_data.get("fields")
            review_data = order_data.get("review")
            review = None
            if isinstance(review_data, dict):
                text, rating, reply = review_data.get("text"), review_data.get("rating"), review_data.get("reply")
                # Пустой объект отзыва FunPay шлёт и для заказов без отзыва.
                if text or rating or reply:
                    review = OrderReview(
                        stars=int(rating) if rating else None,
                        text=text,
                        reply=reply,
                        hidden=bool(review_data.get("hidden")),
                    )
            order_id = str(order_data["order_uid"])
            return OrderInfo(
                order_id=order_id[1:] if order_id.startswith("#") else order_id,
                status=status,
                buyer_id=int(buyer["user_id"]),
                seller_id=int(seller["user_id"]),
                chat_name=str(order_data["chat"]["node_name"]),
                sum=float(order_data["amount"]),
                currency=parse_currency(str(order_data["currency"])) or Currency.UNKNOWN,
                subcategory_id=int(section["local_id"]),
                subcategory_type=str(section["type_id"]),
                subcategory_name=section.get("name"),
                buyer_username=buyer.get("name"),
                seller_username=seller.get("name"),
                amount=cls._api_quantity(type_data.get("amount")),
                player=type_data.get("player") or None,
                server=OrderServer(int(server["server_id"]), server.get("name")) if server else None,
                side=OrderSide(int(side["side_id"]), side.get("name")) if side else None,
                fields={
                    str(key): OrderField(
                        id=str(key),
                        value=value.get("value"),
                        name=value.get("name"),
                        field_type_id=value.get("field_type_id"),
                    )
                    for key, value in (raw_fields.items() if isinstance(raw_fields, dict) else ())
                },
                order_secrets=[
                    str(secret["value"]) if isinstance(secret, dict) else str(secret)
                    for secret in (type_data.get("secrets") or [])
                ],
                review=review,
                locale="en" if locale == "en" else "ru",
                raw=order_data,
            )
        except fpx_err.FpxParseError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise fpx_err.FpxParseError(f"Не удалось разобрать заказ из API: {e!r}") from e

    @staticmethod
    def _api_quantity(raw: Any) -> int | float | None:
        """Количество из ``type_data.amount``: ``"2.0"`` → 2, ``"0.5"`` → 0.5, пусто → None."""
        if not raw:
            return None
        quantity = float(raw)
        return int(quantity) if quantity.is_integer() else quantity

    @staticmethod
    def _describe_api_error(payload: dict[str, Any]) -> str:
        details = [f"status={payload.get('status')!r}"]
        for key in ("error", "message", "msg"):
            if payload.get(key):
                details.append(f"{key}={payload[key]!r}")
        return ", ".join(details)
