# Лоты и поднятие

Получение информации о лотах, автоподнятие и массовое скрытие/показ.

---

## LotManager (через account.lot)

### `await fp.account.lot.get_lot_info(lot_id)`

Информация о лоте.

```python
lot = await fp.account.lot.get_lot_info("12345678")
print(lot.short_desc)  # краткое описание
print(lot.description)  # полное описание
print(lot.price)  # цена (float)
```

Возвращает `CurrentLotInfo`.

### `await fp.account.lot.raise_lots()`

Поднимает все твои лоты во всех категориях.

```python
responses = await fp.account.lot.raise_lots()
```

Возвращает список ответов от сервера. Если у тебя нет лотов — кинет `FpxRaisingLotError`.

**Пример автоподнятия:**

```python
import asyncio


async def auto_raise():
    while True:
        try:
            await fp.account.lot.raise_lots()
            print("Лоты подняты")
        except Exception as e:
            print(f"Ошибка: {e}")
        await asyncio.sleep(60 * 30)  # раз в 30 минут


# Запускаем фоном
asyncio.create_task(auto_raise())
await fp.runner.start_polling(3, is_background=True)
await fp.runner.idle()
```

### `await fp.account.lot.set_offers_hidden(hidden)`

Массово скрывает или показывает все лоты аккаунта (trade lock FunPay: `POST /trade/tradeLockSettings`).

```python
await fp.account.lot.set_offers_hidden(True)   # скрыть все лоты
await fp.account.lot.set_offers_hidden(False)  # показать все лоты
```

Возвращает `True` при успешном запросе. Если `user_id` ещё не закеширован — сначала запросит данные профиля. При ошибке кинет `FpxLotEditingError` (неверные куки - `FpxAuthError`).

### `await fp.account.lot.get_my_subcategory_lots(node_id)`

Таблица твоих лотов одной подкатегории — страница `https://funpay.com/lots/<node_id>/trade`. Один запрос на подкатегорию, включая выключенные лоты.

```python
rows = await fp.account.lot.get_my_subcategory_lots(1331)
for row in rows:
    print(row.offer_id, row.description, row.price, row.currency, row.amount, row.active)
```

Возвращает `list[MyLotRow]` (пустой список, если лотов в подкатегории нет):
- `offer_id`, `node_id` (`str`)
- `description`, `server`, `side` (`str | None`) — колонки таблицы
- `amount` (`int | None`) — наличие, `None` если колонки нет
- `price` (`float`), `currency` (`"RUB"`, `"USD"`, `"EUR"` или `""`)
- `auto_delivery` (`bool`) — у лота включена автовыдача FunPay
- `active` (`bool`) — `False` у строк, которые FunPay помечает как неактивные (класс `warning`)

Полное название подкатегории страница не содержит — его можно взять из `fp.account.category.get_all_categories()` (отдельный запрос главной).

Кинет `FpxAuthError`, если сессия не авторизована, и `FpxGetMyLotsError` при других ошибках.

### `await fp.account.lot.get_lot_fields(lot_id)`

Читает форму редактора лота (`/lots/offerEdit?offer=...`) так же, как `get_lot_fields` из FunPayAPI: только форму редактора, без выборок из скрытых групп, со снятыми чекбоксами в виде пустой строки. Возвращает `LotEditor`, у которого, кроме `fields`, заполнены:

- `currency` — валюта лота (`"RUB"`, `"USD"`, `"EUR"` или `""`)
- `stored_amount` — наличие, которое FunPay хранит у лота (`int | None`)

и есть свойства для чтения и записи: `price`, `amount`, `active`, `auto_delivery`, `secrets`, `title_ru`/`title_en`, `description_ru`/`description_en`, `payment_msg_ru`/`payment_msg_en`, `images`, `deactivate_after_sale`; только для чтения — `active_checkbox`, `subcategory_id`.

- `active` — `False`, если у лота сохранено наличие 0 (FunPay оставляет чекбокс отмеченным у распроданного лота); сам чекбокс — `active_checkbox`. Запись в `active` меняет чекбокс.
- `amount` — при включённой автовыдаче это число товаров автовыдачи; иначе поле «Наличие», `None` если поле пустое (неограниченно) или его нет. `lot.amount = 0` отправит `"0"`, `lot.amount = None` очистит поле.

Если FunPay вместо формы отдал страницу ошибки (лот удалён или чужой) — `FpxLotNotFoundError` (подкласс `FpxGetLotEditorInfoError`, в нём `lot_id` и `error_message`).

### `await fp.account.lot.save_lot(lot)`

Сохраняет лот из `get_lot_fields` целиком (`POST /lots/offerSave`). Поля, которые ты не менял, уходят такими, какими пришли.

```python
from fpx.utils.errors import FpxLotSaveError

lot = await fp.account.lot.get_lot_fields(12345678)
lot.price = 150.0
lot.amount = 10
try:
    await fp.account.lot.save_lot(lot)
except FpxLotSaveError as e:
    print(e.error_message, e.errors)  # {"price": "..."}
```

При успехе возвращает `None`. Если FunPay вернул `error`/`errors` — `FpxLotSaveError` с ошибками по полям в `errors`. Если ответ не 200 или не JSON (исход неизвестен) — `FpxRequestError`.

---

## Внутренний метод (для редактора)

### `await fp.account.lot._get_lot_editor_details(lot_id)`

Возвращает технический объект `LotEditor` с полными данными формы редактирования. Используется внутри редактора, самому вызывать не нужно.

Возвращает `LotEditor`:
- `csrf_token`, `form_created_at`, `offer_id`, `node_id`
- `fields` — словарь со всеми полями лота

---

## Альтернативный доступ через `fpx.services`

```python
from fpx.services import LotManager

lot_mgr = LotManager(fp.account)
lot = await lot_mgr.get_lot_info("12345678")
```
