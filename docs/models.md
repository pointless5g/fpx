# Модели

Все датаклассы которые используются во фреймворке. Самому их создавать не нужно — фреймворк отдаёт уже готовые объекты в хендлеры. Импортировать модели можно через `from fpx import types`, а затем обращаться как `types.Message`, `types.Order`, `types.CurReview`, `types.CategoryLastLot`.

---

## Message

Входящее сообщение. Прилетает в хендлеры `on_message`.

| Поле | Тип | Описание |
|------|-----|----------|
| `sender` | `str` | Ник отправителя |
| `chat_id` | `str` | ID чата (node) |
| `text` | `str` | Текст сообщения |
| `is_system` | `bool` | Системное ли сообщение |
| `author_id` | `int \| None` | ID автора на FunPay, `0` — оповещение FunPay |
| `chat_name` | `str \| None` | Имя переписки `users-<ID>-<ID>` |
| `interlocutor_id` | `int \| None` | ID собеседника в личном чате |
| `is_own` | `bool` | Сообщение с этого аккаунта (бот или продавец из браузера) |
| `by_bot` | `bool` | Текст начинался с метки бота (U+2061), метка снята |
| `image_link`, `image_name` | `str \| None` | Картинка: ссылка и имя файла |
| `badge` | `str \| None` | Метка автора: «поддержка», «арбитраж», «модерация» или «автоответ» |
| `is_employee` | `bool` | Автор — сотрудник FunPay (зелёная метка) |
| `is_autoreply` | `bool` | Автоответ FunPay (серая метка) |
| `type` | `MessageType` | Тип оповещения FunPay: оплата, подтверждение, возврат, отзыв… (`NON_SYSTEM` у обычных) |
| `order_id` | `str \| None` | Номер заказа из оповещения |
| `html` | `str \| None` | Разметка сообщения, как её прислал FunPay |

Поля после `is_system` заполняются при приёме событий через `/runner/`.

**Метод:** `await message.answer(answer_text: str)` — ответить в чат. Поддерживает `{sender}`, `{chat_id}`, `{text}`.

---

## Order

Заказ. Прилетает в хендлеры заказов.

| Поле | Тип | Описание |
|------|-----|----------|
| `order_id` | `str` | ID заказа |
| `chat_id` | `str` | ID чата |
| `order_time` | `str` | Время заказа |
| `description` | `str` | Описание (данные от покупателя) |
| `client_name` | `str` | Ник покупателя |
| `price` | `float` | Цена |
| `amount` | `int` | Количество |
| `topup_data` | `str` | Данные для пополнения (ник, ссылка) |
| `status` | `str` | Статус |
| `name` | `str` | Название товара |
| `category` | `str` | Категория |
| `review` | `dict` | Отзыв |
| `buyer_id` | `int` | ID покупателя |
| `currency` | `Currency` | Валюта цены |
| `subcategory_id` | `int` | ID подкатегории |
| `subcategory_type` | `str` | `lot` / `chip` |
| `created_at` | `datetime` | Дата заказа по Москве |
| `status_kind` | `OrderStatusKind` | `paid` / `closed` / `refunded` |
| `chat_name` | `str` | Чат с покупателем `users-<ID>-<ID>` |

Поля от `buyer_id` до `chat_name` необязательные (`None` по умолчанию), их заполняет `get_my_sells`.

**Метод:** `await order.answer(answer_text: str)` — ответить в чат заказа. Поддерживает `{order_id}`, `{order_time}`, `{client_name}`, `{order_name}`.

---

## Purchase

Покупка. Братский класс [`Order`](#order) — те же поля и тот же метод `.answer()`, но
описывает не заказ у вас, а вашу покупку у другого продавца. Прилетает в хендлеры покупок
(см. [Покупки](purchases.md)).

| Поле | Тип | Описание |
|------|-----|----------|
| `order_id` | `str` | ID заказа |
| `chat_id` | `str` | ID чата |
| `order_time` | `str` | Время заказа |
| `description` | `str` | Описание (данные, которые вы ввели при покупке) |
| `client_name` | `str` | Ник продавца |
| `price` | `float` | Цена |
| `amount` | `int` | Количество |
| `topup_data` | `str` | Данные для пополнения (ник, ссылка) |
| `status` | `str` | Статус |
| `name` | `str` | Название товара |
| `category` | `str` | Категория |
| `review` | `dict` | Отзыв |
| `seller_id` | `int` | ID продавца |

И те же необязательные `currency`, `subcategory_id`, `subcategory_type`, `created_at`, `status_kind`,
`chat_name` (чат с продавцом), что у `Order`; их заполняет `get_my_purchases`.

**Метод:** `await purchase.answer(answer_text: str)` — ответить в чат покупки. Поддерживает `{order_id}`, `{order_time}`, `{client_name}`, `{order_name}`.
В отличие от `Order`, метода `.refund()` у `Purchase` нет.

---

## OrderInfo

Заказ из JSON API FunPay, возвращается `account.order.get_order()` / `get_orders()`.
Имена как в FunPayAPI: `sum` — сумма заказа, `amount` — количество товара.

| Поле | Тип | Описание |
|------|-----|----------|
| `order_id` | `str` | ID заказа |
| `status` | `OrderStatusKind` | `paid` / `closed` / `refunded` / `partially_refunded` / `unpaid` |
| `buyer_id`, `buyer_username` | `int`, `str` | Покупатель |
| `seller_id`, `seller_username` | `int`, `str` | Продавец |
| `chat_name` | `str` | Чат `users-<ID>-<ID>` |
| `sum` | `float` | Сумма заказа |
| `currency` | `Currency` | Валюта |
| `amount` | `int \| float` | Количество товара |
| `subcategory_id`, `subcategory_type` | `int`, `str` | Подкатегория (`lot` / `chip`) |
| `subcategory_name` | `str` | Название подкатегории, если FunPay его прислал |
| `player` | `str` | Имя персонажа (`character_name`) |
| `server`, `side` | `OrderServer`, `OrderSide` | Сервер и сторона (`id`, `name`) |
| `fields` | `dict[str, OrderField]` | Поля лота (`id`, `value`, `name`, `field_type_id`) |
| `order_secrets` | `list[str]` | Товары автовыдачи FunPay |
| `review` | `OrderReview` | Отзыв (`stars`, `text`, `reply`, `hidden`) или `None` |
| `locale` | `str` | `ru` / `en` — язык значений полей по умолчанию |
| `raw` | `dict` | Исходный объект заказа из ответа |

Свойства: `short_description` (`title`), `full_description`, `payment_msg`, `lot_params`
(список пар «название поля, значение»), `lot_params_text`, `lot_params_dict`. Методы:
`get_field(key)`, `get_field_value(key, locale)`, `get_field_value_any(key)`.

`Currency` (`fpx.utils.currency`) — строковый enum `RUB` / `USD` / `EUR` / `UNKNOWN`
(`Currency.RUB == "RUB"`, знак — `Currency.RUB.symbol`). `OrderStatusKind` — `fpx.utils.order_status`.

---

## CurReview

Текущий отзыв. Прилетает в хендлер `on_new_review`. Автоматически подтягивает данные заказа.

| Поле | Тип | Описание |
|------|-----|----------|
| `text` | `str` | Текст отзыва |
| `stars` | `int` | Звёзды (1-5) |
| `author` | `str` | Ник автора |
| `order_id` | `str` | ID заказа |
| `order` | `Order` | Объект заказа |

**Методы:**
- `await review.answer(answer_text)` — ответ на отзыв в профиле. Поддерживает `{author}`, `{order_id}`, `{order_name}`, `{order_time}`, `{stars}`
- `await review.message_author(message_text)` — написать автору в чат
- `await review.delete()` — удалить свой отзыв или ответ на отзыв

---

## Review

Статический отзыв (без связи с заказом). Возвращается `get_review`.

| Поле | Тип | Описание |
|------|-----|----------|
| `text` | `str` | Текст отзыва |
| `stars` | `int` | Звёзды |
| `answer` | `str` | Твой ответ |

---

## Chat

Чат из списка диалогов.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `str` | ID чата (node) |
| `node_msg_id` | `int` | ID последнего сообщения |
| `username` | `str` | Ник собеседника |
| `last_msg` | `str` | Текст последнего сообщения |
| `date` | `str` | Дата |
| `link` | `str` | Ссылка |
| `is_unread` | `bool` | Непрочитанное |

---

## ChatData

Технические данные чата.

| Поле | Тип | Описание |
|------|-----|----------|
| `node_name` | `str` | Системный ID (users-12345-67890) |
| `csrf_token` | `str` | CSRF-токен |
| `user_id` | `str` | Твой ID |
| `last_message` | `Message` | Последнее сообщение |

---

## CategoryLastLot

Информация о лоте в категории.

| Поле | Тип | Описание |
|------|-----|----------|
| `category_id` | `str` | ID категории |
| `filtration` | `str` | Фильтр |
| `price` | `float` | Цена |
| `offer_id` | `str` | ID лота |
| `owner_username` | `str` | Ник продавца |

---

## CurrentLotInfo

Информация о конкретном лоте.

| Поле | Тип | Описание |
|------|-----|----------|
| `short_desc` | `str` | Краткое описание |
| `description` | `str` | Полное описание |
| `price` | `float` | Цена |

---

## LotInfo

Лот из профиля.

| Поле | Тип | Описание |
|------|-----|----------|
| `name` | `str` | Название |
| `id` | `str` | ID лота |

---

## LotEditor

Технический объект редактора лота.

| Поле | Тип | Описание |
|------|-----|----------|
| `csrf_token` | `str` | Токен |
| `form_created_at` | `str` | Время создания формы |
| `offer_id` | `str` | ID оффера |
| `node_id` | `str` | ID нода |
| `location` | `str` | Локация |
| `deleted` | `str` | Флаг удаления |
| `fields` | `dict` | Все поля лота |
| `currency` | `str` | Валюта лота: `"RUB"`, `"USD"`, `"EUR"`, `""` (заполняет `get_lot_fields`) |
| `stored_amount` | `int \| None` | Наличие, сохранённое на FunPay (заполняет `get_lot_fields`) |

Свойства поверх `fields`: `price`, `amount`, `active`, `active_checkbox`, `auto_delivery`, `secrets`, `title_ru`, `title_en`, `description_ru`, `description_en`, `payment_msg_ru`, `payment_msg_en`, `images`, `deactivate_after_sale`, `subcategory_id`. Подробнее — в «Лоты и поднятие».

---

## MyLotRow

Строка таблицы своих лотов подкатегории (`get_my_subcategory_lots`).

| Поле | Тип | Описание |
|------|-----|----------|
| `offer_id` | `str` | ID лота |
| `node_id` | `str` | ID подкатегории |
| `description` | `str \| None` | Описание из таблицы |
| `server` | `str \| None` | Сервер |
| `side` | `str \| None` | Сторона |
| `amount` | `int \| None` | Наличие |
| `price` | `float` | Цена |
| `currency` | `str` | `"RUB"`, `"USD"`, `"EUR"` или `""` |
| `auto_delivery` | `bool` | Включена автовыдача FunPay |
| `active` | `bool` | Лот активен (строка без класса `warning`) |

---

## UserData

Данные юзера.

| Поле | Тип | Описание |
|------|-----|----------|
| `csrf_token` | `str` | CSRF-токен |
| `user_id` | `str` | ID юзера |

---

## Profile

Данные профиля.

| Поле | Тип | Описание |
|------|-----|----------|
| `category_ids` | `list` | ID категорий с лотами |
| `lots` | `list[LotInfo]` | Список лотов |
| `reviews` | `list[CurReview]` | Отзывы |

---

## Balance

Баланс аккаунта.

| Поле | Тип | Описание |
|------|-----|----------|
| `rub` | `float` | Рубли |
| `usd` | `float` | Доллары |
| `eur` | `float` | Евро |

---

## Transaction

Одна операция из истории баланса. Возвращается `get_transactions` / `get_transactions_page`.

| Поле | Тип | Описание |
|------|-----|----------|
| `transaction_id` | `str` | ID транзакции FunPay |
| `type` | `str` | `order` / `withdraw` / `payment` / `other` |
| `amount` | `float` | Сумма (минус для списаний) |
| `date` | `str` | Дата, как на FunPay |
| `description` | `str` | Описание (`Заказ #…`, `Вывод денег #…`) |
| `status` | `str` | `completed` / `cancelled` / `pending` / `unknown` |
| `currency` | `str` | `₽` / `$` / `€` |
| `payment_method` | `str` | Метод (например `card_rub`), если есть |
| `withdrawal_number` | `str` | Маскированный номер карты/кошелька |

---

## TransactionsPage

Одна пачка истории транзакций.

| Поле | Тип | Описание |
|------|-----|----------|
| `transactions` | `list[Transaction]` | Операции на странице |
| `next_transaction_id` | `str` | Курсор следующей пачки (`continue`) |
| `user_id` | `str` | ID владельца истории |
| `filter` | `str` | Применённый фильтр FunPay |

---

## Dependency

Зависимость для хендлеров.

```python
from fpx import Dependency, types


def get_user(message):
    return {"name": message.sender}


async def handler(message: types.Message, user: dict = Dependency(get_user)):
    print(user)
```
