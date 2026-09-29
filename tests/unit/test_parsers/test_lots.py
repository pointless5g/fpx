"""Тесты LotParser — данные лотов, редактор, поднятие."""

import pytest

from fpx._parsers._lots import LotParser
from fpx.utils import errors as fpx_err


class TestLotParser:
    def test_parse_lot_menu_success(self):
        """Кнопка поднятия с data-game → возвращает ID игры."""
        html = """<button class="js-lot-raise" data-game="42">Поднять</button>"""
        assert LotParser.parse_lot_menu(html) == "42"

    def test_parse_lot_menu_fallback_button(self):
        """Fallback: кнопка без класса, но с data-game."""
        html = """<button data-game="99">Поднять</button>"""
        assert LotParser.parse_lot_menu(html) == "99"

    def test_parse_lot_menu_no_button_raises(self):
        """Нет кнопки → FpxNullDataError."""
        with pytest.raises(fpx_err.FpxNullDataError):
            LotParser.parse_lot_menu("<html><body>Нет кнопки</body></html>")

    def test_parse_current_lot_menu_success(self):
        """Парсинг лота: цена, краткое и подробное описание."""
        html = """
        <html>
          <div class="param-item"><h5>Краткое описание</h5><div>Кратко</div></div>
          <div class="param-item"><h5>Подробное описание</h5><div>Подробно</div></div>
          <option value="21" data-content='<span class="payment-value">100,50</span>'></option>
        </html>
        """
        result = LotParser.parse_current_lot_menu(html)
        assert result["short_desc"] == "Кратко"
        assert result["description"] == "Подробно"
        assert result["price"] == 100.50

    def test_parse_current_lot_menu_no_price_raises(self):
        """Нет опции с ценой → FpxNullDataError."""
        html = """
        <div class="param-item"><h5>Краткое описание</h5><div>Кратко</div></div>
        """
        with pytest.raises(fpx_err.FpxNullDataError):
            LotParser.parse_current_lot_menu(html)

    def test_parse_edit_lot_page_success(self):
        """Парсинг редактора: скрытые поля формы."""
        html = """
        <input type="hidden" name="csrf_token" value="abc123">
        <input type="hidden" name="offer_id" value="999">
        <select><option value="1">Опция</option></select>
        """
        result = LotParser.parse_edit_lot_page(html)
        assert result["csrf_token"] == "abc123"
        assert result["offer_id"] == "999"

    def test_parse_edit_lot_page_reads_checked_checkboxes(self):
        """Отмеченные чекбоксы попадают в поля как "on", снятые не попадают вовсе, как у браузера."""
        html = """
        <form class="form-offer-editor">
          <input type="hidden" name="offer_id" value="42">
          <select name="fields[type]"><option value="1" selected>Робуксы</option></select>
          <input class="form-control" type="text" name="price" value="100">
          <input type="checkbox" name="active" checked>
          <input type="checkbox" name="deactivate_after_sale">
          <input type="checkbox" name="auto_delivery" checked>
        </form>
        """
        result = LotParser.parse_edit_lot_page(html)
        assert result["active"] == "on"
        assert result["auto_delivery"] == "on"
        assert "deactivate_after_sale" not in result
        assert result["price"] == "100"

    @pytest.mark.parametrize("active", [True, False])
    def test_parse_edit_lot_page_real_form_markup(self, active):
        """«Активное» - чекбокс без value: браузер отправляет его как "on",
        а у выключенного лота не отправляет вовсе.
        """
        checked = 'checked=""' if active else ""
        html = f"""
        <form action="https://funpay.com/lots/offerSave" class="form-offer-editor" method="post">
        <input name="csrf_token" type="hidden" value="tok"/>
        <input name="form_created_at" type="hidden" value="1790000000"/>
        <input name="offer_id" type="hidden" value="42"/>
        <input name="node_id" type="hidden" value="1331"/>
        <input name="location" type="hidden" value=""/>
        <input name="deleted" type="hidden" value=""/>
        <div class="form-group lot-field" data-id="quantity"><label class="control-label">Количество робуксов</label>
        <select class="form-control lot-field-input" name="fields[quantity]">
        <option value=""> </option>
        <option value="40 робуксов">40 робуксов</option>
        <option selected="" value="Другое количество">Другое количество</option>
        </select>
        </div>
        <div class="form-group has-feedback w-200px">
        <label class="control-label">Цена за 1 шт.</label>
        <input autocomplete="off" class="form-control" inputmode="decimal" name="price" type="text" value="100"/>
        <span class="form-control-feedback">₽</span>
        </div>
        <div class="form-group">
        <div class="checkbox">
        <label>
        <input {checked} name="active" type="checkbox"/>
        <i></i>
        Активное
        </label>
        </div>
        </div>
        </form>
        """
        result = LotParser.parse_edit_lot_page(html)
        assert result["price"] == "100"
        assert result["fields[quantity]"] == "Другое количество"
        if active:
            assert result["active"] == "on"
        else:
            assert "active" not in result

    def test_parse_edit_lot_page_no_inputs_raises(self):
        """Нет скрытых input → FpxNullDataError."""
        with pytest.raises(fpx_err.FpxNullDataError):
            LotParser.parse_edit_lot_page("<html><body>Пусто</body></html>")

    def test_parse_edit_lot_page_no_selects_raises(self):
        """Есть inputs, но нет select → тоже ошибка."""
        html = """<input type="hidden" name="x" value="y">"""
        with pytest.raises(fpx_err.FpxNullDataError):
            LotParser.parse_edit_lot_page(html)


# --- Таблица своих лотов (/lots/<node>/trade) и форма редактора (порт FunPayAPI) ---

HEADER = """
<header><nav class="navbar"><ul class="nav navbar-nav navbar-right logged"><li class="dropdown">
<a href="https://funpay.com/users/42/" class="dropdown-toggle user-link" data-toggle="dropdown">
<div class="user-link-photo"><img src="/img/layout/avatar.png" alt=""></div>
<div class="user-link-name">seller</div>
</a></li></ul></nav></header>
"""


def trade_page(rows: str, *, logged_in: bool = True) -> str:
    """Страница https://funpay.com/lots/1331/trade с таблицей лотов продавца."""
    return f"""<!DOCTYPE html><html lang="ru">
<body data-app-data='{{"locale":"ru","csrf-token":"tok","userId":42}}'>
<div class="wrapper">{HEADER if logged_in else ""}
<div class="content-with-cd"><div class="container"><div class="page-content">
<div class="tc table-hover table-clickable tc-short showcase-table tc-lazyload" data-section-type="lot">
<div class="tc-header">
<div class="tc-server hidden-xxs">Сервер</div>
<div class="tc-desc">Описание</div>
<div class="tc-amount hidden-xxs">Наличие</div>
<div class="tc-price">Цена</div>
</div>
{rows}
</div></div></div></div></div></body></html>"""


ACTIVE_ROW = """
<a href="https://funpay.com/lots/offerEdit?node=1331&amp;offer=111" class="tc-item" data-offer="111">
<div class="tc-server hidden-xxs">Европа</div>
<div class="tc-desc"><div class="tc-desc-text">40 робуксов, быстро</div></div>
<div class="tc-amount hidden-xxs">1 000</div>
<div class="tc-price" data-s="45.5"><div>45.50 <span class="unit">₽</span></div><i class="auto-dlv-icon"></i></div>
</a>
"""

INACTIVE_ROW = """
<a href="https://funpay.com/lots/offerEdit?node=1331&amp;offer=222" class="tc-item warning" data-offer="222">
<div class="tc-side">Альянс</div>
<div class="tc-desc"><div class="tc-desc-text">80 робуксов</div></div>
<div class="tc-amount hidden-xxs">0</div>
<div class="tc-price" data-s="90"><div>90 <span class="unit">₽</span></div></div>
</a>
"""

NO_AMOUNT_ROW = """
<a href="https://funpay.com/lots/offerEdit?node=1331&amp;offer=333" class="tc-item" data-offer="333">
<div class="tc-desc"><div class="tc-desc-text">400 робуксов</div></div>
<div class="tc-price" data-s="410.25"><div>410.25 <span class="unit">₽</span></div></div>
</a>
"""


class TestParseMyLotsTable:
    def test_rows_active_inactive_currency_auto_delivery(self):
        rows = LotParser.parse_my_lots_table(trade_page(ACTIVE_ROW + INACTIVE_ROW + NO_AMOUNT_ROW), "1331")
        assert [r.offer_id for r in rows] == ["111", "222", "333"]
        active, inactive, no_amount = rows

        assert active.active is True
        assert active.auto_delivery is True
        assert active.price == 45.5
        assert active.currency == "RUB"
        assert active.amount == 1000
        assert active.server == "Европа"
        assert active.side is None
        assert active.description == "40 робуксов, быстро"
        assert active.node_id == "1331"
        assert active.public_link == "https://funpay.com/lots/offer?id=111"
        assert 'data-offer="111"' in active.html

        assert inactive.active is False
        assert inactive.auto_delivery is False
        assert inactive.amount == 0
        assert inactive.server is None
        assert inactive.side == "Альянс"

        assert no_amount.amount is None
        assert no_amount.price == 410.25

    def test_empty_table_returns_empty_list(self):
        assert LotParser.parse_my_lots_table(trade_page(""), "1331") == []

    def test_not_logged_in_raises_auth_error(self):
        with pytest.raises(fpx_err.FpxAuthError):
            LotParser.parse_my_lots_table(trade_page(ACTIVE_ROW, logged_in=False), "1331")

    @pytest.mark.parametrize(("unit", "code"), [("$", "USD"), ("€", "EUR"), ("₽", "RUB"), ("¤", "RUB"), ("?", "")])
    def test_currency_from_unit(self, unit, code):
        row = ACTIVE_ROW.replace('<span class="unit">₽</span>', f'<span class="unit">{unit}</span>')
        (parsed,) = LotParser.parse_my_lots_table(trade_page(row), "1331")
        assert parsed.currency == code

    def test_row_without_data_offer_raises(self):
        row = ACTIVE_ROW.replace(' data-offer="111"', "")
        with pytest.raises(fpx_err.FpxParseError):
            LotParser.parse_my_lots_table(trade_page(row), "1331")

    def test_row_with_broken_price_raises(self):
        row = ACTIVE_ROW.replace('data-s="45.5"', 'data-s=""')
        with pytest.raises(fpx_err.FpxParseError):
            LotParser.parse_my_lots_table(trade_page(row), "1331")


def editor_page(
    *,
    data_offer: str = "{&quot;id&quot;:111,&quot;amount&quot;:7}",
    currency: str = "₽",
    active: bool = True,
    auto_delivery: bool = False,
    secrets: str = "",
    amount: str = "7",
    quantity_selected: bool = True,
) -> str:
    """Страница https://funpay.com/lots/offerEdit?offer=111 с формой редактора."""
    selected = " selected" if quantity_selected else ""
    return f"""<!DOCTYPE html><html lang="ru"><body>
{HEADER}
<form class="navbar-form" action="https://funpay.com/games/promoFilter">
<input type="text" name="query" value="">
<select name="outside"><option value="x">x</option></select>
</form>
<div class="content-with-cd"><div class="container">
<form action="https://funpay.com/lots/offerSave" method="post" class="form-offer-editor" data-offer="{data_offer}">
<input type="hidden" name="csrf_token" value="tok">
<input type="hidden" name="form_created_at" value="1790000000">
<input type="hidden" name="offer_id" value="111">
<input type="hidden" name="node_id" value="1331">
<input type="hidden" name="location" value="">
<input type="hidden" name="deleted" value="">
<div class="form-group lot-field" data-id="quantity">
<label class="control-label">Количество робуксов</label>
<select name="fields[quantity]" class="form-control lot-field-input">
<option value=""> </option>
<option value="40 робуксов"{selected}>40 робуксов</option>
<option value="Другое количество">Другое количество</option>
</select>
</div>
<div class="form-group lot-field hidden" data-id="method">
<label class="control-label">Способ получения</label>
<select name="fields[method]" class="form-control lot-field-input">
<option value="Геймпасс">Геймпасс</option>
<option value="Группа">Группа</option>
</select>
</div>
<div class="form-group lot-field">
<label class="control-label">Краткое описание</label>
<input type="text" class="form-control" name="fields[summary][ru]" value="40 робуксов">
<input type="text" class="form-control" name="fields[summary][en]" value="40 robux">
</div>
<div class="form-group lot-field">
<textarea class="form-control" name="fields[desc][ru]">
Первая строка
Вторая строка</textarea>
<textarea class="form-control" name="fields[desc][en]"></textarea>
</div>
<div class="form-group"><textarea class="form-control" name="fields[payment_msg][ru]">Спасибо!</textarea></div>
<input type="hidden" name="fields[images]" value="101,102">
<div class="form-group has-feedback w-200px">
<label class="control-label">Цена за 1 шт.</label>
<input type="text" class="form-control" name="price" value="45.5" autocomplete="off" inputmode="decimal">
<span class="form-control-feedback">{currency}</span>
</div>
<table class="table table-condensed table-buyers-prices">
<tr><th>Банковская карта</th><td>50.10 ₽</td></tr>
</table>
<div class="form-group"><label class="control-label">Наличие</label>
<input type="text" class="form-control" name="amount" value="{amount}"></div>
<div class="form-group"><div class="checkbox"><label>
<input type="checkbox" name="auto_delivery"{" checked" if auto_delivery else ""}><i></i> Автовыдача</label></div></div>
<div class="form-group"><textarea class="form-control" name="secrets">{secrets}</textarea></div>
<div class="form-group"><div class="checkbox"><label>
<input type="checkbox" name="deactivate_after_sale"><i></i> Деактивировать после продажи</label></div></div>
<div class="form-group"><div class="checkbox"><label>
<input type="checkbox" name="active"{" checked" if active else ""}><i></i> Активное</label></div></div>
</form>
</div></div></body></html>"""


class TestParseLotFields:
    def test_reads_only_the_editor_form(self):
        result = LotParser.parse_lot_fields(editor_page())
        fields = result["fields"]
        assert "query" not in fields
        assert "outside" not in fields
        assert fields["csrf_token"] == "tok"
        assert fields["offer_id"] == "111"
        assert fields["node_id"] == "1331"
        assert fields["fields[summary][ru]"] == "40 робуксов"
        assert fields["price"] == "45.5"
        assert fields["amount"] == "7"
        assert fields["fields[images]"] == "101,102"

    def test_skips_selects_in_hidden_groups(self):
        fields = LotParser.parse_lot_fields(editor_page())["fields"]
        assert fields["fields[quantity]"] == "40 робуксов"
        assert "fields[method]" not in fields

    def test_visible_select_without_selected_option_raises(self):
        """FunPayAPI падает на такой выборке; тихо брать первую опцию нельзя."""
        with pytest.raises(fpx_err.FpxParseError, match=r"fields\[quantity\]"):
            LotParser.parse_lot_fields(editor_page(quantity_selected=False))

    def test_checkboxes_checked_on_unchecked_empty(self):
        fields = LotParser.parse_lot_fields(editor_page(active=True, auto_delivery=False))["fields"]
        assert fields["active"] == "on"
        assert fields["auto_delivery"] == ""
        assert fields["deactivate_after_sale"] == ""
        fields = LotParser.parse_lot_fields(editor_page(active=False, auto_delivery=True))["fields"]
        assert fields["active"] == ""
        assert fields["auto_delivery"] == "on"

    def test_textarea_keeps_text_without_leading_newline(self):
        fields = LotParser.parse_lot_fields(editor_page(secrets="\nkey-1\nkey-2"))["fields"]
        assert fields["fields[desc][ru]"] == "Первая строка\nВторая строка"
        assert fields["fields[desc][en]"] == ""
        assert fields["fields[payment_msg][ru]"] == "Спасибо!"
        assert fields["secrets"] == "key-1\nkey-2"

    @pytest.mark.parametrize(("unit", "code"), [("₽", "RUB"), ("$", "USD"), ("€", "EUR"), ("?", "")])
    def test_currency_from_price_feedback(self, unit, code):
        assert LotParser.parse_lot_fields(editor_page(currency=unit))["currency"] == code

    @pytest.mark.parametrize(
        ("data_offer", "stored"),
        [
            ("{&quot;id&quot;:111,&quot;amount&quot;:7}", 7),
            ("{&quot;id&quot;:111,&quot;amount&quot;:0}", 0),
            ("{&quot;id&quot;:111,&quot;amount&quot;:&quot;3&quot;}", 3),
            ("{&quot;id&quot;:111,&quot;amount&quot;:null}", None),
            ("{&quot;id&quot;:111}", None),
            # Сущности, закодированные дважды: FunPayAPI дополнительно делает html.unescape.
            ("{&amp;quot;amount&amp;quot;:5}", 5),
            ("not json", None),
            ("", None),
        ],
    )
    def test_stored_amount_from_data_offer(self, data_offer, stored):
        assert LotParser.parse_lot_fields(editor_page(data_offer=data_offer))["stored_amount"] == stored

    def test_error_page_raises_lot_not_found(self):
        html = f"""<html><body>{HEADER}<div class="content-with-cd"><div class="container">
        <p class="lead">Предложение не найдено.</p></div></div></body></html>"""
        with pytest.raises(fpx_err.FpxLotNotFoundError) as exc:
            LotParser.parse_lot_fields(html)
        assert exc.value.error_message == "Предложение не найдено."
        assert isinstance(exc.value, fpx_err.FpxGetLotEditorInfoError)

    def test_page_without_form_raises_null_data(self):
        with pytest.raises(fpx_err.FpxNullDataError):
            LotParser.parse_lot_fields(f"<html><body>{HEADER}</body></html>")


class TestParseLotSaveResponse:
    @pytest.mark.parametrize("body", [{"done": True}, {"error": 0, "errors": []}, {"error": False}, None, "ok", []])
    def test_accepted(self, body):
        assert LotParser.parse_lot_save_response(body) is None

    def test_field_errors_as_pairs(self):
        body = {"error": "Проверьте поля", "errors": [["price", "Слишком низкая цена"], ["amount", "Неверно"]]}
        message, errors = LotParser.parse_lot_save_response(body)
        assert message == "Проверьте поля"
        assert errors == {"price": "Слишком низкая цена", "amount": "Неверно"}

    def test_field_errors_as_dict(self):
        message, errors = LotParser.parse_lot_save_response({"errors": {"price": ["Слишком", "низкая"]}})
        assert message is None
        assert errors == {"price": "Слишком; низкая"}

    def test_error_code_with_msg(self):
        message, errors = LotParser.parse_lot_save_response({"error": 1, "msg": "Лот не найден"})
        assert message == "Лот не найден"
        assert errors == {}
