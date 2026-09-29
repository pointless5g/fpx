"""
Тесты разбора JSON API заказов ``POST /api/orders/get`` (``OrderParser.parse_orders_api``).

Форма ответа собрана по ключам, которые читает ``FunPayAPI.Account.__parse_order``:
``order_uid``, ``status``, ``currency``, ``amount``, ``section.{type_id,local_id}``,
``buyer/seller.{user_id,name}``, ``chat.node_name``, ``review.{text,rating,reply,hidden}``,
``type_data.{amount,player,secrets,server,side,fields}``.
"""

import copy

import pytest

from fpx._parsers._orders import OrderParser
from fpx.models.account import OrderField, OrderInfo, OrderReview, OrderServer, OrderSide
from fpx.utils import errors as fpx_err
from fpx.utils.currency import Currency
from fpx.utils.order_status import OrderStatusKind

ORDER = {
    "order_uid": "SW4J186Q",
    "status": "paid",
    "currency": "RUB",
    "amount": "86.81",
    "section": {"type_id": "lot", "local_id": 1235},
    "buyer": {"user_id": 4747678, "name": "meowchik228"},
    "seller": {"user_id": 2268991, "name": "femtorr"},
    "chat": {"node_name": "users-2268991-4747678"},
    "review": {"text": "", "rating": 0, "reply": "", "hidden": False},
    "type_data": {
        "amount": "2.0",
        "player": "RobloxNick",
        "server": {"server_id": 12, "name": "EU"},
        "side": {"side_id": 3, "name": "PC"},
        "fields": {
            "summary": {
                "value": {"ru": "80 робуксов", "en": "80 Robux"},
                "name": "Краткое описание",
                "field_type_id": "text",
            },
            "desc": {
                "value": {"ru": "Выдача через геймпасс", "en": ""},
                "name": "Подробное описание",
                "field_type_id": "textarea",
            },
            "payment_msg": {
                "value": {"ru": "Спасибо за покупку", "en": "Thanks"},
                "name": "Сообщение покупателю",
                "field_type_id": "textarea",
            },
            "f-robux": {"value": "80", "name": "Робуксов", "field_type_id": "number"},
            "f-method": {
                "value": {"ru": "Геймпасс", "en": "Gamepass"},
                "name": "Способ",
                "field_type_id": "select",
            },
        },
        "secrets": [{"value": "KEY-1"}, {"value": "KEY-2"}],
    },
}


def response(*orders: dict) -> dict:
    return {"status": "SUCCESS", "data": {order["order_uid"]: order for order in orders}}


def order(**overrides) -> dict:
    data = copy.deepcopy(ORDER)
    data.update(overrides)
    return data


class TestParseOrdersApi:
    def test_full_order(self):
        result = OrderParser.parse_orders_api(response(ORDER))
        assert list(result) == ["SW4J186Q"]
        info = result["SW4J186Q"]
        assert isinstance(info, OrderInfo)
        assert info.order_id == "SW4J186Q"
        assert info.status is OrderStatusKind.PAID
        assert (info.subcategory_type, info.subcategory_id) == ("lot", 1235)
        assert info.subcategory_name is None
        assert (info.buyer_id, info.buyer_username) == (4747678, "meowchik228")
        assert (info.seller_id, info.seller_username) == (2268991, "femtorr")
        assert info.chat_name == "users-2268991-4747678"
        assert info.sum == pytest.approx(86.81)
        assert info.currency is Currency.RUB
        assert info.amount == 2 and isinstance(info.amount, int)
        assert info.player == info.character_name == "RobloxNick"
        assert info.server == OrderServer(12, "EU")
        assert info.side == OrderSide(3, "PC")
        assert info.order_secrets == ["KEY-1", "KEY-2"]
        assert info.review is None
        assert info.locale == "ru"
        assert info.raw["order_uid"] == "SW4J186Q"
        assert info.fields["f-robux"] == OrderField(id="f-robux", value="80", name="Робуксов", field_type_id="number")

    def test_lot_descriptions_and_params(self):
        info = OrderParser.parse_orders_api(response(ORDER))["SW4J186Q"]
        assert info.short_description == info.title == "80 робуксов"
        assert info.full_description == "Выдача через геймпасс"
        assert info.payment_msg == "Спасибо за покупку"
        assert info.lot_params == [("Робуксов", "80"), ("Способ", "Геймпасс")]
        assert info.lot_params_text == "80 Робуксов, Геймпасс"
        assert info.lot_params_dict == {"Робуксов": "80", "Способ": "Геймпасс"}
        assert info.get_field_value("f-method", "en") == "Gamepass"
        assert info.get_field_value("missing") is None

    def test_english_locale_prefers_english_values_and_falls_back_to_russian(self):
        info = OrderParser.parse_orders_api(response(ORDER), locale="en")["SW4J186Q"]
        assert info.locale == "en"
        assert info.short_description == "80 Robux"
        # Английского подробного описания нет — берётся русское.
        assert info.full_description == "Выдача через геймпасс"

    def test_uk_locale_is_treated_as_russian(self):
        assert OrderParser.parse_orders_api(response(ORDER), locale="uk")["SW4J186Q"].locale == "ru"

    @pytest.mark.parametrize(
        ("raw", "kind"),
        [
            ("unpaid", OrderStatusKind.UNPAID),
            ("paid", OrderStatusKind.PAID),
            ("closed", OrderStatusKind.CLOSED),
            ("refunded", OrderStatusKind.REFUNDED),
            ("partially_refunded", OrderStatusKind.PARTIALLY_REFUNDED),
        ],
    )
    def test_statuses(self, raw, kind):
        assert OrderParser.parse_orders_api(response(order(status=raw)))["SW4J186Q"].status is kind

    def test_unknown_status_raises(self):
        with pytest.raises(fpx_err.FpxParseError, match="disputed"):
            OrderParser.parse_orders_api(response(order(status="disputed")))

    def test_review(self):
        review = {"text": "Всё быстро", "rating": 5, "reply": "Спасибо!", "hidden": True}
        info = OrderParser.parse_orders_api(response(order(review=review)))["SW4J186Q"]
        assert info.review == OrderReview(stars=5, text="Всё быстро", reply="Спасибо!", hidden=True)

    def test_missing_review_is_none(self):
        data = order()
        del data["review"]
        assert OrderParser.parse_orders_api(response(data))["SW4J186Q"].review is None

    def test_chip_order_in_dollars_with_fractional_quantity(self):
        data = order(
            order_uid="#CHIP0001",
            currency="USD",
            amount=12,
            section={"type_id": "chip", "local_id": 99, "name": "Робуксы"},
            type_data={"amount": "2.5"},
        )
        info = OrderParser.parse_orders_api({"status": "SUCCESS", "data": {"CHIP0001": data}})["CHIP0001"]
        assert info.order_id == "CHIP0001"
        assert info.currency is Currency.USD
        assert info.sum == 12.0
        assert (info.subcategory_type, info.subcategory_id, info.subcategory_name) == ("chip", 99, "Робуксы")
        assert info.amount == 2.5
        assert info.player is None and info.server is None and info.side is None
        assert info.fields == {} and info.order_secrets == []
        assert info.short_description is None and info.lot_params == [] and info.lot_params_text is None

    def test_empty_php_containers(self):
        """PHP кодирует пустой словарь как []: fields/type_data могут прийти списком."""
        info = OrderParser.parse_orders_api(response(order(type_data={"fields": [], "secrets": []})))["SW4J186Q"]
        assert info.fields == {} and info.order_secrets == [] and info.amount is None

    def test_several_orders(self):
        result = OrderParser.parse_orders_api(response(ORDER, order(order_uid="SECOND01", status="closed")))
        assert set(result) == {"SW4J186Q", "SECOND01"}
        assert result["SECOND01"].status is OrderStatusKind.CLOSED

    def test_no_orders_found_is_empty(self):
        assert OrderParser.parse_orders_api({"status": "SUCCESS", "data": []}) == {}
        assert OrderParser.parse_orders_api({"status": "SUCCESS", "data": {}}) == {}


class TestParseOrdersApiErrors:
    def test_error_status(self):
        with pytest.raises(fpx_err.FpxParseError, match="Order not found"):
            OrderParser.parse_orders_api({"status": "ERROR", "message": "Order not found"})

    def test_success_without_data(self):
        with pytest.raises(fpx_err.FpxParseError):
            OrderParser.parse_orders_api({"status": "SUCCESS"})

    @pytest.mark.parametrize("payload", [None, [], "<html>", {"status": "SUCCESS", "data": "x"}])
    def test_unexpected_shapes(self, payload):
        with pytest.raises(fpx_err.FpxParseError):
            OrderParser.parse_orders_api(payload)

    @pytest.mark.parametrize("missing", ["buyer", "seller", "chat", "section", "amount", "currency", "order_uid"])
    def test_missing_required_key(self, missing):
        data = order()
        del data[missing]
        with pytest.raises(fpx_err.FpxParseError) as exc:
            OrderParser.parse_orders_api(
                response(data) if missing != "order_uid" else {"status": "SUCCESS", "data": {"X": data}}
            )
        assert isinstance(exc.value.__cause__, KeyError)
