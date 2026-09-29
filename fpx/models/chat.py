from dataclasses import dataclass, field
from typing import Any, List, cast

from fpx.utils import errors as fpx_err
from fpx.utils.formatting import safe_format
from fpx.utils.message_types import MessageType


@dataclass
class Chat:
    """
    id: Chat id (node)
    username: Client nickname
    last_msg: Last message in chat
    date: last message date
    link: full chat link (https://funpay.com/chat/?node=id)
    is_unread: Readed or not
    """

    id: str
    node_msg_id: int
    username: str
    last_msg: str
    date: str
    link: str
    is_unread: bool


@dataclass
class Message:
    """
    Сообщение чата.

    Поля после is_system заполняет приём событий через /runner/; у сообщений из
    других источников они остаются по умолчанию.
    """

    node_msg_id: int
    sender: str
    chat_id: str | int
    text: str
    is_system: bool
    # ID автора на FunPay; 0 - оповещение FunPay.
    author_id: int | None = None
    # Имя переписки users-<ID>-<ID>: по нему отправляются сообщения и видно собеседника.
    chat_name: str | None = None
    # ID собеседника в личном чате (второй ID из chat_name).
    interlocutor_id: int | None = None
    # Сообщение написано с этого аккаунта: ботом или человеком из браузера.
    is_own: bool = False
    # Текст начинался с метки бота (U+2061), или картинка отправлена ботом FunPay Cardinal.
    by_bot: bool = False
    # Ссылка на картинку и её имя, если сообщение - картинка.
    image_link: str | None = None
    image_name: str | None = None
    # Зелёная метка сотрудника FunPay («поддержка», «арбитраж», «модерация») или серая («автоответ»).
    badge: str | None = None
    # Автор - сотрудник FunPay (зелёная метка).
    is_employee: bool = False
    # Автоответ FunPay от имени продавца (серая метка «автоответ»).
    is_autoreply: bool = False
    # Тип оповещения FunPay и номер заказа, о котором оно (только у is_system).
    type: MessageType = MessageType.NON_SYSTEM
    order_id: str | None = None
    # Разметка сообщения, как её прислал FunPay.
    html: str | None = field(default=None, repr=False)
    _client: Any = field(init=False, repr=False, default=None)

    async def answer(self, answer_text: str) -> bool:
        """Ответить в этот же чат"""
        if not self._client:
            # TODO(#12): убрать ignore после аннотации fpx/utils/errors.py
            raise fpx_err.FpxClientNotAttachedError("Объект Message не привязан к клиенту fpx")  # type: ignore[no-untyped-call]
        formatted_reply = safe_format(answer_text, sender=self.sender, chat_id=self.chat_id, text=self.text)
        return cast(bool, await self._client._account.chat.send_message(self.chat_id, formatted_reply))


@dataclass
class ChatData:
    node_name: str
    csrf_token: str
    user_id: str
    last_messages: List[Message]
