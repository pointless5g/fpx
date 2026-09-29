# Заказы

Отслеживание заказов, автовыдача, возвраты.

---

## Хендлеры

### `@fp.router.on_orders(mapping=None)`

Все события заказов (оплата, подтверждение, возврат).

⚠️ Не используй вместе с узкими хендлерами — будет дублирование.

```python
from fpx import types


@fp.router.on_orders()
async def any_order(order: types.Order):
    print(f"Заказ {order.order_id}, статус: {order.status}")
```

### `@fp.router.on_new_order(mapping=None)`

Только новые оплаченные заказы.

```python
@fp.router.on_new_order()
async def new_order(order: types.Order):
    print(f"Новый заказ #{order.order_id} от {order.client_name}")
    await order.answer(f'Заказ "{order.name}" принят!')
```

**mapping** — список ключевых слов. Хендлер сработает только если одно из слов есть в описании заказа:

```python
@fp.router.on_new_order(mapping=["ключ", "key"])
async def auto_key(order: types.Order):
    await order.answer("Вот твой ключ: XXX-YYY-ZZZ")
```

### `@fp.router.on_confirmed_orders(mapping=None)`

Только подтверждённые заказы (покупатель нажал "Подтвердить выполнение").

```python
@fp.router.on_confirmed_orders()
async def confirmed(order: types.Order):
    await order.answer("Спасибо за подтверждение! Буду рад отзыву")
```

### `@fp.router.on_refunded_orders(mapping=None)`

Только возвраты.

```python
@fp.router.on_refunded_orders()
async def refunded(order: types.Order):
    print(f"Возврат: {order.order_id}")
```

---

## Объект Order

| Поле | Тип | Описание |
|------|-----|----------|
| `order_id` | `str` | ID заказа |
| `chat_id` | `str` | ID чата |
| `order_time` | `str` | Время заказа |
| `description` | `str` | Описание (что ввёл покупатель) |
| `client_name` | `str` | Ник покупателя |
| `price` | `float` | Цена |
| `amount` | `int` | Количество |
| `status` | `str` | Статус (Оплачен / Paid / Відкрито, Закрыт / Closed / Закрито, Возврат / Refunded / Повернення) |
| `name` | `str` | Название товара |
| `category` | `str` | Категория |
| `review` | `dict` | Отзыв (если есть) |
| `buyer_id` | `int \| None` | ID покупателя |
| `currency` | `Currency \| None` | Валюта цены (`Currency.RUB` / `USD` / `EUR`) |
| `subcategory_id` | `int \| None` | ID подкатегории FunPay |
| `subcategory_type` | `str \| None` | `lot` — обычные лоты, `chip` — игровая валюта |
| `created_at` | `datetime \| None` | Дата заказа по Москве (aware) |
| `status_kind` | `OrderStatusKind \| None` | Статус без привязки к языку: `paid` / `closed` / `refunded` |
| `chat_name` | `str \| None` | Имя чата с покупателем `users-<ID>-<ID>` |

Поля `buyer_id` … `chat_name` заполняет таблица продаж (`get_my_sells`); в хендлеры раннера
они пока не передаются.

### Методы

**`await order.answer(answer_text: str)`** — отправить сообщение в чат заказа. Поддерживает форматирование:
- `{order_id}` — ID заказа
- `{order_time}` — время
- `{client_name}` — ник покупателя
- `{order_name}` — название товара

---

## OrderManager (через account.order)

### `await fp.account.order.get_order_details(order_id)`

Полная информация о заказе со страницы `/orders/{id}/`.

```python
order = await fp.account.order.get_order_details("ABC123")
print(order.status)
print(order.description)
```

### `await fp.account.order.get_order(order_id, locale=None)`

Заказ через JSON API FunPay (`POST /api/orders/get`) — как `get_order` в FunPayAPI.
Возвращает `OrderInfo`: в отличие от `get_order_details`, в нём есть ID покупателя и продавца,
имя чата, подкатегория, валюта, поля оплаченного лота и товары автовыдачи.

```python
info = await fp.account.order.get_order("ABC123")
print(info.status)                # OrderStatusKind.PAID
print(info.buyer_id, info.chat_name)
print(info.sum, info.currency)    # сумма заказа
print(info.amount)                # количество товара
print(info.short_description)
print(info.lot_params)            # [("Способ", "Геймпасс"), ...]
```

`locale` (`ru` / `en` / `uk`) уходит в `Accept-Language` и выбирает язык значений полей.
При любой ошибке — `FpxGetOrderInfoError`, исходная причина в `__cause__`
(`FpxAuthError` на 403, `FpxRequestError` на другой не-200, `FpxParseError` на ответ без `SUCCESS`).

### `await fp.account.order.get_orders(order_ids, locale=None)`

То же для 1–10 заказов одним запросом. Возвращает `dict[str, OrderInfo]`; заказов, которых FunPay
не вернул, в словаре нет. Больше 10 ID — `FpxAttributeError`.

### `await fp.account.order.refund_order(order_id)`

Возврат денег по заказу.

```python
await fp.account.order.refund_order("ABC123")
```

Возвращает `True` если возврат прошёл. При ошибке — `FpxRefundError`.

---

## Альтернативный доступ через `fpx.services`

Те же методы доступны через отдельно объявленный `OrderManager` из `fpx.services`, если хочется явно держать его как отдельную переменную:

```python
from fpx.services import OrderManager

order_mgr = OrderManager(fp.account)
details = await order_mgr.get_order_details("ABC123")
await order_mgr.refund_order("ABC123")
```
