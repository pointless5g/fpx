from dataclasses import dataclass, field
from typing import Any

from fpx.utils import errors as fpx_err


@dataclass
class CurrentLotInfo:
    id: str
    short_desc: str | int
    description: str
    price: float
    _client: Any = field(init=False, repr=False, default=None)

    async def edit_price(self, new_price: float) -> Any:
        """Изменяет цену лота"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект CurrentLotInfo не привязан к клиенту fpx")
        return await self._client.editor.change_lot_price(self.id, new_price)

    async def raise_lots(self) -> Any:
        """Поднимает все лоты"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект CurrentLotInfo не привязан к клиенту fpx")
        return await self._client.lot.raise_lots()

    async def deactivate(self) -> Any:
        """Выключает лот"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект CurrentLotInfo не привязан к клиенту fpx")
        return await self._client.editor.toggle_off_lot(self.id)

    async def activate(self) -> Any:
        """Включает лот"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект CurrentLotInfo не привязан к клиенту fpx")
        return await self._client.editor.toggle_on_lot(self.id)


@dataclass
class LotEditor:
    """
    Форма редактора лота (https://funpay.com/lots/offerEdit?offer=...).

    ``fields`` — поля формы в том виде, в каком они уйдут в ``POST /lots/offerSave``.
    Свойства ниже (порт ``LotFields`` из FunPayAPI) читают и пишут прямо в ``fields``,
    поэтому после их изменения объект можно сразу сохранить через
    ``LotManager.save_lot`` (или старый ``FunPayClient.edit_lot``).

    ``currency`` и ``stored_amount`` заполняет только ``LotManager.get_lot_fields``;
    у объекта из ``LotManager._get_lot_editor_details`` они остаются пустыми.
    """

    csrf_token: str
    form_created_at: str
    offer_id: str
    node_id: str
    location: str
    deleted: str
    fields: dict[str, Any] = field(default_factory=dict)
    # Код валюты лота из подписи у поля цены: "RUB", "USD", "EUR"; "" — не удалось определить.
    currency: str = ""
    # Наличие, которое FunPay хранит у лота (JSON в data-offer формы); None — неизвестно.
    stored_amount: int | None = None

    def _text(self, key: str) -> str:
        value = self.fields.get(key)
        return "" if value is None else str(value)

    def _checkbox(self, key: str) -> bool | None:
        """None — чекбокса нет в форме; иначе отмечен ли он."""
        if key not in self.fields:
            return None
        return bool(self.fields[key])

    def _set_checkbox(self, key: str, value: bool | None) -> None:
        if value is None:
            self.fields.pop(key, None)
        else:
            self.fields[key] = "on" if value else ""

    @property
    def title_ru(self) -> str:
        """Краткое описание (название) лота на русском."""
        return self._text("fields[summary][ru]")

    @title_ru.setter
    def title_ru(self, value: str) -> None:
        self.fields["fields[summary][ru]"] = value

    @property
    def title_en(self) -> str:
        """Краткое описание (название) лота на английском."""
        return self._text("fields[summary][en]")

    @title_en.setter
    def title_en(self, value: str) -> None:
        self.fields["fields[summary][en]"] = value

    @property
    def description_ru(self) -> str:
        """Подробное описание лота на русском."""
        return self._text("fields[desc][ru]")

    @description_ru.setter
    def description_ru(self, value: str) -> None:
        self.fields["fields[desc][ru]"] = value

    @property
    def description_en(self) -> str:
        """Подробное описание лота на английском."""
        return self._text("fields[desc][en]")

    @description_en.setter
    def description_en(self, value: str) -> None:
        self.fields["fields[desc][en]"] = value

    @property
    def payment_msg_ru(self) -> str:
        """Сообщение покупателю после оплаты на русском."""
        return self._text("fields[payment_msg][ru]")

    @payment_msg_ru.setter
    def payment_msg_ru(self, value: str) -> None:
        self.fields["fields[payment_msg][ru]"] = value

    @property
    def payment_msg_en(self) -> str:
        """Сообщение покупателю после оплаты на английском."""
        return self._text("fields[payment_msg][en]")

    @payment_msg_en.setter
    def payment_msg_en(self, value: str) -> None:
        self.fields["fields[payment_msg][en]"] = value

    @property
    def images(self) -> list[int]:
        """ID картинок лота."""
        return [int(i) for i in self._text("fields[images]").split(",") if i.strip().isdecimal()]

    @images.setter
    def images(self, value: list[int]) -> None:
        self.fields["fields[images]"] = ",".join(str(i) for i in value)

    @property
    def price(self) -> float | None:
        """Цена за 1 шт.; None, если поле цены пустое или его нет."""
        raw = self._text("price").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @price.setter
    def price(self, value: float | None) -> None:
        self.fields["price"] = "" if value is None else str(value)

    @property
    def auto_delivery(self) -> bool | None:
        """Включена ли автовыдача FunPay; None — в категории нет автовыдачи."""
        return self._checkbox("auto_delivery")

    @auto_delivery.setter
    def auto_delivery(self, value: bool | None) -> None:
        self._set_checkbox("auto_delivery", value)

    @property
    def deactivate_after_sale(self) -> bool | None:
        """Деактивировать ли лот после продажи; None — такого чекбокса нет."""
        return self._checkbox("deactivate_after_sale")

    @deactivate_after_sale.setter
    def deactivate_after_sale(self, value: bool | None) -> None:
        self._set_checkbox("deactivate_after_sale", value)

    @property
    def active_checkbox(self) -> bool:
        """Отмечен ли чекбокс «Активное» в форме (без учёта наличия)."""
        return self._text("active") == "on"

    @property
    def active(self) -> bool:
        """
        Активен ли лот, как его считает FunPayAPI: False, если FunPay хранит
        у лота наличие 0 (чекбокс при этом может оставаться отмеченным), иначе —
        состояние чекбокса «Активное».

        Запись меняет только чекбокс: у лота с сохранённым наличием 0 свойство
        останется False до следующего чтения после сохранения нового наличия.
        """
        if self.stored_amount == 0:
            return False
        return self.active_checkbox

    @active.setter
    def active(self, value: bool) -> None:
        self.fields["active"] = "on" if value else ""

    @property
    def secrets(self) -> list[str]:
        """Товары встроенной автовыдачи FunPay (непустые строки)."""
        return [i for i in self._text("secrets").strip().split("\n") if i]

    @secrets.setter
    def secrets(self, value: list[str]) -> None:
        self.fields["secrets"] = "\n".join(value)

    @property
    def amount(self) -> int | None:
        """
        Количество товара.

        При включённой автовыдаче — число товаров автовыдачи (как в FunPayAPI).
        Иначе значение поля «Наличие»; None, если поля нет в форме или оно пустое
        (пустое «Наличие» FunPay не ограничивает). FunPayAPI читает пустое поле
        как 0 — здесь 0 значит именно ноль.

        Запись кладёт число в поле «Наличие» как есть: 0 уходит на FunPay как "0",
        None очищает поле. FunPayAPI, в отличие от этого, отправлял 0 пустой
        строкой, то есть как неограниченное наличие.
        """
        if self.auto_delivery:
            return len(self.secrets)
        raw = self._text("amount").strip()
        return int(raw) if raw.isdecimal() else None

    @amount.setter
    def amount(self, value: int | None) -> None:
        self.fields["amount"] = "" if value is None else str(value)

    @property
    def subcategory_id(self) -> int | None:
        """ID подкатегории (node_id) числом."""
        node = str(self.node_id).strip()
        return int(node) if node.isdecimal() else None

    @property
    def public_link(self) -> str:
        """Публичная ссылка на лот."""
        return f"https://funpay.com/lots/offer?id={self.offer_id}"

    @property
    def private_link(self) -> str:
        """Ссылка на редактор лота."""
        return f"https://funpay.com/lots/offerEdit?offer={self.offer_id}"


@dataclass
class MyLotRow:
    """
    Строка таблицы своих лотов подкатегории (https://funpay.com/lots/<node>/trade).
    Порт ``MyLotShortcut`` из FunPayAPI.
    """

    offer_id: str
    node_id: str
    description: str | None
    server: str | None
    side: str | None
    amount: int | None
    price: float
    # Код валюты: "RUB", "USD", "EUR"; "" — не удалось определить.
    currency: str
    auto_delivery: bool
    # False у строк с классом warning: FunPay не показывает такой лот покупателям.
    active: bool
    html: str = field(default="", repr=False)

    @property
    def public_link(self) -> str:
        """Публичная ссылка на лот."""
        return f"https://funpay.com/lots/offer?id={self.offer_id}"

    @property
    def private_link(self) -> str:
        """Ссылка на редактор лота."""
        return f"https://funpay.com/lots/offerEdit?offer={self.offer_id}"


@dataclass
class FieldOptions:
    key: str
    value: str


@dataclass
class LotField:
    """
    key (str): ключ филда, типа fields[type]
    options (list[str] | None): список опций выборки, ну допустим Аренда, Продажа
    """

    key: str
    options: list[FieldOptions] | None
    value: str | None = None


@dataclass
class LotCreationFields:
    fields: list[LotField]
    _csrf_token: str
    _form_created_at: str
    _offer_id: str
    _node_id: str
    _location: str
    _deleted: str

    def get_field(self, field_key: str) -> LotField | None:
        for f in self.fields:
            if f.key == field_key:
                return f
        return None

    def _require_field(self, field_key: str) -> LotField:
        """
        Как get_field, но гарантирует не-None результат (для внутреннего использования
        в свойствах ниже, где отсутствие обязательного филда, баг данных, а не штатный случай).
        """
        f = self.get_field(field_key)
        assert f is not None, f"Филд с ключом '{field_key}' отсутствует в LotCreationFields.fields"
        return f

    def set_field(self, k: str, val: str) -> None:
        """
        Сохраняет филд

        Args:
            k (str): ключ филда (допустим fields[type])
            val (str): значение филда
        """
        for f in self.fields:
            if f.key == k:
                f.value = val

    def get_field_options(self, k: str) -> list[FieldOptions] | None:
        f = self.get_field(k)
        return f.options if f is not None else None

    @property
    def short_desc_ru(self) -> str | None:
        return self._require_field("fields[summary][ru]").value

    @short_desc_ru.setter
    def short_desc_ru(self, text: str) -> None:
        f = self._require_field("fields[summary][ru]")
        f.value = text

    @property
    def short_desc_en(self) -> str | None:
        return self._require_field("fields[summary][en]").value

    @short_desc_en.setter
    def short_desc_en(self, text: str) -> None:
        f = self._require_field("fields[summary][en]")
        f.value = text

    @property
    def desc_ru(self) -> str | None:
        return self._require_field("fields[desc][ru]").value

    @desc_ru.setter
    def desc_ru(self, text: str) -> None:
        f = self._require_field("fields[desc][ru]")
        f.value = text

    @property
    def desc_en(self) -> str | None:
        return self._require_field("fields[desc][en]").value

    @desc_en.setter
    def desc_en(self, text: str) -> None:
        f = self._require_field("fields[desc][en]")
        f.value = text

    @property
    def secrets(self) -> list[str]:
        secrets = self._require_field("secrets").value
        return secrets.split("\n") if secrets is not None else []

    @secrets.setter
    def secrets(self, val: list[str]) -> None:
        f = self._require_field("secrets")
        f.value = "\n".join(val)

    @property
    def payment_msg_ru(self) -> str | None:
        return self._require_field("fields[payment_msg][ru]").value

    @payment_msg_ru.setter
    def payment_msg_ru(self, text: str) -> None:
        f = self._require_field("fields[payment_msg][ru]")
        f.value = text

    @property
    def payment_msg_en(self) -> str | None:
        return self._require_field("fields[payment_msg][en]").value

    @payment_msg_en.setter
    def payment_msg_en(self, text: str) -> None:
        f = self._require_field("fields[payment_msg][en]")
        f.value = text

    @property
    def amount(self) -> str | None:
        return self._require_field("amount").value

    @amount.setter
    def amount(self, val: str) -> None:
        f = self._require_field("amount")
        f.value = val

    @property
    def price(self) -> str | None:
        return self._require_field("price").value

    @price.setter
    def price(self, val: str) -> None:
        f = self._require_field("price")
        f.value = val

    @property
    def images(self) -> list[str]:
        """
        Список id фоток
        """
        images = self._require_field("fields[images]").value
        return images.split(",") if images is not None else []

    @images.setter
    def images(self, images: list[str]) -> None:
        """
        Список id фоток
        """
        f = self._require_field("fields[images]")
        f.value = ",".join(str(i) for i in images)

    def validate(self) -> bool:
        """Валидация объекта"""
        required = [self.price, self.amount, self.short_desc_ru, self.short_desc_en]
        if all(v is not None for v in required):
            return True
        return False


@dataclass
class LotInfo:
    name: str
    id: str
    _client: Any = field(init=False, repr=False, default=None)

    async def edit_price(self, new_price: float) -> Any:
        """Изменяет цену лота"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект LotInfo не привязан к клиенту fpx")
        return await self._client.editor.change_lot_price(self.id, new_price)

    async def raise_lots(self) -> Any:
        """Поднимает все лоты"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект LotInfo не привязан к клиенту fpx")
        return await self._client.lot.raise_lots()

    async def deactivate(self) -> Any:
        """Выключает лот"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект LotInfo не привязан к клиенту fpx")
        return await self._client.editor.toggle_off_lot(self.id)

    async def activate(self) -> Any:
        """Включает лот"""
        if not self._client:
            raise fpx_err.FpxCriticalRunnerError("Объект LotInfo не привязан к клиенту fpx")
        return await self._client.editor.toggle_on_lot(self.id)


@dataclass
class CategoryLastLot:
    category_id: str
    filtration: str
    price: float
    offer_id: str
    owner_username: str
