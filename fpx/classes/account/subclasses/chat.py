from typing import Any, cast

import httpx

from fpx.models.chat import Chat, ChatData, Message, SentMessage
from fpx.utils import errors as fpx_err

# Метка бота в начале текста: по ней бот узнаёт свои сообщения (так же делает FunPay Cardinal).
BOT_MARK = "\u2061"
# Такого тега у FunPay нет, поэтому объект chat_node приходит с данными.
_EMPTY_TAG = "00000000"


class ChatManager:
    def __init__(self, account: Any) -> None:
        # account: Account (см. fpx/classes/account/account.py). Оставлен как Any,
        # так как сам класс Account ещё не аннотирован (отдельная задача #20).
        self._account = account

    async def get_chats(self) -> list[Chat]:
        """
        Собирает все чаты на аккаунте.

        Returns:
            list[Chat]: Список объектов чатов. Каждый содержит:
                - id (str): ID чата (node_id).
                - username (str): Имя клиента.
                - last_msg (str): Последнее сообщение в чате.
                - date (str): Дата последнего сообщения.
                - link (str): Полная ссылка на чат.
                - is_unread (bool): Прочитано или нет (True, если не прочитано).

        Raises:
            FpxGetChatsError: Ошибка получения чатов FunPay

        """
        step = "запрос страницы чатов с FunPay"
        try:
            html = await self._account._client.get_chats_page()
            step = "парсинг данных чатов"
            chats = self._account._parser.parse_chats_list(html)
        except Exception as e:
            raise fpx_err.FpxGetChatsError(f"Не удалось выполнить {step}. Ошибка: {e}") from e
        return cast(list[Chat], chats)

    async def send_message(self, chat_id: str, text: str, with_nodes: bool = False) -> dict[str, Any]:
        """
        Отправляет сообщение.

        Args:
            chat_id (str): ID чата
            text (str): Текст сообщения
        Returns:
            dict: Словарь, которым отвечает фанпей
                в формате {'objects': [], 'response': {'error': None}},
                если требуется, можно проверять if .send_message() / if not .send_message
                при ошибке пункт Raises
        Raises:
            FpxMessageNotDelivered: Если не удалось отправить сообщение.

        """
        step = f"запрос данных чата ID {chat_id}"
        try:
            if chat_id not in self._account.data._node_names or not self._account.data._csrf_token:
                await self.get_chat_data(chat_id)
            step = f"POST запрос на отправку сообщения {text} в чат ID {chat_id}"
            response = await self._account._client.send_message_request(
                self._account.data._node_names[chat_id], -1, text
            )
        except Exception as e:
            raise fpx_err.FpxMessageDeliverError(f"Не удалось выполнить {step}. Ошибка: {e}") from e
        _raise_refusal(response)
        return cast(dict[str, Any], response)

    async def send(
        self,
        chat_id: str | int,
        text: str | None = None,
        *,
        image_id: int | str | None = None,
        mark_bot: bool = False,
    ) -> SentMessage:
        """
        Отправляет сообщение или картинку и возвращает ID нового сообщения.

        Отправка и чтение чата идут одним запросом /runner/, как на сайте FunPay, поэтому
        страница чата не загружается, а ID отправленного сообщения берётся из ответа.

        Args:
            chat_id (str | int): ID чата (node) или имя переписки users-<ID>-<ID>.
            text (str | None): Текст сообщения.
            image_id (int | str | None): ID картинки из upload_image / upload_image_bytes.
            mark_bot (bool): Начать текст с метки бота U+2061. По ней приём событий
                отмечает сообщение как by_bot, и ID находится надёжнее.

        Returns:
            SentMessage: ID нового сообщения (None, если его не оказалось в ответе) и имя переписки.

        Raises:
            FpxMessageRefusedError: FunPay отказал (error_message - его текст); сообщение не отправлено.
            FpxMessageOutcomeUnknownError: ответ не получен или не читается; сообщение могло уйти.
            FpxMessageDeliverError: запрос не ушёл (нет соединения, FunPay ответил 429); сообщение не отправлено.
        """
        node = await self._node_name(chat_id)
        content = "" if image_id is not None else f"{BOT_MARK if mark_bot else ''}{text or ''}"
        data: dict[str, Any] = {"node": node, "last_message": -1, "content": content}
        if image_id is not None:
            data["image_id"] = int(image_id)
        chat_node = {
            "type": "chat_node",
            "id": node,
            "tag": _EMPTY_TAG,
            "data": {"node": node, "last_message": -1, "content": ""},
        }
        try:
            response = await self._account._client.runner_request([chat_node], {"action": "chat_message", "data": data})
        except fpx_err.FpxRequestOutcomeUnknownError as e:
            raise fpx_err.FpxMessageOutcomeUnknownError(f"Сообщение в чат {node} могло уйти: {e}") from e
        except (fpx_err.FpxRequestError, httpx.TransportError) as e:
            raise fpx_err.FpxMessageDeliverError(f"Сообщение в чат {node} не отправлено: {e}") from e
        except Exception as e:
            raise fpx_err.FpxMessageOutcomeUnknownError(f"Ответ на отправку в чат {node} не читается: {e}") from e
        _raise_refusal(response, nested_only=True)
        return await self._receipt(response, node, text, image_id is not None, mark_bot)

    async def _node_name(self, chat_id: str | int) -> str:
        """Имя переписки users-<ID>-<ID> для ID чата: из кеша или со страницы чата."""
        if str(chat_id).startswith("users-"):
            return str(chat_id)
        if chat_id not in self._account.data._node_names:
            await self.get_chat_data(chat_id)
        return str(self._account.data._node_names[chat_id])

    async def _receipt(
        self, response: dict[str, Any], node: str, text: str | None, is_image: bool, marked: bool
    ) -> SentMessage:
        """Новейшее своё сообщение в чате из ответа: картинка, помеченный текст или тот же текст."""
        if self._account.data.user_id is None:
            await self._account.profile.get_user_data()
        my_id = int(self._account.data.user_id)
        received = response.get("objects")
        objects: list[Any] = received if isinstance(received, list) else []
        chat = next(
            (
                obj.get("data")
                for obj in objects
                if isinstance(obj, dict)
                and obj.get("type") == "chat_node"
                and isinstance(obj.get("data"), dict)
                and node in (str((obj["data"].get("node") or {}).get("name")), str(obj.get("id")))
            ),
            None,
        )
        if chat is None:
            return SentMessage(id=None, chat_name=node, text=text)
        messages = self._account._parser.parse_runner_messages(chat.get("messages") or [], {}, my_id)
        wanted = (text or "").strip()
        for message in reversed(messages):
            if not message["is_own"]:
                continue
            if is_image:
                found = message["image_link"] is not None
            elif marked:
                found = message["by_bot"]
            else:
                found = message["image_link"] is None and message["message"].strip() == wanted
            if found:
                return SentMessage(
                    id=message["node_id"],
                    chat_name=node,
                    text=None if is_image else message["message"],
                    image_link=message["image_link"],
                    html=message["html"],
                )
        return SentMessage(id=None, chat_name=node, text=text)

    async def get_chat_data(self, chat_id: int | str, last_message_node_id: int | str | None = None) -> ChatData:
        """
        Получает данные чата.

        Args:
            chat_id (int | str): Айди чата

        Returns:
            ChatData: Объект с тех. данными чата:
                - node_name (str): Полный ID переписки, нужный для отправки сообщения (users-8778502-19903068)
                - csrf_token (str): Нужен для post запросов, сохраняется в кеш self.account._csrf_token
                - user_id (str): твой ID
                - Message: Объект, содержащий последнее сообщение в чате:
                    - chat_id (str): ID чата
                    - is_system (bool): Системное ли сообщение
                    - sender (str): Отправитель сообщения
                    - text (str): Текст сообщения
        Raises:
            FpxGetChatDataError: Ошибка запроса данных чата
        """
        try:
            stage = "запроса данных FunPay"
            html = await self._account._client.get_current_chat(chat_id)
            stage = "парсинга данных"
            data = self._account._parser.parse_chat(html)
        except Exception as e:
            raise fpx_err.FpxGetChatDataError(f"При выполнении {stage} произошла ошибка: {e}") from e
        good_msg_list: list[Message] = []
        if data.get("messages"):
            message_list = []
            for msg in data.get("messages"):
                message_list.append(
                    Message(
                        node_msg_id=msg.get("node_id"),
                        sender=msg.get("sender"),
                        text=msg.get("message"),
                        is_system=msg.get("is_system"),
                        chat_id=chat_id,
                    )
                )
            if not last_message_node_id:
                good_msg_list.append(message_list[-1])
            else:
                for msg in message_list:
                    if int(msg.node_msg_id) > int(last_message_node_id):
                        good_msg_list.append(msg)
        else:
            good_msg_list = []
        chat = ChatData(
            node_name=data["data-name"],
            csrf_token=data["csrf-token"],
            user_id=data["user-id"],
            last_messages=good_msg_list,
        )
        self._account.data._node_names[chat_id] = chat.node_name
        self._account.data._csrf_token = chat.csrf_token
        self._account.data.user_id = chat.user_id
        return chat

    async def send_image(self, chat_id: str | int, image_id: str | int) -> dict[str, Any]:
        """
        Отправка изображения в чат
        Args:
            chat_id (str): ID чата
            image_id (str): ID изображения на фанпей
                получить на fp.account.upload_image
        Returns:
            dict: Словарь, которым отвечает фанпей
                в формате {'objects': [], 'response': {'error': None}},
                если требуется, можно проверять if .send_message() / if not .send_message
                при ошибке пункт Raises
        Raises:
            FpxMessageNotDelivered: Если не удалось отправить сообщение.
        """
        step = f"запрос данных чата ID {chat_id}"
        try:
            if chat_id not in self._account.data._node_names or not self._account.data._csrf_token:
                await self.get_chat_data(chat_id)
            step = f"POST запрос на отправку изображения {image_id} в чат ID {chat_id}"
            response = await self._account._client.send_image_request(
                self._account.data._node_names[chat_id], -1, image_id
            )
        except Exception as e:
            raise fpx_err.FpxMessageDeliverError(f"Не удалось выполнить {step}. Ошибка: {e}") from e
        _raise_refusal(response)
        return cast(dict[str, Any], response)

    async def ban_chat(self, chat_id: int | str) -> bool:
        """
        Блокирует чат (кнопка «Заблокировать» в шапке чата FunPay).

        FunPay выполняет блокировку через ``POST /chat/mute`` с ``mute=1``.

        Args:
            chat_id (int | str): ID чата (node / data-id). Если передан
                системный ``users-...``, числовой ``data-id`` берётся со страницы чата.
        Returns:
            bool: True если чат заблокирован.
        Raises:
            FpxBanChatError: Не удалось заблокировать чат.
        """
        node_id = str(chat_id)
        step = f"блокировка чата ID {chat_id}"
        try:
            if not node_id.isdigit():
                step = f"запрос данных чата ID {chat_id}"
                html = await self._account._client.get_current_chat(chat_id)
                data = self._account._parser.parse_chat(html)
                parsed_id = data.get("data-id")
                if parsed_id:
                    node_id = str(parsed_id)
            step = f"POST запрос на блокировку чата ID {node_id}"
            response = await self._account._client.ban_chat(node_id)
        except Exception as e:
            raise fpx_err.FpxBanChatError(f"Не удалось выполнить {step}. Ошибка: {e}") from e
        if response.get("error") is None:
            return True
        error_code = response.get("error", "400")
        error_msg = response.get("msg", "Неизвестная ошибка")
        raise fpx_err.FpxBanChatError(f"Сервер вернул ошибку: {error_code} - {error_msg}")


def _raise_refusal(response: Any, *, nested_only: bool = False) -> None:
    """
    Отказ FunPay на отправку.

    FunPay кладёт ответ на действие в поле response: {"objects": [...], "response": {"error": ...}}.
    Ошибка на верхнем уровне - прежний разбор, он остаётся для совместимости.
    """
    if not isinstance(response, dict):
        raise fpx_err.FpxMessageRefusedError(None)
    answer = response.get("response")
    if isinstance(answer, dict):
        if answer.get("error") is not None:
            raise fpx_err.FpxMessageRefusedError(str(answer.get("error")))
        return
    if nested_only:
        raise fpx_err.FpxMessageRefusedError(None)
    if response.get("error") is not None:
        raise fpx_err.FpxMessageRefusedError(f"{response.get('error')} - {response.get('msg', 'Неизвестная ошибка')}")
