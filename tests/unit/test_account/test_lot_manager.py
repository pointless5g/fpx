"""Тесты LotManager — данные лотов, автовыдача, поднятие, создание, таблица своих лотов, редактор."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from fpx._api._client import FunPayClient
from fpx._parsers import FpxParser
from fpx.classes.account.subclasses.lot import LotManager
from fpx.models.account import Profile
from fpx.models.lots import CurrentLotInfo, LotCreationFields, LotEditor, MyLotRow
from fpx.utils import errors as fpx_err


@pytest.fixture
def account():
    acc = MagicMock()
    acc._client.get_lot_editor_data = AsyncMock()
    acc._client.get_lot_info = AsyncMock()
    acc._client.get_node_editor_data = AsyncMock()
    acc._client.create_lot = AsyncMock()
    acc._client.set_offers_hidden = AsyncMock()
    acc._client.raise_lot = AsyncMock()
    acc._parser.parse_edit_lot_page = MagicMock()
    acc._parser.parse_current_lot_menu = MagicMock()
    acc._parser.parse_create_lot_page = MagicMock()
    acc.profile.get_user_data = AsyncMock()
    acc.profile.profile = AsyncMock()
    acc.addons.get_game_id = AsyncMock()
    acc.data._csrf_token = "tok"
    acc.data.user_id = "42"
    return acc


@pytest.fixture
def manager(account):
    return LotManager(account)


class TestGetLotEditorDetails:
    @pytest.mark.asyncio
    async def test_success_splits_base_and_other_fields(self, manager, account):
        account._client.get_lot_editor_data.return_value = "<html></html>"
        account._parser.parse_edit_lot_page.return_value = {
            "csrf_token": "tok",
            "form_created_at": "ts",
            "offer_id": "1",
            "node_id": "2",
            "location": "",
            "deleted": "",
            "price": "100",
            "amount": "5",
        }
        result = await manager._get_lot_editor_details("1")
        assert isinstance(result, LotEditor)
        assert result.csrf_token == "tok"
        assert result.fields == {"price": "100", "amount": "5"}

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account._client.get_lot_editor_data.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxGetLotEditorInfoError):
            await manager._get_lot_editor_details("1")


class TestGetLotSecrets:
    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        account._client.get_lot_editor_data.return_value = "<html></html>"
        account._parser.parse_edit_lot_page.return_value = {
            "csrf_token": "t",
            "form_created_at": "ts",
            "offer_id": "1",
            "node_id": "2",
            "location": "",
            "deleted": "",
            "secrets": "a\nb",
        }
        result = await manager.get_lot_secrets("1")
        assert result == ["a", "b"]

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account._client.get_lot_editor_data.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxGetLotInfoError):
            await manager.get_lot_secrets("1")


class TestGetLotInfo:
    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        account._client.get_lot_info.return_value = "<html></html>"
        account._parser.parse_current_lot_menu.return_value = {
            "short_desc": "Short",
            "description": "Long",
            "price": "100.5",
        }
        result = await manager.get_lot_info("1")
        assert isinstance(result, CurrentLotInfo)
        assert result.price == 100.5
        assert result._client is account

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account._client.get_lot_info.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxGetLotInfoError):
            await manager.get_lot_info("1")


class TestRaiseLots:
    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        account.data._csrf_token = "tok"
        account.profile.profile.return_value = Profile(category_ids=["1", "2"])
        account.addons.get_game_id.side_effect = ["g1", "g2"]
        account._client.raise_lot.side_effect = ["ok1", "ok2"]
        result = await manager.raise_lots()
        assert result == ["ok1", "ok2"]

    @pytest.mark.asyncio
    async def test_fetches_csrf_token_first_if_missing(self, manager, account):
        account.data._csrf_token = None
        account.profile.profile.return_value = Profile(category_ids=[])
        with pytest.raises(fpx_err.FpxRaisingLotError):
            await manager.raise_lots()
        account.profile.get_user_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_categories_raises(self, manager, account):
        account.profile.profile.return_value = Profile(category_ids=[])
        with pytest.raises(fpx_err.FpxRaisingLotError):
            await manager.raise_lots()

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account.profile.profile.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxRaisingLotError):
            await manager.raise_lots()


class TestGetNodeEditorData:
    @pytest.mark.asyncio
    async def test_success_builds_lot_creation_fields(self, manager, account):
        account._client.get_node_editor_data.return_value = "<html></html>"
        account._parser.parse_create_lot_page.return_value = {
            "csrf_token": "tok",
            "form_created_at": "ts",
            "offer_id": "1",
            "node_id": "2",
            "location": "",
            "deleted": "",
            "fields[type]": [{"Аренда": "1"}, {"Продажа": "2"}],
            "price": [],
        }
        result = await manager.get_node_editor_data("2")
        assert isinstance(result, LotCreationFields)
        assert result._csrf_token == "tok"
        type_field = result.get_field("fields[type]")
        # см. исходный код: key берётся из значений словаря, value - из ключей
        assert type_field.options[0].key == "1"
        assert type_field.options[0].value == "Аренда"
        price_field = result.get_field("price")
        assert price_field.options is None

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account._client.get_node_editor_data.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxGetLotEditorInfoError):
            await manager.get_node_editor_data("2")


class TestCreateLot:
    def _valid_fields(self):
        fields = MagicMock(spec=LotCreationFields)
        fields.validate.return_value = True
        return fields

    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        fields = self._valid_fields()
        response = MagicMock()
        response.status_code = 200
        account._client.create_lot.return_value = response
        result = await manager.create_lot(fields)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_fields_raises(self, manager, account):
        fields = self._valid_fields()
        fields.validate.return_value = False
        with pytest.raises(fpx_err.FpxLotCreateError):
            await manager.create_lot(fields)

    @pytest.mark.asyncio
    async def test_non_200_response_raises(self, manager, account):
        fields = self._valid_fields()
        response = MagicMock()
        response.status_code = 500
        account._client.create_lot.return_value = response
        with pytest.raises(fpx_err.FpxLotCreateError):
            await manager.create_lot(fields)


class TestSetOffersHidden:
    @pytest.mark.asyncio
    async def test_hide_success(self, manager, account):
        response = MagicMock()
        response.status_code = 200
        account._client.set_offers_hidden.return_value = response
        result = await manager.set_offers_hidden(True)
        assert result is True
        account._client.set_offers_hidden.assert_awaited_once_with("42", True)
        account.profile.get_user_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_show_success(self, manager, account):
        response = MagicMock()
        response.status_code = 200
        account._client.set_offers_hidden.return_value = response
        result = await manager.set_offers_hidden(False)
        assert result is True
        account._client.set_offers_hidden.assert_awaited_once_with("42", False)

    @pytest.mark.asyncio
    async def test_non_200_response_raises(self, manager, account):
        response = MagicMock()
        response.status_code = 500
        account._client.set_offers_hidden.return_value = response
        with pytest.raises(fpx_err.FpxLotEditingError):
            await manager.set_offers_hidden(True)

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        account._client.set_offers_hidden.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxLotEditingError):
            await manager.set_offers_hidden(False)


# --- Таблица своих лотов, чтение формы редактора и сохранение (порт FunPayAPI) ---

LOGGED_IN = '<div class="user-link-name">seller</div>'

TRADE_PAGE = f"""<html><body>{LOGGED_IN}
<div class="tc">
<a href="https://funpay.com/lots/offerEdit?node=1331&amp;offer=111" class="tc-item" data-offer="111">
<div class="tc-desc"><div class="tc-desc-text">40 робуксов</div></div>
<div class="tc-amount">5</div>
<div class="tc-price" data-s="45.5"><div>45.50 <span class="unit">₽</span></div></div>
</a>
<a href="https://funpay.com/lots/offerEdit?node=1331&amp;offer=222" class="tc-item warning" data-offer="222">
<div class="tc-desc"><div class="tc-desc-text">80 робуксов</div></div>
<div class="tc-amount">0</div>
<div class="tc-price" data-s="90"><div>90 <span class="unit">₽</span></div><i class="auto-dlv-icon"></i></div>
</a>
</div></body></html>"""


def editor_form(*, active: bool = True, amount: str = "", stored: str = "null") -> str:
    checked = " checked" if active else ""
    return f"""<html><body>{LOGGED_IN}
<form class="form-offer-editor" data-offer="{{&quot;amount&quot;:{stored}}}">
<input type="hidden" name="csrf_token" value="form-tok">
<input type="hidden" name="form_created_at" value="1790000000">
<input type="hidden" name="offer_id" value="111">
<input type="hidden" name="node_id" value="1331">
<input type="hidden" name="location" value="">
<input type="hidden" name="deleted" value="">
<div class="form-group"><select name="fields[quantity]">
<option value="40 робуксов" selected>40 робуксов</option></select></div>
<div class="form-group hidden"><select name="fields[method]"><option value="Группа">Группа</option></select></div>
<input type="text" class="form-control" name="fields[summary][ru]" value="40 робуксов">
<div class="form-group has-feedback"><input type="text" class="form-control" name="price" value="45.5">
<span class="form-control-feedback">₽</span></div>
<input type="text" class="form-control" name="amount" value="{amount}">
<input type="checkbox" name="auto_delivery">
<input type="checkbox" name="active"{checked}>
</form></body></html>"""


def real_parser_account():
    acc = MagicMock()
    acc._parser = FpxParser()
    acc._client.lot_menu_by_category = AsyncMock()
    acc._client.get_lot_editor_data = AsyncMock()
    acc._client.edit_lot = AsyncMock()
    return acc


class TestGetMySubcategoryLots:
    @pytest.mark.asyncio
    async def test_success(self):
        acc = real_parser_account()
        acc._client.lot_menu_by_category.return_value = TRADE_PAGE
        rows = await LotManager(acc).get_my_subcategory_lots(1331)
        acc._client.lot_menu_by_category.assert_awaited_once_with(1331)
        assert all(isinstance(r, MyLotRow) for r in rows)
        assert [(r.offer_id, r.active, r.auto_delivery, r.amount) for r in rows] == [
            ("111", True, False, 5),
            ("222", False, True, 0),
        ]
        assert {r.node_id for r in rows} == {"1331"}

    @pytest.mark.asyncio
    async def test_empty_table(self):
        acc = real_parser_account()
        acc._client.lot_menu_by_category.return_value = f'<html><body>{LOGGED_IN}<div class="tc"></div></body></html>'
        assert await LotManager(acc).get_my_subcategory_lots("1331") == []

    @pytest.mark.asyncio
    async def test_auth_error_passes_through(self):
        acc = real_parser_account()
        acc._client.lot_menu_by_category.return_value = "<html><body>Войти</body></html>"
        with pytest.raises(fpx_err.FpxAuthError):
            await LotManager(acc).get_my_subcategory_lots("1331")

    @pytest.mark.asyncio
    async def test_request_error_wrapped(self):
        acc = real_parser_account()
        acc._client.lot_menu_by_category.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxGetMyLotsError):
            await LotManager(acc).get_my_subcategory_lots("1331")


class TestGetLotFields:
    @pytest.mark.asyncio
    async def test_builds_lot_editor(self):
        acc = real_parser_account()
        acc._client.get_lot_editor_data.return_value = editor_form(amount="5", stored="5")
        lot = await LotManager(acc).get_lot_fields(111)
        acc._client.get_lot_editor_data.assert_awaited_once_with(111)
        assert isinstance(lot, LotEditor)
        assert (lot.csrf_token, lot.offer_id, lot.node_id, lot.form_created_at) == (
            "form-tok",
            "111",
            "1331",
            "1790000000",
        )
        assert "csrf_token" not in lot.fields and "offer_id" not in lot.fields
        assert lot.currency == "RUB"
        assert lot.stored_amount == 5
        assert lot.active is True
        assert lot.auto_delivery is False
        assert lot.amount == 5
        assert lot.price == 45.5
        assert lot.title_ru == "40 робуксов"
        assert lot.subcategory_id == 1331
        assert "fields[method]" not in lot.fields

    @pytest.mark.asyncio
    async def test_sold_out_lot_reads_inactive(self):
        acc = real_parser_account()
        acc._client.get_lot_editor_data.return_value = editor_form(active=True, amount="", stored="0")
        lot = await LotManager(acc).get_lot_fields("111")
        assert lot.stored_amount == 0
        assert lot.active is False
        assert lot.active_checkbox is True

    @pytest.mark.asyncio
    async def test_error_page_raises_lot_not_found_with_id(self):
        acc = real_parser_account()
        acc._client.get_lot_editor_data.return_value = '<html><body><p class="lead">Лот не найден</p></body></html>'
        with pytest.raises(fpx_err.FpxLotNotFoundError) as exc:
            await LotManager(acc).get_lot_fields(111)
        assert exc.value.lot_id == "111"
        assert exc.value.error_message == "Лот не найден"
        assert "111" in exc.value.message

    @pytest.mark.asyncio
    async def test_other_errors_wrapped(self):
        acc = real_parser_account()
        acc._client.get_lot_editor_data.return_value = "<html><body></body></html>"
        with pytest.raises(fpx_err.FpxGetLotEditorInfoError) as exc:
            await LotManager(acc).get_lot_fields(111)
        assert not isinstance(exc.value, fpx_err.FpxLotNotFoundError)

    @pytest.mark.asyncio
    async def test_auth_error_passes_through(self):
        acc = real_parser_account()
        acc._client.get_lot_editor_data.side_effect = fpx_err.FpxAuthError()
        with pytest.raises(fpx_err.FpxAuthError):
            await LotManager(acc).get_lot_fields(111)


def lot_editor(fields=None):
    return LotEditor(
        csrf_token="t",
        form_created_at="ts",
        offer_id="111",
        node_id="1331",
        location="",
        deleted="",
        fields=fields or {},
    )


class TestSaveLot:
    @pytest.mark.asyncio
    async def test_success_returns_none(self):
        acc = real_parser_account()
        acc._client.edit_lot.return_value = httpx.Response(200, json={"done": True})
        lot = lot_editor({"price": "50"})
        assert await LotManager(acc).save_lot(lot) is None
        acc._client.edit_lot.assert_awaited_once_with(lot)

    @pytest.mark.asyncio
    async def test_json_errors_raise_lot_save_error(self):
        acc = real_parser_account()
        acc._client.edit_lot.return_value = httpx.Response(
            200, json={"error": "Проверьте поля", "errors": [["price", "Слишком низкая цена"]]}
        )
        with pytest.raises(fpx_err.FpxLotSaveError) as exc:
            await LotManager(acc).save_lot(lot_editor())
        assert exc.value.lot_id == "111"
        assert exc.value.error_message == "Проверьте поля"
        assert exc.value.errors == {"price": "Слишком низкая цена"}
        assert "Слишком низкая цена" in exc.value.message
        assert isinstance(exc.value, fpx_err.FpxLotEditingError)

    @pytest.mark.asyncio
    async def test_error_without_field_errors(self):
        acc = real_parser_account()
        acc._client.edit_lot.return_value = httpx.Response(200, json={"error": 1, "msg": "Лот удалён"})
        with pytest.raises(fpx_err.FpxLotSaveError) as exc:
            await LotManager(acc).save_lot(lot_editor())
        assert exc.value.error_message == "Лот удалён"
        assert exc.value.errors == {}

    @pytest.mark.asyncio
    async def test_json_errors_on_non_200_still_lot_save_error(self):
        acc = real_parser_account()
        acc._client.edit_lot.return_value = httpx.Response(400, json={"errors": {"amount": "Неверное значение"}})
        with pytest.raises(fpx_err.FpxLotSaveError):
            await LotManager(acc).save_lot(lot_editor())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(502, text="Bad gateway"),
            httpx.Response(200, text="<html></html>"),
            httpx.Response(200, json=[]),
        ],
    )
    async def test_unknown_outcome_raises_request_error(self, response):
        acc = real_parser_account()
        acc._client.edit_lot.return_value = response
        with pytest.raises(fpx_err.FpxRequestError):
            await LotManager(acc).save_lot(lot_editor())

    @pytest.mark.asyncio
    async def test_transport_error_wrapped(self):
        acc = real_parser_account()
        acc._client.edit_lot.side_effect = httpx.ConnectError("down")
        with pytest.raises(fpx_err.FpxRequestError):
            await LotManager(acc).save_lot(lot_editor())


class FakeFunPay:
    """FunPay для сквозного теста: отдаёт форму редактора и запоминает то, что пришло в offerSave."""

    def __init__(self, page: str, save_json: dict) -> None:
        self.page = page
        self.save_json = save_json
        self.saved: list[dict] = []

    async def execute(self, method, url, **kwargs):
        if method == "GET":
            return httpx.Response(200, text=self.page)
        self.saved.append(kwargs["data"])
        return httpx.Response(200, json=self.save_json)


def manager_over(funpay: FakeFunPay) -> LotManager:
    account = MagicMock()
    account._parser = FpxParser()
    account._request_engine.execute = funpay.execute
    account._client = FunPayClient(account, MagicMock())
    return LotManager(account)


class TestReadEditSaveRoundTrip:
    @pytest.mark.asyncio
    async def test_price_change_keeps_other_fields_as_read(self):
        funpay = FakeFunPay(editor_form(active=False, amount=""), {"done": True})
        manager = manager_over(funpay)
        lot = await manager.get_lot_fields(111)
        lot.price = 50.0
        await manager.save_lot(lot)
        (sent,) = funpay.saved
        assert sent["price"] == "50.0"
        assert sent["offer_id"] == "111"
        assert sent["node_id"] == "1331"
        # Снятый чекбокс и пустое «Наличие» (неограниченно) уходят такими, какими пришли.
        assert sent["active"] == ""
        assert sent["amount"] == ""
        assert sent["auto_delivery"] == ""
        assert sent["fields[quantity]"] == "40 робуксов"
        assert "fields[method]" not in sent

    @pytest.mark.asyncio
    async def test_rejected_save_raises_with_field_errors(self):
        funpay = FakeFunPay(editor_form(), {"error": "Ошибка", "errors": [["amount", "Неверное наличие"]]})
        manager = manager_over(funpay)
        lot = await manager.get_lot_fields(111)
        lot.amount = 0
        with pytest.raises(fpx_err.FpxLotSaveError) as exc:
            await manager.save_lot(lot)
        assert funpay.saved[0]["amount"] == "0"
        assert exc.value.errors == {"amount": "Неверное наличие"}
