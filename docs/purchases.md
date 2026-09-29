# Покупки

Отслеживание покупок, которые совершает сам аккаунт (как покупатель).

!!! note "Братский класс `Order`"
    `Purchase` — «братский» класс `Order` (см. [Заказы](orders.md)): те же поля, тот же
    жизненный цикл статусов и тот же принцип работы хендлеров и `PurchaseManager`/`OrderManager`.
    Разница только в направлении: `Order` — это то, что купили **у вас**, `Purchase` — то,
    что **вы сами купили**. Если знаком с заказами — с покупками разберёшься по аналогии.

---

## Хендлеры

### `@fp.router.on_purchases(mapping=None)`

Все события покупок (оплата, подтверждение, возврат).

⚠️ Не используй вместе с узкими хендлерами — будет дублирование.

```python
from fpx import types


@fp.router.on_purchases()
async def any_purchase(order: types.Purchase):
    print(f"Покупка {order.order_id}, статус: {order.status}")
```

### `@fp.router.on_new_purchase(mapping=None)`

Только новые оплаченные покупки.

```python
@fp.router.on_new_purchase()
async def new_purchase(order: types.Purchase):
    print(f"Новая покупка #{order.order_id} у {order.client_name}")
    await order.answer("Оплатил, жду выполнения!")
```

**mapping** — список ключевых слов. Хендлер сработает только если одно из слов есть в описании покупки:

```python
@fp.router.on_new_purchase(mapping=["ключ", "key"])
async def auto_reply(order: types.Purchase):
    await order.answer("Спасибо, ожидаю ключ")
```

### `@fp.router.on_confirmed_purchases(mapping=None)`

Только подтверждённые покупки (вы нажали "Подтвердить выполнение").

```python
@fp.router.on_confirmed_purchases()
async def confirmed(order: types.Purchase):
    print(f"Покупка {order.order_id} подтверждена")
```

### `@fp.router.on_refunded_purchase(mapping=None)`

Только возвраты по покупкам.

```python
@fp.router.on_refunded_purchase()
async def refunded(order: types.Purchase):
    print(f"Возврат по покупке: {order.order_id}")
```

---

## Объект Purchase

Поля совпадают с [`Order`](orders.md#объект-order), кроме ID собеседника:

| Поле | Тип | Описание |
|------|-----|----------|
| `order_id` | `str` | ID заказа |
| `chat_id` | `str` | ID чата |
| `order_time` | `str` | Время заказа |
| `description` | `str` | Описание (что ввёл покупатель, т.е. вы) |
| `client_name` | `str` | Ник продавца |
| `price` | `float` | Цена |
| `amount` | `int` | Количество |
| `status` | `str` | Статус (Оплачен, Закрыт, Возврат) |
| `name` | `str` | Название товара |
| `category` | `str` | Категория |
| `review` | `dict` | Отзыв (если есть) |
| `seller_id` | `int \| None` | ID продавца |
| `currency`, `subcategory_id`, `subcategory_type`, `created_at`, `status_kind`, `chat_name` | | Как у [`Order`](orders.md#объект-order), `chat_name` — чат с продавцом |

Вместо `buyer_id` у покупки `seller_id`. Эти поля заполняет `get_my_purchases`.

### Методы

**`await order.answer(answer_text: str)`** — отправить сообщение в чат покупки. Поддерживает форматирование:
- `{order_id}` — ID заказа
- `{order_time}` — время
- `{client_name}` — ник продавца
- `{order_name}` — название товара

В отличие от `Order`, у `Purchase` нет метода `.refund()` — вернуть деньги за собственную покупку
через API нельзя, возврат инициирует продавец.

---

## PurchaseManager (через account.purchase)

### `await fp.account.purchase.get_my_purchases(limit=0)`

Список ваших покупок со страницы истории покупок. Именно на нём строится кеш раннера
для `on_purchases`/`on_new_purchase`/`on_confirmed_purchases`/`on_refunded_purchase`.

```python
purchases = await fp.account.purchase.get_my_purchases(50)
for p in purchases:
    print(p.order_id, p.status)
```

Без покупок — пустой список, а не ошибка.

### `await fp.account.purchase.get_purchase_details(order_id)`

Полная информация о покупке со страницы `/orders/{id}/` (аналог
`order.get_order_details`, под капотом использует тот же `OrderManager`).

```python
purchase = await fp.account.purchase.get_purchase_details("ABC123")
print(purchase.status)
print(purchase.description)
```

---

## Альтернативный доступ через `fpx.services`

Те же методы доступны через отдельно объявленный `PurchaseManager` из `fpx.services`,
если хочется явно держать его как отдельную переменную:

```python
from fpx.services import PurchaseManager

purchase_mgr = PurchaseManager(fp.account)
details = await purchase_mgr.get_purchase_details("ABC123")
purchases = await purchase_mgr.get_my_purchases(50)
```
