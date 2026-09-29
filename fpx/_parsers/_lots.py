from __future__ import annotations

import html as html_lib
import json
import logging
from typing import Any

from bs4 import BeautifulSoup, Tag

from fpx.models.lots import MyLotRow
from fpx.utils import errors as fpx_err

from ._base import BaseParser

logger = logging.getLogger("fpx.lot_parser")

# Как FunPayAPI (common/utils.py, CURRENCY_MAP) переводит подпись валюты в валюту.
_CURRENCY_CODES = {
    "RUB": "RUB",
    "EUR": "EUR",
    "USD": "USD",
    "₽": "RUB",
    "€": "EUR",
    "$": "USD",
    "¤": "RUB",
}


class LotParser(BaseParser):
    @staticmethod
    def _parse_currency(text: str) -> str:
        """Код валюты ("RUB", "USD", "EUR") по подписи FunPay; "" — неизвестная валюта."""
        return _CURRENCY_CODES.get(text.strip(), "")

    @staticmethod
    def _optional_text(tag: Any) -> str | None:
        return tag.get_text().strip() if isinstance(tag, Tag) else None

    @classmethod
    def parse_my_lots_table(cls, html_content: str, node_id: str = "") -> list[MyLotRow]:
        """
        Парсит таблицу своих лотов подкатегории: https://funpay.com/lots/<node>/trade.
        Порт ``Account.get_my_subcategory_lots`` из FunPayAPI.

        Raises:
            FpxAuthError: на странице нет имени пользователя (сессия не авторизована).
            FpxParseError: у строки нет ID лота или цены.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        if soup.find("div", class_="user-link-name") is None:
            raise fpx_err.FpxAuthError("На странице своих лотов нет имени пользователя: сессия не авторизована.")
        rows: list[MyLotRow] = []
        # FunPayAPI берёт валюту из первой строки; здесь — из каждой строки с подписью.
        currency = ""
        for offer in soup.find_all("a", class_="tc-item"):
            offer_id = cls._get_str_attr(offer, "data-offer").strip()
            if not offer_id:
                raise fpx_err.FpxParseError("У строки таблицы своих лотов нет атрибута data-offer.")
            price_tag = cls._as_tag(offer.find("div", class_="tc-price"), f"У лота {offer_id} не найдена цена.")
            raw_price = cls._get_str_attr(price_tag, "data-s")
            try:
                price = float(raw_price)
            except ValueError as e:
                raise fpx_err.FpxParseError(f"У лота {offer_id} цена data-s не число: {raw_price!r}") from e
            unit = price_tag.find("span", class_="unit")
            if isinstance(unit, Tag):
                currency = cls._parse_currency(unit.get_text())
            amount_tag = offer.find("div", class_="tc-amount")
            # FunPay разделяет разряды пробелами ("1 000"), в том числе неразрывными.
            amount_text = "".join(amount_tag.get_text().split()) if isinstance(amount_tag, Tag) else ""
            rows.append(
                MyLotRow(
                    offer_id=offer_id,
                    node_id=str(node_id),
                    description=cls._optional_text(offer.find("div", class_="tc-desc-text")),
                    server=cls._optional_text(offer.find("div", class_="tc-server")),
                    side=cls._optional_text(offer.find("div", class_="tc-side")),
                    amount=int(amount_text) if amount_text.isdecimal() else None,
                    price=price,
                    currency=currency,
                    auto_delivery=price_tag.find("i", class_="auto-dlv-icon") is not None,
                    active="warning" not in cls._get_class_list(offer),
                    html=str(offer),
                )
            )
        return rows

    @staticmethod
    def _parse_stored_amount(raw: str) -> int | None:
        """Наличие из JSON в data-offer формы редактора; None — нет данных."""
        if not raw:
            return None
        # bs4 уже раскодировал сущности атрибута; FunPayAPI раскодирует ещё раз — пробуем оба варианта.
        for candidate in (raw, html_lib.unescape(raw)):
            try:
                data = json.loads(candidate)
            except ValueError:
                continue
            break
        else:
            return None
        if not isinstance(data, dict):
            return None
        amount = data.get("amount")
        if isinstance(amount, bool):
            return None
        if isinstance(amount, int):
            return amount
        if isinstance(amount, float) and amount.is_integer():
            return int(amount)
        if isinstance(amount, str) and amount.strip().isdecimal():
            return int(amount.strip())
        return None

    @classmethod
    def parse_lot_fields(cls, html_content: str) -> dict[str, Any]:
        """
        Парсит форму редактора лота https://funpay.com/lots/offerEdit?offer=...
        Порт ``Account.get_lot_fields`` из FunPayAPI: читается только
        ``form.form-offer-editor``, выборки в скрытых ``form-group`` пропускаются,
        снятые чекбоксы попадают в поля пустой строкой, отмеченные — "on".

        Returns:
            dict:
                - fields (dict[str, str]): все поля формы, включая csrf_token, offer_id, node_id.
                - currency (str): код валюты из подписи у цены ("" — неизвестна).
                - stored_amount (int | None): наличие из data-offer формы.
        Raises:
            FpxLotNotFoundError: FunPay отдал страницу ошибки (``p.lead``).
            FpxNullDataError: на странице нет формы редактора.
            FpxParseError: у видимой выборки не отмечено ни одной опции.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        lead = soup.find("p", class_="lead")
        if isinstance(lead, Tag):
            text = lead.get_text().strip()
            raise fpx_err.FpxLotNotFoundError(f"FunPay не открыл редактор лота: {text}", error_message=text)
        form = soup.find("form", class_="form-offer-editor")
        if not isinstance(form, Tag):
            raise fpx_err.FpxNullDataError(
                "На странице не найдена форма редактора лота (form-offer-editor). Возможно слетела сессия"
            )
        fields: dict[str, str] = {}
        checked: list[str] = []
        for tag in form.find_all("input"):
            name = cls._get_str_attr(tag, "name")
            if not name:
                continue
            input_type = cls._get_str_attr(tag, "type").lower()
            if input_type == "checkbox":
                fields[name] = ""
                if tag.has_attr("checked"):
                    checked.append(name)
                continue
            if input_type == "radio" and not tag.has_attr("checked"):
                continue
            fields[name] = cls._get_str_attr(tag, "value")
        for tag in form.find_all("textarea"):
            name = cls._get_str_attr(tag, "name")
            if not name:
                continue
            text = tag.get_text()
            # Браузер отбрасывает один перевод строки сразу после <textarea>; html.parser — нет.
            if text.startswith("\r\n"):
                text = text[2:]
            elif text.startswith("\n"):
                text = text[1:]
            fields[name] = text
        for tag in form.find_all("select"):
            name = cls._get_str_attr(tag, "name")
            if not name:
                continue
            group = tag.find_parent(class_="form-group")
            if isinstance(group, Tag) and "hidden" in cls._get_class_list(group):
                continue
            selected = tag.find("option", selected=True)
            if not isinstance(selected, Tag):
                raise fpx_err.FpxParseError(f"В редакторе лота у выборки {name} не отмечено ни одной опции.")
            if selected.has_attr("value"):
                fields[name] = cls._get_str_attr(selected, "value")
            else:
                fields[name] = selected.get_text().strip()
        for name in checked:
            fields[name] = "on"
        feedback = form.find("span", class_="form-control-feedback")
        return {
            "fields": fields,
            "currency": cls._parse_currency(feedback.get_text()) if isinstance(feedback, Tag) else "",
            "stored_amount": cls._parse_stored_amount(cls._get_str_attr(form, "data-offer")),
        }

    @staticmethod
    def _error_text(value: Any) -> str:
        if isinstance(value, (list, tuple)):
            return "; ".join(str(i) for i in value)
        return str(value)

    @classmethod
    def parse_lot_save_response(cls, body: Any) -> tuple[str | None, dict[str, str]] | None:
        """
        Разбирает JSON-ответ ``POST /lots/offerSave`` так же, как ``save_offer`` в FunPayAPI:
        отказ — это непустой ``error`` или ``errors``.

        Returns:
            None, если FunPay принял сохранение; иначе (текст ошибки или None,
            ошибки по полям ``{имя поля: текст}``).
        """
        if not isinstance(body, dict):
            return None
        error = body.get("error")
        raw_errors = body.get("errors")
        if not error and not raw_errors:
            return None
        errors: dict[str, str] = {}
        if isinstance(raw_errors, dict):
            errors = {str(k): cls._error_text(v) for k, v in raw_errors.items()}
        elif isinstance(raw_errors, (list, tuple)):
            # FunPayAPI ожидает список пар [поле, текст].
            for i, item in enumerate(raw_errors):
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    errors[str(item[0])] = cls._error_text(item[1])
                else:
                    errors[str(i)] = cls._error_text(item)
        elif raw_errors:
            errors[""] = cls._error_text(raw_errors)
        msg = body.get("msg")
        message: str | None = None
        if isinstance(error, str) and error.strip():
            message = error.strip()
        elif isinstance(msg, str) and msg.strip():
            message = msg.strip()
        elif error and not isinstance(error, bool):
            message = str(error)
        return message, errors

    @classmethod
    def parse_lot_menu(cls, html_content: str) -> str:
        """Парсит страницу pay.com/lots/.../trade"""
        soup = BeautifulSoup(html_content, "html.parser")
        button = soup.find("button", class_="js-lot-raise")
        if not button:
            button = soup.find("button", attrs={"data-game": True})
        if button:
            data_game = cls._get_str_attr(button, "data-game")
            if data_game:
                return data_game
            raise fpx_err.FpxParseError("Атрибут data-game не найден внутри кнопки поднятия")
        raise fpx_err.FpxNullDataError(
            "На странице лотов не найдена кнопка для поднятия.Возможно у вас нет созданных лотов в этой категории"
        )

    @classmethod
    def parse_current_lot_menu(cls, html_content: str) -> dict[str, Any]:
        """https://funpay.com/lots/offer?id=..."""
        result: dict[str, Any] = {}
        soup = BeautifulSoup(html_content, "html.parser")
        param_items: list[Tag] = soup.find_all("div", class_="param-item")
        if not param_items:
            param_items = [parent for h5 in soup.find_all("h5") if (parent := h5.find_parent("div")) is not None]
        if not param_items:
            raise fpx_err.FpxNullDataError(
                "Страница лота не найдена. Возможно, указана инвалидная ссылка или лот был удалён."
            )
        descriptions: dict[str, str] = {}
        for item in param_items:
            try:
                header_tag = item.find(["h5", "h4", "label"])
                content_tag = item.find("div") or item.find("textarea")
                if header_tag and content_tag:
                    header = header_tag.get_text(strip=True)
                    text = content_tag.get_text(separator="\n", strip=True)
                    descriptions[header] = text
            except Exception as e:
                logger.debug(f"При парсинге конкретного объекта произошла ошибка: {e}")
        result["short_desc"] = (
            descriptions.get("Краткое описание")
            or descriptions.get("Short description")
            or descriptions.get("Короткий опис")
        )
        result["description"] = (
            descriptions.get("Подробное описание")
            or descriptions.get("Detailed description")
            or descriptions.get("Докладний опис")
        )
        option = soup.find("option", value="21") or soup.find("option", attrs={"data-content": True})
        if option:
            inner_html = cls._get_str_attr(option, "data-content")
            if inner_html:
                inner_soup = BeautifulSoup(inner_html, "html.parser")
                price_span = inner_soup.find("span", class_="payment-value")
                raw_price = price_span.get_text(strip=True) if price_span else inner_soup.get_text(strip=True)
                raw_price = raw_price.replace(",", ".")
                cleaned_price = "".join(c for c in raw_price if c.isdigit() or c == ".")
                try:
                    result["price"] = float(cleaned_price) if cleaned_price else 0.0
                except ValueError:
                    result["price"] = 0.0
                return result
        raise fpx_err.FpxNullDataError("Не удалось найти цену в скрытых атрибутах выбора оплаты.")

    @classmethod
    def parse_edit_lot_page(cls, html_content: str) -> dict[str, Any]:
        """https://funpay.com/lots/offerEdit?node=...&offer=..."""
        soup = BeautifulSoup(html_content, "html.parser")
        hidden_inputs = soup.find_all("input", type="hidden")
        if not hidden_inputs:
            raise fpx_err.FpxNullDataError("Не найдено вводных данных в редакторе лота. Возможно слетела сессия")
        result: dict[str, Any] = {
            name: cls._get_str_attr(tag, "value") for tag in hidden_inputs if (name := cls._get_str_attr(tag, "name"))
        }
        selects = soup.find_all("select")
        if not selects:
            raise fpx_err.FpxNullDataError(
                "Ни одна выборка в редакторе лотов не найдена. Проверьте актуальность сессии"
            )
        for s in selects:
            try:
                name = cls._get_str_attr(s, "name")
                if not name:
                    continue
                selected_option = s.find("option", selected=True)
                if selected_option:
                    result[name] = cls._get_str_attr(selected_option, "value")
                else:
                    first_opt = s.find("option")
                    result[name] = cls._get_str_attr(first_opt, "value") if first_opt else ""
            except Exception as e:
                logger.debug(f"При парсинге конкретной выборки произошла ошибка: {e}")
        inputs: list[Tag] = soup.find_all("input", class_="form-control")
        if not inputs:
            inputs = [
                i
                for i in soup.find_all("input")
                if cls._get_str_attr(i, "name")
                and i.get("type") in ["text", "number", None]
                and i.get("type") != "hidden"
            ]
        if not inputs:
            logger.debug("Ни одно поле для ввода в редакторе лотов не найдено. Возможно всё в порядке")
        else:
            for i in inputs:
                try:
                    name = cls._get_str_attr(i, "name")
                    if name:
                        result[name] = cls._get_str_attr(i, "value")
                except Exception as e:
                    logger.debug(f"При парсинге конкретного поля для ввода произошла ошибка: {e}")
        textareas = soup.find_all("textarea")
        if not textareas:
            logger.debug("При парсинге редактора лотов не найдено ни одного текстового поля. Возможно всё в порядке")
        else:
            for t in textareas:
                try:
                    name = cls._get_str_attr(t, "name")
                    if name:
                        result[name] = t.get_text().strip()
                except Exception as e:
                    logger.debug(f"При парсинге конкретного текстового поля произошла ошибка: {e}")
        # Чекбоксы («Активное», «Автовыдача», «Деактивировать после продажи»)
        form = soup.select_one("form.form-offer-editor") or soup
        for checkbox in form.find_all("input", attrs={"type": "checkbox"}):
            name = cls._get_str_attr(checkbox, "name")
            if name and checkbox.has_attr("checked"):
                result[name] = cls._get_str_attr(checkbox, "value") or "on"
        return result

    @classmethod
    def parse_create_lot_page(cls, html_content: str) -> dict[str, Any]:
        """https://funpay.com/lots/offerEdit?node=..."""
        soup = BeautifulSoup(html_content, "html.parser")
        hidden_inputs = soup.find_all("input", type="hidden")
        if not hidden_inputs:
            raise fpx_err.FpxNullDataError("Не найдено вводных данных в редакторе лота. Возможно слетела сессия")
        result: dict[str, Any] = {
            name: cls._get_str_attr(tag, "value") for tag in hidden_inputs if (name := cls._get_str_attr(tag, "name"))
        }
        selects = soup.find_all("select")
        if not selects:
            raise fpx_err.FpxNullDataError(
                "Ни одна выборка в редакторе лотов не найдена. Проверьте актуальность сессии"
            )
        for s in selects:
            try:
                name = cls._get_str_attr(s, "name")
                options = s.find_all("option")
                value_list: list[dict[str, str]] = []
                for option in options:
                    value_name = option.get_text(strip=True)
                    value = cls._get_str_attr(option, "value")
                    if value_name and value:
                        value_list.append({value_name: value})
                result[name] = value_list
            except Exception as e:
                logger.debug(f"При парсинге конкретной выборки произошла ошибка: {e}")
        inputs: list[Tag] = soup.find_all("input", class_="form-control")
        if not inputs:
            inputs = [
                i
                for i in soup.find_all("input")
                if cls._get_str_attr(i, "name")
                and i.get("type") in ["text", "number", None]
                and i.get("type") != "hidden"
            ]
        if not inputs:
            logger.debug("Ни одно поле для ввода в редакторе лотов не найдено. Возможно всё в порядке")
        else:
            for i in inputs:
                try:
                    name = cls._get_str_attr(i, "name")
                    if name:
                        result[name] = cls._get_str_attr(i, "value")
                except Exception as e:
                    logger.debug(f"При парсинге конкретного поля для ввода произошла ошибка: {e}")
        textareas = soup.find_all("textarea")
        if not textareas:
            logger.debug("При парсинге редактора лотов не найдено ни одного текстового поля. Возможно всё в порядке")
        else:
            for t in textareas:
                try:
                    name = cls._get_str_attr(t, "name")
                    if name:
                        result[name] = t.get_text().strip()
                except Exception as e:
                    logger.debug(f"При парсинге конкретного текстового поля произошла ошибка: {e}")
        return result
