"""Тесты ChatManager — чаты, отправка сообщений и изображений."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from fpx.classes.account.subclasses.chat import ChatManager
from fpx.models.chat import Chat, ChatData
from fpx.utils import errors as fpx_err


@pytest.fixture
def account():
    acc = MagicMock()
    acc.data._node_names = {}
    acc.data._csrf_token = None
    acc.data.user_id = None
    acc._client.get_chats_page = AsyncMock()
    acc._client.get_current_chat = AsyncMock()
    acc._client.send_message_request = AsyncMock()
    acc._client.send_image_request = AsyncMock()
    acc._client.ban_chat = AsyncMock()
    acc._parser.parse_chats_list = MagicMock()
    acc._parser.parse_chat = MagicMock()
    return acc


@pytest.fixture
def manager(account):
    return ChatManager(account)


class TestGetChats:
    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        account._client.get_chats_page.return_value = "<html></html>"
        chat = Chat(id="1", node_msg_id=1, username="Bob", last_msg="hi", date="10:00", link="/x", is_unread=False)
        account._parser.parse_chats_list.return_value = [chat]
        result = await manager.get_chats()
        assert result == [chat]

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        cause = RuntimeError("boom")
        account._client.get_chats_page.side_effect = cause
        with pytest.raises(fpx_err.FpxGetChatsError) as exc:
            await manager.get_chats()
        assert exc.value.__cause__ is cause


class TestGetChatData:
    @pytest.mark.asyncio
    async def test_success_with_messages_no_last_id(self, manager, account):
        account._client.get_current_chat.return_value = "<html></html>"
        account._parser.parse_chat.return_value = {
            "messages": [
                {"node_id": "1", "sender": "A", "message": "msg1", "is_system": False},
                {"node_id": "2", "sender": "A", "message": "msg2", "is_system": False},
            ],
            "data-name": "users-1-2",
            "csrf-token": "tok",
            "user-id": "1",
        }
        result = await manager.get_chat_data("chat-1")
        assert isinstance(result, ChatData)
        assert len(result.last_messages) == 1
        assert result.last_messages[0].text == "msg2"
        assert account.data._node_names["chat-1"] == "users-1-2"
        assert account.data._csrf_token == "tok"
        assert account.data.user_id == "1"

    @pytest.mark.asyncio
    async def test_success_with_last_message_node_id_filter(self, manager, account):
        account._client.get_current_chat.return_value = "<html></html>"
        account._parser.parse_chat.return_value = {
            "messages": [
                {"node_id": "1", "sender": "A", "message": "old", "is_system": False},
                {"node_id": "5", "sender": "A", "message": "new1", "is_system": False},
                {"node_id": "6", "sender": "A", "message": "new2", "is_system": False},
            ],
            "data-name": "users-1-2",
            "csrf-token": "tok",
            "user-id": "1",
        }
        result = await manager.get_chat_data("chat-1", last_message_node_id=2)
        assert [m.text for m in result.last_messages] == ["new1", "new2"]

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty_list(self, manager, account):
        account._client.get_current_chat.return_value = "<html></html>"
        account._parser.parse_chat.return_value = {
            "messages": [],
            "data-name": "users-1-2",
            "csrf-token": "tok",
            "user-id": "1",
        }
        result = await manager.get_chat_data("chat-1")
        assert result.last_messages == []

    @pytest.mark.asyncio
    async def test_error_wrapped(self, manager, account):
        cause = RuntimeError("boom")
        account._client.get_current_chat.side_effect = cause
        with pytest.raises(fpx_err.FpxGetChatDataError) as exc:
            await manager.get_chat_data("chat-1")
        assert exc.value.__cause__ is cause


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_success_fetches_chat_data_first_time(self, manager, account):
        account._client.get_current_chat.return_value = "<html></html>"
        account._parser.parse_chat.return_value = {
            "messages": [],
            "data-name": "users-1-2",
            "csrf-token": "tok",
            "user-id": "1",
        }
        account._client.send_message_request.return_value = {"error": None}
        result = await manager.send_message("chat-1", "hello")
        assert result == {"error": None}
        account._client.send_message_request.assert_awaited_once_with("users-1-2", -1, "hello")

    @pytest.mark.asyncio
    async def test_success_reuses_cached_node_name(self, manager, account):
        account.data._node_names["chat-1"] = "users-1-2"
        account.data._csrf_token = "tok"
        account._client.send_message_request.return_value = {"error": None}
        result = await manager.send_message("chat-1", "hello")
        assert result == {"error": None}
        account._client.get_current_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_response_raises(self, manager, account):
        account.data._node_names["chat-1"] = "users-1-2"
        account.data._csrf_token = "tok"
        account._client.send_message_request.return_value = {"error": "400", "msg": "bad"}
        with pytest.raises(fpx_err.FpxMessageDeliverError):
            await manager.send_message("chat-1", "hello")

    @pytest.mark.asyncio
    async def test_exception_wrapped(self, manager, account):
        account.data._node_names["chat-1"] = "users-1-2"
        account.data._csrf_token = "tok"
        account._client.send_message_request.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxMessageDeliverError):
            await manager.send_message("chat-1", "hello")


class TestSendImage:
    @pytest.mark.asyncio
    async def test_success(self, manager, account):
        account.data._node_names["chat-1"] = "users-1-2"
        account.data._csrf_token = "tok"
        account._client.send_image_request.return_value = {"error": None}
        result = await manager.send_image("chat-1", "img-1")
        assert result == {"error": None}
        account._client.send_image_request.assert_awaited_once_with("users-1-2", -1, "img-1")

    @pytest.mark.asyncio
    async def test_error_response_raises(self, manager, account):
        account.data._node_names["chat-1"] = "users-1-2"
        account.data._csrf_token = "tok"
        account._client.send_image_request.return_value = {"error": "400", "msg": "bad"}
        with pytest.raises(fpx_err.FpxMessageDeliverError):
            await manager.send_image("chat-1", "img-1")


class TestBanChat:
    @pytest.mark.asyncio
    async def test_success_numeric_id(self, manager, account):
        account._client.ban_chat.return_value = {"error": None}
        result = await manager.ban_chat("257449748")
        assert result is True
        account._client.ban_chat.assert_awaited_once_with("257449748")
        account._client.get_current_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_resolves_users_node_name(self, manager, account):
        account._client.get_current_chat.return_value = "<html></html>"
        account._parser.parse_chat.return_value = {"data-id": "257449748"}
        account._client.ban_chat.return_value = {"error": None}
        result = await manager.ban_chat("users-2700698-19797153")
        assert result is True
        account._client.get_current_chat.assert_awaited_once_with("users-2700698-19797153")
        account._client.ban_chat.assert_awaited_once_with("257449748")

    @pytest.mark.asyncio
    async def test_error_response_raises(self, manager, account):
        account._client.ban_chat.return_value = {"error": "1", "msg": "Нужно авторизоваться"}
        with pytest.raises(fpx_err.FpxBanChatError):
            await manager.ban_chat("123")

    @pytest.mark.asyncio
    async def test_exception_wrapped(self, manager, account):
        account._client.ban_chat.side_effect = Exception("boom")
        with pytest.raises(fpx_err.FpxBanChatError):
            await manager.ban_chat("123")


def _node(messages, name="users-1-2", node_id=555):
    """Объект chat_node ответа /runner/; messages - (ID, автор, текст)."""
    return {
        "type": "chat_node",
        "id": name,
        "tag": "t1",
        "data": {
            "node": {"id": node_id, "name": name, "silent": False},
            "messages": [
                {"id": msg_id, "author": author, "html": f'<div class="chat-msg-text">{text}</div>'}
                for msg_id, author, text in messages
            ],
        },
    }


@pytest.fixture
def sender(account):
    from fpx._parsers import FpxParser

    account.data.user_id = "1"
    account._parser = FpxParser()
    account._client.runner_request = AsyncMock()
    return ChatManager(account)


class TestSend:
    @pytest.mark.asyncio
    async def test_the_new_message_id_comes_from_the_same_request(self, sender, account):
        account._client.runner_request.return_value = {
            "objects": [_node([(10, 2, "Логин"), (11, 1, "⁡Готово"), (12, 2, "Спасибо")])],
            "response": {"error": None},
        }
        sent = await sender.send("users-1-2", "Готово", mark_bot=True)
        assert (sent.id, sent.chat_name, sent.text) == (11, "users-1-2", "Готово")
        objects, request = account._client.runner_request.await_args.args
        assert request == {
            "action": "chat_message",
            "data": {"node": "users-1-2", "last_message": -1, "content": "⁡Готово"},
        }
        assert objects[0]["type"] == "chat_node" and objects[0]["data"]["node"] == "users-1-2"
        account._client.get_current_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_without_the_mark_the_same_words_are_the_receipt(self, sender, account):
        account._client.runner_request.return_value = {
            "objects": [_node([(11, 1, "Привет"), (12, 1, "Готово")])],
            "response": {"error": None},
        }
        assert (await sender.send("users-1-2", "Привет")).id == 11

    @pytest.mark.asyncio
    async def test_a_receipt_missing_from_the_answer_is_no_id(self, sender, account):
        account._client.runner_request.return_value = {"objects": [], "response": {"error": None}}
        assert (await sender.send("users-1-2", "Готово", mark_bot=True)).id is None

    @pytest.mark.asyncio
    async def test_a_refusal_under_response_is_a_refusal(self, sender, account):
        account._client.runner_request.return_value = {
            "objects": [],
            "response": {"error": "Нельзя отправлять сообщения слишком часто."},
        }
        with pytest.raises(fpx_err.FpxMessageRefusedError) as refused:
            await sender.send("users-1-2", "Готово")
        assert refused.value.error_message == "Нельзя отправлять сообщения слишком часто."
        assert refused.value.is_flood is True

    @pytest.mark.asyncio
    async def test_no_answer_to_the_action_is_a_refusal(self, sender, account):
        account._client.runner_request.return_value = {"objects": [], "response": False}
        with pytest.raises(fpx_err.FpxMessageRefusedError) as refused:
            await sender.send("users-1-2", "Готово")
        assert refused.value.error_message is None

    @pytest.mark.asyncio
    async def test_a_request_that_may_have_gone_is_an_unknown_outcome(self, sender, account):
        account._client.runner_request.side_effect = fpx_err.FpxRequestOutcomeUnknownError("502")
        with pytest.raises(fpx_err.FpxMessageOutcomeUnknownError):
            await sender.send("users-1-2", "Готово")

    @pytest.mark.asyncio
    async def test_an_unreadable_answer_is_an_unknown_outcome(self, sender, account):
        account._client.runner_request.side_effect = ValueError("not json")
        with pytest.raises(fpx_err.FpxMessageOutcomeUnknownError):
            await sender.send("users-1-2", "Готово")

    @pytest.mark.asyncio
    async def test_a_request_that_never_left_is_not_sent(self, sender, account):
        account._client.runner_request.side_effect = fpx_err.FpxRequestError("429")
        with pytest.raises(fpx_err.FpxMessageDeliverError) as failed:
            await sender.send("users-1-2", "Готово")
        assert not isinstance(failed.value, fpx_err.FpxMessageOutcomeUnknownError)

    @pytest.mark.asyncio
    async def test_a_picture_is_sent_by_id_and_found_by_its_link(self, sender, account):
        picture = {
            "id": 13,
            "author": 1,
            "html": '<a class="chat-img-link" href="https://sfunpay.com/s/chat/x.jpg"><img alt="x.png"></a>',
        }
        node = _node([])
        node["data"]["messages"] = [picture]
        account._client.runner_request.return_value = {"objects": [node], "response": {"error": None}}
        sent = await sender.send("users-1-2", image_id=77)
        assert (sent.id, sent.image_link) == (13, "https://sfunpay.com/s/chat/x.jpg")
        _objects, request = account._client.runner_request.await_args.args
        assert request["data"]["image_id"] == 77 and request["data"]["content"] == ""

    @pytest.mark.asyncio
    async def test_a_numeric_chat_id_is_resolved_to_its_name_once(self, sender, account):
        account.data._node_names["555"] = "users-1-2"
        account._client.runner_request.return_value = {"objects": [], "response": {"error": None}}
        sent = await sender.send("555", "Привет")
        assert sent.chat_name == "users-1-2"


class TestLegacySendRefusal:
    @pytest.mark.asyncio
    async def test_a_refusal_under_response_is_no_longer_a_success(self, manager, account):
        account.data._node_names["chat-1"] = "users-1-2"
        account.data._csrf_token = "tok"
        account._client.send_message_request.return_value = {
            "objects": [],
            "response": {"error": "Нельзя отправлять сообщения слишком часто."},
        }
        with pytest.raises(fpx_err.FpxMessageRefusedError):
            await manager.send_message("chat-1", "hello")
