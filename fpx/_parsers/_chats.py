from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup, Tag

from fpx.models.chat import Chat
from fpx.utils import errors as fpx_err
from fpx.utils.message_types import MessageType, classify_notice

from ._base import BaseParser

logger = logging.getLogger("fpx.chat_parser")

# Метка бота в начале текста (FunPay Cardinal и fpx при отправке с mark_bot=True).
_BOT_MARK = "\u2061"
# Прежняя метка: считается ботом только в собственных сообщениях.
_OLD_BOT_MARK = "\u2064"
# Зелёная метка сотрудника FunPay в шапке сообщения; серая - «автоответ».
_STAFF_LABEL = "chat-msg-author-label label label-success"
_DEFAULT_LABEL = "chat-msg-author-label label label-default"
_AUTOREPLY_LABELS = frozenset({"автоответ", "автовідповідь", "auto-reply"})


def _strip_invisible_suffix(text: str) -> str:
    """Убирает с конца пробелы и невидимые символы (категория Cf), которые FunPay дописывает к тексту."""
    end = len(text)
    while end > 0 and (text[end - 1].isspace() or unicodedata.category(text[end - 1]) == "Cf"):
        end -= 1
    return text[:end]


class ChatParser(BaseParser):
    @classmethod
    def _parse_contact_item(cls, item: Tag) -> Chat:
        """Парсит элемент списка чатов (a.contact-item)."""
        href = cls._get_str_attr(item, "href")
        node_msg_id = int(cls._get_str_attr(item, "data-node-msg", "0"))
        chat_id = href.split("node=")[-1] if "node=" in href else ""
        username = cls.clean_text(item.find("div", class_="media-user-name"))
        last_msg = cls.clean_text(item.find("div", class_="contact-item-message"))
        date = cls.clean_text(item.find("div", class_="contact-item-time"))
        is_unread = "unread" in cls._get_class_list(item)
        return Chat(
            id=chat_id,
            node_msg_id=node_msg_id,
            username=username,
            last_msg=last_msg,
            date=date,
            link=href,
            is_unread=is_unread,
        )

    @classmethod
    def _message_text(cls, item: Tag) -> str:
        """Текст сообщения чата, у картинки без подписи - ссылка на неё."""
        msg_tag = item.find("div", class_="chat-msg-text")
        if not msg_tag:
            return ""
        message = msg_tag.get_text(separator="\n").strip()
        if not message:
            img_link = msg_tag.find("a", class_="chat-img-link")
            message = cls._get_str_attr(img_link, "href") if img_link else ""
        return message

    @classmethod
    def parse_chats_list(cls, html_content: str) -> list[Chat]:
        """Парсит страницу https://funpay.com/chat/"""
        soup = BeautifulSoup(html_content, "html.parser")
        items: list[Tag] = soup.find_all("a", class_="contact-item")
        if not items:
            items = cls._safe_parse_links(html_content, r"node=\d+")
        if not items:
            raise fpx_err.FpxNullDataError("На странице не найдено ни одного чата")
        chats: list[Chat] = []
        for item in items:
            try:
                chats.append(cls._parse_contact_item(item))
            except Exception as e:
                logger.debug(f"Ошибка парсинга отдельного чата: {e}. Пропускаем элемент.")
                continue
        if not chats:
            raise fpx_err.FpxParseError(
                "Не удалось распарсить ни один чат, верстка полностью изменилась, или что-то сломалось."
            )
        return chats

    @classmethod
    def parse_chat_bookmarks(cls, html_content: str) -> list[Chat]:
        """
        Парсит список чатов из объекта chat_bookmarks ответа /runner/.

        Разметка та же, что на https://funpay.com/chat/, но пустой список здесь
        не ошибка: у аккаунта может ещё не быть чатов.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        chats: list[Chat] = []
        for item in soup.find_all("a", class_="contact-item"):
            try:
                chat = cls._parse_contact_item(item)
            except Exception as e:
                logger.debug(f"Ошибка парсинга отдельного чата: {e}. Пропускаем элемент.")
                continue
            if chat.id:
                chats.append(chat)
        return chats

    @classmethod
    def parse_runner_messages(
        cls, messages: list[dict[str, Any]], names: dict[int, str], my_id: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Парсит сообщения объекта chat_node ответа /runner/.

        FunPay отдаёт у сообщения ID, ID автора и HTML в разметке страницы чата.
        Автор 0 - оповещение FunPay. Ник и метка автора в HTML есть только у первого
        сообщения серии, поэтому известные ники передаются в names ({ID автора: ник}),
        а метка берётся из первой шапки автора в пачке.

        Кроме прежних ключей (node_id, author_id, sender, message, is_system) у сообщения есть:
        is_own (автор - my_id), by_bot (метка бота U+2061 снята с текста), image_link и
        image_name (картинка), badge, is_employee и is_autoreply (метки автора), type и
        order_id (тип оповещения FunPay и номер заказа), html (исходная разметка).
        """
        names = dict(names)
        parsed: list[tuple[int, int, str, BeautifulSoup]] = []
        badges: dict[int, str | None] = {}
        for raw in messages:
            try:
                node_id = int(raw["id"])
                author_id = int(raw.get("author") or 0)
                html = str(raw.get("html") or "")
                item = BeautifulSoup(html.replace("<br>", "\n"), "html.parser")
            except Exception as e:
                logger.debug(f"Не удалось распарсить сообщение из chat_node: {e}")
                continue
            head = item.find("div", class_="media-user-name")
            if author_id and isinstance(head, Tag):
                author_link = head.find("a", class_="chat-msg-author-link")
                if author_link:
                    names[author_id] = author_link.get_text(strip=True)
                if author_id not in badges:
                    staff = head.find("span", attrs={"class": _STAFF_LABEL})
                    badges[author_id] = staff.get_text(strip=True) if staff else None
            elif author_id:
                author_link = item.find("a", class_="chat-msg-author-link")
                if author_link:
                    names[author_id] = author_link.get_text(strip=True)
            parsed.append((node_id, author_id, html, item))

        result: list[dict[str, Any]] = []
        for node_id, author_id, html, item in parsed:
            try:
                result.append(cls._runner_message(node_id, author_id, html, item, names, badges, my_id))
            except Exception as e:
                logger.debug(f"Не удалось распарсить сообщение {node_id} из chat_node: {e}")
        return result

    @classmethod
    def _runner_message(
        cls,
        node_id: int,
        author_id: int,
        html: str,
        item: BeautifulSoup,
        names: dict[int, str],
        badges: dict[int, str | None],
        my_id: int | None,
    ) -> dict[str, Any]:
        is_system = author_id == 0
        image_link: str | None = None
        image_name: str | None = None
        by_bot = False
        image = item.find("a", class_="chat-img-link")
        if not is_system and isinstance(image, Tag):
            image_link = cls._get_str_attr(image, "href") or None
            img = image.find("img")
            image_name = cls._get_str_attr(img, "alt") or None if isinstance(img, Tag) else None
            # Картинки бота FunPay Cardinal: «Отправлено_с_помощью_бота_FunPay_Cardinal.png».
            by_bot = bool(image_name and "funpay_cardinal" in image_name.lower())
            text = image_link or ""
        else:
            block = item.find("div", attrs={"role": "alert"}) if is_system else None
            if not isinstance(block, Tag):
                block = item.find("div", class_="chat-msg-text")
            text = _strip_invisible_suffix(block.get_text() if isinstance(block, Tag) else "")
            if is_system:
                text = text.strip()
            if text.startswith(_BOT_MARK) or (
                text.startswith(_OLD_BOT_MARK) and my_id is not None and author_id == my_id
            ):
                text = text[1:]
                by_bot = True
        message_type, order_id = classify_notice(text) if is_system else (MessageType.NON_SYSTEM, None)
        badge = badges.get(author_id)
        is_autoreply = False
        head = item.find("div", class_="media-user-name")
        default_label = head.find("span", attrs={"class": _DEFAULT_LABEL}) if isinstance(head, Tag) else None
        if default_label is not None:
            label = default_label.get_text(strip=True)
            is_autoreply = label.lower() in _AUTOREPLY_LABELS
            badge = badge or label
        return {
            "node_id": node_id,
            "author_id": author_id,
            "sender": "FunPay" if is_system else names.get(author_id, "Unknown"),
            "message": text,
            "is_system": is_system,
            "is_own": my_id is not None and author_id == my_id,
            "by_bot": by_bot,
            "image_link": image_link,
            "image_name": image_name,
            "badge": badge,
            "is_employee": badges.get(author_id) is not None,
            "is_autoreply": is_autoreply,
            "type": message_type,
            "order_id": order_id,
            "html": html,
        }

    @classmethod
    def parse_chat(cls, html_content: str) -> dict[str, Any]:
        """Парсит страницу https://funpay.com/chat/?node=..."""
        soup = BeautifulSoup(html_content, "html.parser")
        result: dict[str, Any] = {}
        chat_div = soup.find("div", class_="chat")
        if not chat_div:
            chat_div = soup.find("div", attrs={"data-id": re.compile(r"^\d+$")})
        body = soup.find("body")
        if not chat_div or not body:
            raise fpx_err.FpxNullDataError("На странице чата не найден блок переписки или тег body")
        chats = soup.find_all("div", class_="chat-msg-item")
        result["messages"] = []
        if chats:
            for chat in chats:
                try:
                    res: dict[str, Any] = {
                        "is_system": False,
                        "node_id": cls._get_str_attr(chat, "id").split("-")[-1],
                        "message": cls._message_text(chat),
                    }
                    author_block: Tag | None = None
                    current_node: Tag | None = chat
                    while current_node:
                        author_block = current_node.find("div", class_="media-user-name")
                        if author_block:
                            break
                        current_node = current_node.find_previous_sibling("div", class_="chat-msg-item")
                    if author_block:
                        author = author_block.find("a", class_="chat-msg-author-link")
                        if not author:
                            sender_lbl = author_block.find("span", class_="chat-msg-author-label")
                            res["sender"] = cls.clean_text(sender_lbl) if sender_lbl else "FunPay"
                            if res["sender"] and res["sender"].lower() == "оповещение":
                                res["sender"] = "FunPay"
                                res["is_system"] = True
                        else:
                            res["sender"] = author.get_text(strip=True)
                    else:
                        res["sender"] = "Unknown"
                    result["messages"].append(res)
                except Exception as e:
                    logger.debug(f"Не удалось распарсить N сообщение в чате: {e}")
        else:
            logger.debug("Сообщений не найдено!")
            # парсинг тех.данных
        try:
            result["data-name"] = cls._get_str_attr(chat_div, "data-name")
            result["data-id"] = cls._get_str_attr(chat_div, "data-id")
            app_data_str = cls._get_str_attr(body, "data-app-data", "{}") or "{}"
            app_data = json.loads(app_data_str)
            result["csrf-token"] = app_data.get("csrf-token", "")
            result["user-id"] = app_data.get("userId", "")
        except Exception as e:
            logger.debug(f"Ошибка извлечения системных данных чата: {e}")
            raise fpx_err.FpxParseError("Не удалось распарсить системные метаданные чата (CSRF/User ID)") from e
        return result
