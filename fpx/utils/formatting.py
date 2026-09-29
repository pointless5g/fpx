"""Безопасная подстановка плейсхолдеров ``{name}`` в текстах ответов."""

from __future__ import annotations

import re
from typing import Any

# ``{{`` / ``}}`` — экранирование как у str.format; ``{name}`` — именованный плейсхолдер.
_TOKEN_RE = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}")


def safe_format(template: str, **kwargs: Any) -> str:
    """Подставить известные плейсхолдеры, не падая на фигурных скобках в тексте.

    Заменяет только ``{name}``, для которых передано значение. Неизвестные имена
    (``{SALE50}``), числовые скобки (``{100}``), JSON и непарные ``{`` / ``}``
    остаются как есть. Удвоенные скобки ``{{`` / ``}}`` по-прежнему экранируют
    одну скобку — как ``str.format``.
    """

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        key = match.group(1)
        if key in kwargs:
            return format(kwargs[key])
        return token

    return _TOKEN_RE.sub(_replace, template)


def private_chat_name(first_user_id: Any, second_user_id: Any) -> str | None:
    """Имя личного чата FunPay двух пользователей: ``users-<меньший ID>-<больший ID>``.

    Так FunPay называет ноду переписки (и так её собирает FunPayAPI для заказов).

    Returns:
        Имя чата или ``None``, если хотя бы один ID неизвестен или не число.
    """
    ids: list[int] = []
    for user_id in (first_user_id, second_user_id):
        if user_id is None or isinstance(user_id, bool):
            return None
        try:
            ids.append(int(str(user_id).strip()))
        except ValueError:
            return None
    low, high = sorted(ids)
    return f"users-{low}-{high}"
