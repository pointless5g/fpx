"""
Тесты таблицы заказов (``parse_my_sells``): продажи /orders/trade и покупки /orders/.

Разметка собрана по селекторам ``FunPayAPI.Account.get_sales`` (``a.tc-item`` с классом статуса,
``div.tc-order``, ``div.order-desc``, ``div.text-muted``, ``div.media-user-name span[data-href]``,
``div.tc-price`` со ``span.unit``, ``div.tc-date-time``, ``select[name=game]`` с ``data-data``,
``input[name=continue]``) и по живой строке продажи из тестов AutoRobux Marketplace.
"""

from datetime import timedelta

import pytest

from fpx._parsers._profile import ProfileParser
from fpx.utils import errors as fpx_err
from fpx.utils.currency import Currency
from fpx.utils.order_status import OrderStatusKind

MY_ID = 2268991

# Так FunPay кодирует data-data у option фильтра игр: JSON в двойных кавычках через &quot;.
GAME_FILTER = """
<select name="game" class="form-control">
  <option value="">Все игры</option>
  <option value="41"
    data-data="[[&quot;lot-1235&quot;,&quot;Донат робуксов (паки)&quot;],[&quot;chip-99&quot;,&quot;Робуксы&quot;]]"
  >Roblox</option>
  <option value="436" data-data='[["lot-210","Аккаунты"]]'>Brawl Stars</option>
</select>
"""


def sale_row(
    order_id: str,
    *,
    row_class: str = "",
    date: str = "сегодня, 1:41",
    desc: str = "80 робуксов",
    subcategory: str = "Roblox, Донат робуксов (паки)",
    buyer: str = "meowchik228",
    buyer_id: int | None = 4747678,
    status: str = "Оплачен",
    price: str = '86.81 <span class="unit">₽</span>',
) -> str:
    href = f' data-href="https://funpay.com/users/{buyer_id}/"' if buyer_id is not None else ""
    return f"""
<a href="https://funpay.com/orders/{order_id}/" class="tc-item {row_class}">
  <div class="tc-date" data-order="{order_id}">
    <div class="tc-date-time">{date}</div>
    <div class="tc-date-left">5 минут назад</div>
  </div>
  <div class="tc-order">#{order_id}</div>
  <div class="order-desc">
    <div>{desc}</div>
    <div class="text-muted">{subcategory}</div>
  </div>
  <div class="tc-user">
    <div class="media media-user offline">
      <div class="media-left"><div class="avatar-photo pseudo-a" tabindex="0"{href}></div></div>
      <div class="media-body">
        <div class="media-user-name"><span class="pseudo-a" tabindex="0"{href}>{buyer}</span></div>
        <div class="media-user-status">был 5 минут назад</div>
      </div>
    </div>
  </div>
  <div class="tc-status text-primary">{status}</div>
  <div class="tc-price text-nowrap tc-seller-sum">{price}</div>
</a>"""


def orders_page(
    rows: str, *, title: str = "Мои продажи", next_page: str | None = "P2CURSOR", filters: bool = True
) -> str:
    continue_form = (
        '<form class="dyn-table-form" action="https://funpay.com/orders/trade" method="post">'
        f'<input type="hidden" name="continue" value="{next_page}"></form>'
        if next_page is not None
        else ""
    )
    return f"""<!DOCTYPE html><html lang="ru"><head><title>{title} / FunPay</title></head>
<body data-app-data='{{"locale":"ru","csrf-token":"tok","userId":{MY_ID}}}'>
<header class="navbar">
  <a class="menu-item" href="https://funpay.com/orders/">Покупки</a>
  <a class="menu-item" href="https://funpay.com/orders/trade">Продажи</a>
  <div class="user-link-name">femtorr</div>
</header>
<div class="page-content-full">
  <h1 class="page-header page-header-no-hr">
    {title}            <button class="btn btn-default pull-right" title="Выгрузить">
        <i class="fa fa-download"></i><span class="hidden-xs"> Выгрузить</span>
    </button>
  </h1>
  <form class="form-inline showcase-filters" action="https://funpay.com/orders/trade" method="get">
    <input type="text" name="id" class="form-control" placeholder="Номер заказа">
    <input type="text" name="buyer" class="form-control" placeholder="Покупатель">
    {GAME_FILTER if filters else ""}
  </form>
  <div class="tc table-hover table-clickable tc-selling showcase-table">
    <div class="tc-header"><div class="tc-date">Дата</div><div class="tc-order">Заказ</div></div>
    {rows}
  </div>
  {continue_form}
</div>
</body></html>"""


def continue_fragment(rows: str, next_page: str | None = None) -> str:
    """Ответ на POST /orders/trade с continue: только строки и форма следующей страницы."""
    form = (
        f'<form class="dyn-table-form"><input type="hidden" name="continue" value="{next_page}"></form>'
        if next_page
        else ""
    )
    return rows + form


def by_id(result: dict) -> dict:
    return {row["order-id"]: row for row in result["sells"]}


class TestSalesRows:
    def test_status_from_row_class(self):
        html = orders_page(
            sale_row("PAID0001", row_class="info", status="Оплачен")
            + sale_row("CLOSED01", status="Закрыт")
            + sale_row("REFUND01", row_class="warning", status="Возврат")
        )
        rows = by_id(ProfileParser.parse_my_sells(html))
        assert rows["PAID0001"]["status-kind"] is OrderStatusKind.PAID
        assert rows["CLOSED01"]["status-kind"] is OrderStatusKind.CLOSED
        assert rows["REFUND01"]["status-kind"] is OrderStatusKind.REFUNDED
        # Подпись FunPay остаётся как была.
        assert rows["REFUND01"]["status"] == "Возврат"

    def test_row_class_wins_over_localized_caption(self):
        """Класс строки не зависит от языка аккаунта, подпись — зависит."""
        html = orders_page(
            sale_row("EN000001", row_class="info", status="Paid")
            + sale_row("EN000002", row_class="warning", status="?")
        )
        rows = by_id(ProfileParser.parse_my_sells(html))
        assert rows["EN000001"]["status-kind"] is OrderStatusKind.PAID
        assert rows["EN000002"]["status-kind"] is OrderStatusKind.REFUNDED

    def test_row_without_class_falls_back_to_caption_then_closed(self):
        html = orders_page(sale_row("NOCLASS1", status="Оплачен") + sale_row("NOCLASS2", status="???"))
        rows = by_id(ProfileParser.parse_my_sells(html))
        assert rows["NOCLASS1"]["status-kind"] is OrderStatusKind.PAID
        assert rows["NOCLASS2"]["status-kind"] is OrderStatusKind.CLOSED

    def test_buyer_id_from_data_href(self):
        row = ProfileParser.parse_my_sells(orders_page(sale_row("SW4J186Q", row_class="info")))["sells"][0]
        assert row["order-id"] == "SW4J186Q"
        assert row["client-name"] == "meowchik228"
        assert row["client-id"] == 4747678

    def test_buyer_without_profile_link_has_no_id(self):
        row = ProfileParser.parse_my_sells(orders_page(sale_row("NOLINK01", buyer_id=None)))["sells"][0]
        assert row["client-name"] == "meowchik228"
        assert row["client-id"] is None

    @pytest.mark.parametrize(
        ("price_html", "price", "currency"),
        [
            ('86.81 <span class="unit">₽</span>', 86.81, Currency.RUB),
            ('1 234.50 <span class="unit">₽</span>', 1234.5, Currency.RUB),
            ('2.35 <span class="unit">$</span>', 2.35, Currency.USD),
            ('1.99 <span class="unit">€</span>', 1.99, Currency.EUR),
            ("99 ₽", 99.0, Currency.RUB),
            ('5 <span class="unit">¤</span>', 5.0, Currency.RUB),
            ('5 <span class="unit">₿</span>', 5.0, Currency.UNKNOWN),
            ("150", 150.0, None),
        ],
    )
    def test_price_and_currency(self, price_html, price, currency):
        row = ProfileParser.parse_my_sells(orders_page(sale_row("PRICE001", price=price_html)))["sells"][0]
        assert row["price"] == pytest.approx(price)
        assert row["currency"] == currency

    def test_subcategory_from_game_filter(self):
        html = orders_page(
            sale_row("LOT00001", subcategory="Roblox, Донат робуксов (паки)")
            + sale_row("CHIP0001", subcategory="Roblox, Робуксы")
            + sale_row("OTHER001", subcategory="Brawl Stars, Аккаунты")
            + sale_row("UNKNOWN1", subcategory="Dota 2, Предметы")
        )
        result = ProfileParser.parse_my_sells(html)
        rows = by_id(result)
        assert (rows["LOT00001"]["subcategory-type"], rows["LOT00001"]["subcategory-id"]) == ("lot", 1235)
        assert (rows["CHIP0001"]["subcategory-type"], rows["CHIP0001"]["subcategory-id"]) == ("chip", 99)
        assert (rows["OTHER001"]["subcategory-type"], rows["OTHER001"]["subcategory-id"]) == ("lot", 210)
        assert rows["UNKNOWN1"]["subcategory-id"] is None
        assert rows["UNKNOWN1"]["subcategory-type"] is None
        assert rows["LOT00001"]["category"] == "Roblox, Донат робуксов (паки)"
        assert result["subcategories"] == {
            "Roblox, Донат робуксов (паки)": ("lot", 1235),
            "Roblox, Робуксы": ("chip", 99),
            "Brawl Stars, Аккаунты": ("lot", 210),
        }

    def test_continue_page_uses_subcategories_from_first_page(self):
        first = ProfileParser.parse_my_sells(orders_page(sale_row("FIRST001")))
        fragment = continue_fragment(sale_row("SECOND01", subcategory="Roblox, Робуксы"))
        without_map = ProfileParser.parse_my_sells(fragment)
        with_map = ProfileParser.parse_my_sells(fragment, subcategories=first["subcategories"])
        assert "subcategories" not in without_map
        assert without_map["sells"][0]["subcategory-id"] is None
        assert with_map["sells"][0]["subcategory-id"] == 99
        assert with_map["sells"][0]["subcategory-type"] == "chip"

    def test_dates_are_moscow_aware(self):
        html = orders_page(
            sale_row("DATE0001", date="12 сентября, 12:00")
            + sale_row("DATE0002", date="5 января 2025, 9:30")
            + sale_row("DATE0003", date="сегодня, 1:41")
            + sale_row("DATE0004", date="Вчера, 23:10")
        )
        rows = by_id(ProfileParser.parse_my_sells(html))
        sept = rows["DATE0001"]["created-at"]
        assert (sept.month, sept.day, sept.hour, sept.minute) == (9, 12, 12, 0)
        assert sept.utcoffset() == timedelta(hours=3)
        jan = rows["DATE0002"]["created-at"]
        assert (jan.year, jan.month, jan.day, jan.hour, jan.minute) == (2025, 1, 5, 9, 30)
        today = rows["DATE0003"]["created-at"]
        assert (today.hour, today.minute) == (1, 41)
        assert today.utcoffset() == timedelta(hours=3)
        yesterday = rows["DATE0004"]["created-at"]
        assert (yesterday.hour, yesterday.minute) == (23, 10)
        assert today.date() - yesterday.date() == timedelta(days=1)
        # Текст как был.
        assert rows["DATE0003"]["order-time"] == "сегодня, 1:41"

    def test_unparsable_date_is_none(self):
        row = ProfileParser.parse_my_sells(orders_page(sale_row("DATE0005", date="12:00")))["sells"][0]
        assert row["created-at"] is None
        assert row["order-time"] == "12:00"

    @pytest.mark.parametrize(
        ("desc", "amount", "topup"),
        [
            ("80 робуксов", 1, None),
            ("Robux, 1 000 шт.", 1000, None),
            ("Robux, 1 000 шт.", 1000, None),
            ("Gold, 12 500 000 шт.", 12500000, None),
            ("Gems, 2 pcs.", 2, None),
            ("Товар 1 000 шт., nickname123", 1000, "nickname123"),
            ("Товар 5 шт., https://example.com/player/1", 5, "https://example.com/player/1"),
            ("Товар 3 шт.", 3, None),
        ],
    )
    def test_amount_with_thousands_separator(self, desc, amount, topup):
        row = ProfileParser.parse_my_sells(orders_page(sale_row("AMOUNT01", desc=desc)))["sells"][0]
        assert row["amount"] == amount
        assert row["topup_data"] == topup
        assert row["name"] == desc

    def test_page_level_cursor_and_user_id(self):
        result = ProfileParser.parse_my_sells(orders_page(sale_row("CURSOR01"), next_page="ZX81NEXT"))
        # Курсор берётся из input[name=continue], а не из первого input формы фильтров.
        assert result["next_page"] == "ZX81NEXT"
        assert result["user-id"] == str(MY_ID)

    def test_last_page_has_no_cursor_key(self):
        result = ProfileParser.parse_my_sells(orders_page(sale_row("LAST0001"), next_page=None))
        assert result.get("next_page") is None


class TestEmptyAndBrokenPages:
    def test_seller_without_sales_gets_empty_list(self):
        result = ProfileParser.parse_my_sells(orders_page("", next_page=None))
        assert result["sells"] == []
        assert result.get("next_page") is None
        assert result["user-id"] == str(MY_ID)

    def test_empty_page_without_filters_is_still_recognized_by_heading(self):
        result = ProfileParser.parse_my_sells(orders_page("", next_page=None, filters=False))
        assert result["sells"] == []

    def test_buyer_without_purchases_gets_empty_list(self):
        result = ProfileParser.parse_my_sells(orders_page("", title="Мои покупки", next_page=None, filters=False))
        assert result["sells"] == []

    def test_navigation_links_are_not_rows(self):
        """Ссылки «/orders/» и «/orders/trade» из шапки не превращаются в строки «Unknown»."""
        result = ProfileParser.parse_my_sells(orders_page("", next_page=None))
        assert all(row["order-id"] != "Unknown" for row in result["sells"])

    def test_unrecognized_page_still_raises(self):
        with pytest.raises(fpx_err.FpxNullDataError):
            ProfileParser.parse_my_sells("<html><body>Вход</body></html>")

    def test_login_page_with_order_nav_links_raises(self):
        html = (
            '<html><body><a href="https://funpay.com/orders/">Покупки</a>'
            '<h1 class="page-header">Вход</h1></body></html>'
        )
        with pytest.raises(fpx_err.FpxNullDataError):
            ProfileParser.parse_my_sells(html)

    def test_fallback_to_order_links_without_tc_item_class(self):
        html = orders_page('<a href="https://funpay.com/orders/ABCD1234/"><div class="tc-order">#ABCD1234</div></a>')
        result = ProfileParser.parse_my_sells(html)
        assert [row["order-id"] for row in result["sells"]] == ["ABCD1234"]


class TestPurchasesTable:
    def test_purchase_row_uses_same_fields(self):
        html = orders_page(
            sale_row(
                "BUY00001", row_class="info", buyer="shop", buyer_id=1234567, price='10 <span class="unit">₽</span>'
            ),
            title="Мои покупки",
        )
        row = ProfileParser.parse_my_sells(html)["sells"][0]
        assert row["client-name"] == "shop"
        assert row["client-id"] == 1234567
        assert row["status-kind"] is OrderStatusKind.PAID
        assert row["currency"] is Currency.RUB
