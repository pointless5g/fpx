# Чаты и сообщения

Всё что связано с получением, отправкой и обработкой сообщений.

---

## Хендлеры (через роутер)

Основной способ — через `@fp.router.on_message()`. Подробно описано в разделе [Роутер](router.md).

```python
from fpx import types


@fp.router.on_message()
async def any_msg(message: types.Message):
    print(f"{message.sender}: {message.text}")
    await message.answer("Принято")
```

### Команды

```python
async def status_cmd(message: types.Message):
    await message.answer("Бот работает")


fp.router.message_commands({"!status": status_cmd})
```

---

## Объект Message

Прилетает в хендлеры. Содержит:

| Поле | Тип | Описание |
|------|-----|----------|
| `sender` | `str` | Ник отправителя |
| `chat_id` | `str` | ID чата (node) |
| `text` | `str` | Текст сообщения |
| `is_system` | `bool` | Системное ли сообщение |

### Методы

**`await message.answer(answer_text: str)`** — ответить в тот же чат. Поддерживает форматирование:
- `{sender}` — ник отправителя
- `{chat_id}` — ID чата
- `{text}` — текст сообщения

```python
await message.answer("Привет, {sender}! Твой ID чата: {chat_id}")
```

---

## ChatManager (через account.chat)

Методы для работы с чатами напрямую, вне хендлеров.

### `await fp.account.chat.get_chats()`

Возвращает список всех чатов на аккаунте.

```python
chats = await fp.account.chat.get_chats()
for chat in chats:
    print(f"{chat.username}: {chat.last_msg}")
```

Возвращает `list[Chat]`, каждый объект содержит:
- `id` — ID чата (node)
- `username` — Ник собеседника
- `last_msg` — Последнее сообщение
- `date` — Дата
- `link` — Ссылка на чат
- `is_unread` — Непрочитанное ли

### `await fp.account.chat.send_message(chat_id, text)`

Отправить сообщение в чат по его ID.

```python
await fp.account.chat.send_message("12345678", "Привет")
```

### `await fp.account.chat.send(chat_id, text=None, *, image_id=None, mark_bot=False)`

Отправляет текст или картинку и возвращает `SentMessage` с ID нового сообщения. Отправка и
чтение чата идут одним запросом `/runner/`, как на сайте: страница чата не загружается.

```python
sent = await fp.account.chat.send("users-1000-2000", "Готово!", mark_bot=True)
print(sent.id)  # ID сообщения в чате; None, если FunPay не вернул его в ответе
```

- `chat_id` — имя переписки `users-<ID>-<ID>` или числовой ID чата.
- `mark_bot=True` — текст начинается с метки бота U+2061; приём событий отдаёт такое
  сообщение с `by_bot=True` и без метки в тексте.
- Картинка: `image_id = await fp.account.upload_image_bytes(data)`, затем `send(chat_id, image_id=image_id)`.

Ошибки:

| Исключение | Что значит | Можно отправить ещё раз? |
|---|---|---|
| `FpxMessageRefusedError` | FunPay отказал; `error_message` — его текст, `is_flood` — слишком часто | да, если это флуд — после паузы |
| `FpxMessageOutcomeUnknownError` | Ответ не получен: сообщение могло уйти | осторожно: можно задвоить |
| `FpxMessageDeliverError` (прочие) | Запрос не ушёл: нет соединения, 429 | да |

### `await fp.account.chat.send_image(chat_id, image_id)`

Отправить изображение в чат по его ID.

```python
image_id = await fp.account.upload_image("photo.jpg")
await fp.account.chat.send_image("12345678", image_id)
```

**Аргументы:**
- `chat_id` (str) -- ID чата.
- `image_id` (str) -- ID изображения на FunPay, полученный через `fp.account.upload_image`.

**Возвращает** словарь ответа от FunPay.

**Исключения:** `FpxMessageDeliverError`.

### `await fp.account.chat.ban_chat(chat_id)`

Блокирует чат — то же действие, что кнопка «Заблокировать» в шапке переписки.

FunPay делает это через `POST /chat/mute` с `node_id` чата и `mute=1`.

```python
await fp.account.chat.ban_chat("12345678")
```

Если передан системный ID вида `users-123-456`, числовой `data-id` берётся со страницы чата.

**Аргументы:**
- `chat_id` (int | str) — ID чата (node / data-id).

**Возвращает** `True` при успехе.

**Исключения:** `FpxBanChatError`.

### `await fp.account.chat.get_chat_data(chat_id)`

Получает технические данные чата (csrf_token, node_name, последнее сообщение).

```python
data = await fp.account.chat.get_chat_data("12345678")
print(data.csrf_token)
print(data.last_message.text)
```

Возвращает `ChatData`:
- `node_name` — системный ID (например `users-12345-67890`)
- `csrf_token` — токен для POST-запросов
- `user_id` — твой ID
- `last_message` — объект `Message` (последнее сообщение)

---

## Альтернативный доступ через `fpx.services`

Все методы выше доступны и так же через `fp.account.chat`, и через отдельно объявленный `ChatManager` из `fpx.services` - оба варианта работают с тем же самым аккаунтом, разница только в стиле кода:

```python
from fpx.services import ChatManager

chat = ChatManager(fp.account)
chats = await chat.get_chats()
```

`ChatManager` не создаёт ничего своего — он просто принимает уже существующий `account` (например `fp.account`) и даёт к нему ещё один способ доступа.
