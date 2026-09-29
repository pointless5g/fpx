"""Тесты ChatParser — парсинг списка чатов и переписки."""

import json

import pytest

from fpx._parsers._chats import ChatParser
from fpx.models.chat import Chat
from fpx.utils import errors as fpx_err
from fpx.utils.message_types import MessageType, classify_notice


class TestChatParser:
    def test_parse_chats_list_success(self):
        """Успешный парсинг: 1 чат с полными данными."""
        html = """
        <a class="contact-item" href="/chat/?node=777" data-node-msg="999">
          <div class="media-user-name">Иван</div>
          <div class="contact-item-message">Привет!</div>
          <div class="contact-item-time">10:00</div>
        </a>
        """
        chats = ChatParser.parse_chats_list(html)
        assert len(chats) == 1
        assert isinstance(chats[0], Chat)
        assert chats[0].id == "777"
        assert chats[0].node_msg_id == 999
        assert chats[0].username == "Иван"
        assert chats[0].last_msg == "Привет!"
        assert chats[0].date == "10:00"
        assert chats[0].is_unread is False

    def test_parse_chats_list_unread(self):
        """Чат с классом unread помечается is_unread=True."""
        html = """
        <a class="contact-item unread" href="/chat/?node=888" data-node-msg="1">
          <div class="media-user-name">Петр</div>
        </a>
        """
        chats = ChatParser.parse_chats_list(html)
        assert chats[0].is_unread is True

    def test_parse_chats_list_fallback_links(self):
        """Если нет класса contact-item — fallback по href с node=."""
        html = """<a href="/chat/?node=111">Чат</a>"""
        chats = ChatParser.parse_chats_list(html)
        assert len(chats) == 1
        assert chats[0].id == "111"

    def test_parse_chats_list_empty_raises(self):
        """Пустая страница → FpxNullDataError."""
        with pytest.raises(fpx_err.FpxNullDataError):
            ChatParser.parse_chats_list("<html><body>Пусто</body></html>")

    def test_parse_chat_success(self):
        """Парсинг конкретного чата: последнее сообщение от пользователя."""
        html = """
        <html><body>
          <div class="chat" data-id="123">
            <div class="chat-msg-item">
              <div class="media-user-name">
                <a class="chat-msg-author-link">Петр</a>
              </div>
              <div class="chat-msg-text">Как дела?</div>
            </div>
          </div>
        </body></html>
        """
        result = ChatParser.parse_chat(html)
        assert result["data-id"] == "123"
        assert "messages" in result
        msgs = result["messages"]
        for msg in msgs:
            assert msg["sender"] == "Петр"
            assert msg["message"] == "Как дела?"
            assert msg["is_system"] is False
            break

    def test_parse_chat_system_notification(self):
        """Системное сообщение: отправитель = FunPay, is_system = True."""
        html = """
        <html><body>
          <div class="chat">
            <div class="chat-msg-item">
              <div class="media-user-name">
                <span class="chat-msg-author-label">Оповещение</span>
              </div>
              <div class="chat-msg-text">Заказ оплачен</div>
            </div>
          </div>
        </body></html>
        """
        result = ChatParser.parse_chat(html)
        msgs = result["messages"]
        for msg in msgs:
            assert msg["sender"] == "FunPay"
            assert msg["is_system"] is True

    def test_parse_chat_real_notification_markup(self):
        """Оповещение и сообщение покупателя в разметке страницы чата FunPay (сентябрь 2026).

        Ники, ID и номер заказа заменены. У оповещения имя FunPay написано текстом,
        без ссылки на профиль, и стоит метка «оповещение»; ссылки на покупателя
        есть только в тексте сообщения. Покупатель, написавший «оплатил заказ»,
        системным не считается.
        """
        html = """
        <html>
        <body data-app-data="{&quot;csrf-token&quot;:&quot;tok&quot;,&quot;userId&quot;:1000}">
        <div class="chat chat-float" data-id="555" data-name="users-1000-2000" data-user="1000">
        <div class="chat-message-container"><div class="chat-message-list">
        <div class="chat-msg-item chat-msg-with-head" id="message-101">
        <div class="chat-message">
        <div class="media-user-name">
                        FunPay
                        <span class="chat-msg-author-label label label-primary">оповещение</span>
        <div class="chat-msg-date" title="26 сентября, 4:09:42">04:09:42</div>
        </div>
        <div class="chat-msg-body">
        <div class="alert alert-with-icon alert-info" role="alert">
        <i class="fas fa-info-circle alert-icon"></i>
        <div class="chat-msg-text">Покупатель <a href="https://funpay.com/users/2000/">Buyer</a> оплатил
        <a href="https://funpay.com/orders/ABCD1234/">заказ #ABCD1234</a>. Roblox, Донат робуксов (паки), 80 робуксов.
        <a href="https://funpay.com/users/2000/">Buyer</a>, не забудьте потом нажать кнопку
        «Подтвердить выполнение заказа».</div>
        </div>
        </div>
        </div>
        </div>
        <div class="chat-msg-item chat-msg-with-head" id="message-102">
        <div class="chat-message">
        <div class="media-user-name">
        <a class="chat-msg-author-link" href="https://funpay.com/users/2000/">Buyer</a>
        <div class="chat-msg-date" title="26 сентября, 4:10:22">04:10:22</div>
        </div>
        <div class="chat-msg-body">
        <div class="chat-msg-text">Я оплатил заказ, где товар?</div>
        </div>
        </div>
        </div>
        </div></div>
        </div>
        </body>
        </html>
        """
        messages = ChatParser.parse_chat(html)["messages"]
        assert [(msg["node_id"], msg["sender"], msg["is_system"]) for msg in messages] == [
            ("101", "FunPay", True),
            ("102", "Buyer", False),
        ]
        assert messages[0]["message"].startswith("Покупатель")

    def test_parse_chat_bookmarks(self):
        """Список чатов из chat_bookmarks ответа /runner/ - та же разметка, что на /chat/."""
        html = (
            '<a href="https://funpay.com/chat/?node=555" class="contact-item unread" data-id="555"'
            ' data-node-msg="102" data-user-msg="101"><div class="contact-item-photo"></div>'
            '<div class="media-user-name">Buyer</div><div class="contact-item-message">Привет</div>'
            '<div class="contact-item-time">12:00</div></a>'
            '<a href="https://funpay.com/chat/?node=556" class="contact-item" data-id="556" data-node-msg="90">'
            '<div class="media-user-name">Other</div><div class="contact-item-message">Изображение</div></a>'
        )
        chats = ChatParser.parse_chat_bookmarks(html)
        assert [(chat.id, chat.node_msg_id, chat.username, chat.last_msg, chat.is_unread) for chat in chats] == [
            ("555", 102, "Buyer", "Привет", True),
            ("556", 90, "Other", "Изображение", False),
        ]

    def test_parse_chat_bookmarks_empty_is_not_an_error(self):
        """У аккаунта без чатов chat_bookmarks пустой - это не ошибка разметки."""
        assert ChatParser.parse_chat_bookmarks("") == []

    def test_parse_runner_messages_real_markup(self):
        """Сообщения chat_node в разметке страницы чата FunPay (сентябрь 2026), ники и ID заменены.

        Ник есть только у первого сообщения серии, поэтому автор без шапки
        берётся из переданных имён или из предыдущей шапки того же автора.
        """
        notification = """
        <div class="chat-msg-item chat-msg-with-head" id="message-101">
        <div class="chat-message">
        <div class="media-user-name">
                        FunPay
                        <span class="chat-msg-author-label label label-primary">оповещение</span>
        <div class="chat-msg-date" title="26 сентября, 4:09:42">04:09:42</div>
        </div>
        <div class="chat-msg-body">
        <div class="alert alert-with-icon alert-info" role="alert">
        <i class="fas fa-info-circle alert-icon"></i>
        <div class="chat-msg-text">Покупатель <a href="https://funpay.com/users/2000/">Buyer</a> оплатил
        <a href="https://funpay.com/orders/ABCD1234/">заказ #ABCD1234</a>.</div>
        </div>
        </div>
        </div>
        </div>"""
        buyer = """
        <div class="chat-msg-item chat-msg-with-head" id="message-102">
        <div class="chat-message">
        <div class="media-user-name">
        <a class="chat-msg-author-link" href="https://funpay.com/users/2000/">Buyer</a>
        <div class="chat-msg-date" title="26 сентября, 4:10:22">04:10:22</div>
        </div>
        <div class="chat-msg-body">
        <div class="chat-msg-text">Я оплатил заказ, где товар?</div>
        </div>
        </div>
        </div>"""
        continuation = (
            '<div class="chat-msg-item" id="message-103"><div class="chat-message">'
            '<div class="chat-msg-body"><div class="chat-msg-text">Второе</div></div></div></div>'
        )
        mine = (
            '<div class="chat-msg-item" id="message-104"><div class="chat-message">'
            '<div class="chat-msg-body"><div class="chat-msg-text">Ответ</div></div></div></div>'
        )
        messages = ChatParser.parse_runner_messages(
            [
                {"id": 101, "author": 0, "html": notification},
                {"id": 102, "author": 2000, "html": buyer},
                {"id": 103, "author": 2000, "html": continuation},
                {"id": 104, "author": 1000, "html": mine},
            ],
            {1000: "Shop"},
        )
        assert [(msg["node_id"], msg["sender"], msg["is_system"], msg["message"]) for msg in messages[1:]] == [
            (102, "Buyer", False, "Я оплатил заказ, где товар?"),
            (103, "Buyer", False, "Второе"),
            (104, "Shop", False, "Ответ"),
        ]
        assert (messages[0]["node_id"], messages[0]["sender"], messages[0]["is_system"]) == (101, "FunPay", True)
        assert messages[0]["message"].startswith("Покупатель")

    def test_parse_runner_messages_skips_broken_items(self):
        """Сообщение без ID пропускается, неизвестный автор без шапки - Unknown."""
        messages = ChatParser.parse_runner_messages(
            [{"id": "x"}, {"id": 5, "author": 42, "html": '<div class="chat-msg-text">hi</div>'}], {}
        )
        assert [(msg["node_id"], msg["sender"], msg["message"]) for msg in messages] == [(5, "Unknown", "hi")]

    def test_parse_chat_empty_raises(self):
        """HTML без блока чата → FpxNullDataError."""
        with pytest.raises(fpx_err.FpxNullDataError):
            ChatParser.parse_chat("<html><body>Нет чата</body></html>")

    def test_parse_chat_invalid_app_data_chains_cause(self):
        """Сломанный data-app-data → FpxParseError с исходным JSONDecodeError в __cause__."""
        html = """
        <html><body data-app-data="not-json">
          <div class="chat" data-name="users-1-2"></div>
        </body></html>
        """
        with pytest.raises(fpx_err.FpxParseError) as exc:
            ChatParser.parse_chat(html)
        assert isinstance(exc.value.__cause__, json.JSONDecodeError)


# -- сообщения chat_node: автор, метки, картинки, метка бота, оповещения


def _message_html(msg_id, text, head=None, label=None):
    """Разметка сообщения chat_node; head - ник автора (шапка серии), label - (класс метки, текст)."""
    label_html = f'<span class="chat-msg-author-label label {label[0]}">{label[1]}</span>' if label else ""
    head_html = (
        f'<div class="media-user-name"><a class="chat-msg-author-link" href="https://funpay.com/users/1/">{head}</a>'
        f"{label_html}</div>"
        if head
        else ""
    )
    classes = "chat-msg-item chat-msg-with-head" if head else "chat-msg-item"
    return (
        f'<div class="{classes}" id="message-{msg_id}"><div class="chat-message">{head_html}'
        f'<div class="chat-msg-body"><div class="chat-msg-text">{text}</div></div></div></div>'
    )


def _notice_html(msg_id, text):
    return (
        f'<div class="chat-msg-item chat-msg-with-head" id="message-{msg_id}"><div class="chat-message">'
        '<div class="media-user-name">FunPay <span class="chat-msg-author-label label label-primary">оповещение</span>'
        '</div><div class="chat-msg-body"><div class="alert alert-with-icon alert-info" role="alert">'
        f'<i class="fas fa-info-circle alert-icon"></i><div class="chat-msg-text">{text}</div></div></div></div></div>'
    )


class TestRunnerMessageDetails:
    def test_a_payment_notice_names_its_type_and_order(self):
        text = (
            'Покупатель <a href="https://funpay.com/users/2000/">Buyer</a> оплатил\n'
            '<a href="https://funpay.com/orders/ABCD1234/">заказ #ABCD1234</a>. Roblox, 80 робуксов.\n'
            '<a href="https://funpay.com/users/2000/">Buyer</a>, не забудьте потом нажать кнопку '
            "«Подтвердить выполнение заказа»."
        )
        (message,) = ChatParser.parse_runner_messages([{"id": 1, "author": 0, "html": _notice_html(1, text)}], {})
        assert (message["is_system"], message["type"], message["order_id"]) == (
            True,
            MessageType.ORDER_PURCHASED,
            "ABCD1234",
        )
        assert message["sender"] == "FunPay"
        assert message["message"].startswith("Покупатель Buyer оплатил")

    def test_a_buyer_who_writes_like_a_notice_is_still_a_buyer(self):
        html = _message_html(2, "Покупатель Buyer оплатил заказ #ABCD1234.", head="Buyer")
        (message,) = ChatParser.parse_runner_messages([{"id": 2, "author": 2000, "html": html}], {})
        assert (message["is_system"], message["type"], message["order_id"]) == (False, MessageType.NON_SYSTEM, None)

    def test_a_staff_label_marks_every_message_of_its_author(self):
        messages = ChatParser.parse_runner_messages(
            [
                {
                    "id": 3,
                    "author": 7,
                    "html": _message_html(3, "Здравствуйте", head="Arbiter", label=("label-success", "арбитраж")),
                },
                {"id": 4, "author": 7, "html": _message_html(4, "Жду ответа продавца")},
                {"id": 5, "author": 2000, "html": _message_html(5, "Я покупатель", head="Buyer")},
            ],
            {},
        )
        assert [(m["sender"], m["badge"], m["is_employee"]) for m in messages] == [
            ("Arbiter", "арбитраж", True),
            ("Arbiter", "арбитраж", True),
            ("Buyer", None, False),
        ]

    def test_an_autoreply_is_not_staff(self):
        html = _message_html(6, "Скоро отвечу", head="Shop", label=("label-default", "автоответ"))
        (message,) = ChatParser.parse_runner_messages([{"id": 6, "author": 1000, "html": html}], {}, my_id=1000)
        assert (message["is_autoreply"], message["is_employee"], message["badge"], message["is_own"]) == (
            True,
            False,
            "автоответ",
            True,
        )

    def test_a_picture_keeps_its_link_and_name(self):
        html = (
            '<div class="chat-msg-item" id="message-8"><div class="chat-message"><div class="chat-msg-body">'
            '<div class="chat-msg-text"><a class="chat-img-link" href="https://sfunpay.com/s/chat/ab/cd.jpg">'
            '<img src="https://sfunpay.com/s/chat/ab/cd200x200.jpg" alt="screenshot.png"></a></div></div></div></div>'
        )
        (message,) = ChatParser.parse_runner_messages([{"id": 8, "author": 2000, "html": html}], {})
        assert (message["image_link"], message["image_name"], message["by_bot"]) == (
            "https://sfunpay.com/s/chat/ab/cd.jpg",
            "screenshot.png",
            False,
        )
        assert message["message"] == "https://sfunpay.com/s/chat/ab/cd.jpg"

    def test_the_bot_mark_is_taken_off_the_text(self):
        messages = ChatParser.parse_runner_messages(
            [
                {"id": 9, "author": 1000, "html": _message_html(9, "⁡Готово!", head="Shop")},
                {"id": 10, "author": 1000, "html": _message_html(10, "⁤Старая метка")},
                {"id": 11, "author": 2000, "html": _message_html(11, "⁤не наша метка", head="Buyer")},
            ],
            {},
            my_id=1000,
        )
        assert [(m["message"], m["by_bot"], m["is_own"]) for m in messages] == [
            ("Готово!", True, True),
            ("Старая метка", True, True),
            ("⁤не наша метка", False, False),
        ]

    def test_line_breaks_stay_and_invisible_tails_go(self):
        html = _message_html(12, "логин<br>пароль ​⁣ ", head="Buyer")
        (message,) = ChatParser.parse_runner_messages([{"id": 12, "author": 2000, "html": html}], {})
        assert message["message"] == "логин\nпароль"
        assert message["html"] == html


class TestClassifyNotice:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                "Покупатель Buyer подтвердил успешное выполнение заказа #ABCD1234 и отправил деньги продавцу Shop.",
                MessageType.ORDER_CONFIRMED,
            ),
            (
                "The buyer Buyer has confirmed that order #ABCD1234 has been fulfilled successfully"
                " and that the seller Shop has been paid.",
                MessageType.ORDER_CONFIRMED,
            ),
            (
                "Администратор Admin подтвердил успешное выполнение заказа #ABCD1234 и отправил деньги продавцу Shop.",
                MessageType.ORDER_CONFIRMED_BY_ADMIN,
            ),
            ("Продавец Shop вернул деньги покупателю Buyer по заказу #ABCD1234.", MessageType.REFUND),
            ("Администратор Admin вернул деньги покупателю Buyer по заказу #ABCD1234.", MessageType.REFUND_BY_ADMIN),
            ("Часть средств по заказу #ABCD1234 возвращена покупателю.", MessageType.PARTIAL_REFUND),
            ("Заказ #ABCD1234 открыт повторно.", MessageType.ORDER_REOPENED),
            ("Покупатель Buyer написал отзыв к заказу #ABCD1234.", MessageType.NEW_FEEDBACK),
            ("Продавец Shop ответил на отзыв к заказу #ABCD1234.", MessageType.NEW_FEEDBACK_ANSWER),
            ("Покупатель Buyer изменил отзыв к заказу #ABCD1234.", MessageType.FEEDBACK_CHANGED),
            ("Покупатель Buyer удалил отзыв к заказу #ABCD1234.", MessageType.FEEDBACK_DELETED),
        ],
    )
    def test_known_notices(self, text, expected):
        assert classify_notice(text) == (expected, "ABCD1234")

    def test_notices_without_an_order(self):
        assert classify_notice(
            "Уважаемые продавцы, не доверяйте сообщениям в чате! Перед выполнением заказа всегда проверяйте "
            "наличие оплаты в разделе «Мои продажи»."
        ) == (MessageType.DEAR_VENDORS, None)
        assert classify_notice("Что-то новое от FunPay") == (MessageType.UNKNOWN_SYSTEM, None)
        assert classify_notice("Что-то новое про заказ #ABCD1234") == (MessageType.UNKNOWN_SYSTEM, "ABCD1234")
