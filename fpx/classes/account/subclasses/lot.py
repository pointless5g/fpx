from typing import Any

from fpx.models.lots import CurrentLotInfo, FieldOptions, LotCreationFields, LotEditor, LotField, MyLotRow
from fpx.utils import errors as fpx_err

# Поля формы редактора, которые LotEditor хранит отдельными атрибутами, а не в fields.
_EDITOR_BASE_FIELDS = ("csrf_token", "form_created_at", "offer_id", "node_id", "location", "deleted")


class LotManager:
    def __init__(self, account: Any) -> None:
        # account: Account (см. fpx/classes/account/account.py). Оставлен как Any,
        # так как типизация здесь через реальный класс Account создала бы
        # циклический импорт (Account -> LotManager -> Account).
        self._account = account

    async def _get_lot_editor_details(self, lot_id: int | str) -> LotEditor:
        """
        Не для обычного использования! (функция для изменения лота)
        Получает данные для изменения лота с https://funpay.com/lots/offerEdit?offer={lot_id}.

        Args:
            lot_id (str | int): Айди лота
        Returns:
            LotEditor: Возвращает объект с:
                - csrf_token (str): нужен для любого post запроса.
                - form_created_at (str): время создания формы изменения лота.
                - offer_id (str): Айди оффера(лота).
                - node_id (str): Айди нода.
                - location (str): Обычно пустой.
                - deleted (str): Обычно пустой.
                - fields (dict): Словарь с филдами, нет фиксированного кол-ва филдов, просто отправляйте все.
        Raises:
            FpxGetLotEditorInfoError: ошибка поулучения данных редактора
        """
        try:
            stage = "запроса данных с FunPay"
            html = await self._account._client.get_lot_editor_data(lot_id)
            stage = "парсинга данных"
            data = self._account._parser.parse_edit_lot_page(html)
        except Exception as e:
            raise fpx_err.FpxGetLotEditorInfoError(f"При выполнении {stage} произошла ошибка: {e}") from e
        base_fields = ["csrf_token", "form_created_at", "offer_id", "node_id", "location", "deleted"]
        main_data = {k: v for k, v in data.items() if k in base_fields}
        other_fields = {k: v for k, v in data.items() if k not in base_fields}
        lot = LotEditor(**main_data, fields=other_fields)
        return lot

    async def get_my_subcategory_lots(self, node_id: int | str) -> list[MyLotRow]:
        """
        Таблица своих лотов одной подкатегории (https://funpay.com/lots/<node_id>/trade),
        как ``Account.get_my_subcategory_lots`` в FunPayAPI.

        Args:
            node_id (int | str): ID подкатегории.
        Returns:
            list[MyLotRow]: строки таблицы; пустой список, если лотов в подкатегории нет.
        Raises:
            FpxAuthError: сессия не авторизована.
            FpxGetMyLotsError: ошибка запроса или парсинга таблицы.
        """
        try:
            stage = "запроса данных с FunPay"
            html = await self._account._client.lot_menu_by_category(node_id)
            stage = "парсинга данных"
            rows: list[MyLotRow] = self._account._parser.parse_my_lots_table(html, str(node_id))
        except fpx_err.FpxAuthError:
            raise
        except Exception as e:
            raise fpx_err.FpxGetMyLotsError(
                f"Таблица лотов подкатегории {node_id}: при выполнении {stage} произошла ошибка: {e}"
            ) from e
        return rows

    async def get_lot_fields(self, lot_id: int | str) -> LotEditor:
        """
        Читает форму редактора лота так, как ``Account.get_lot_fields`` в FunPayAPI.

        В отличие от ``_get_lot_editor_details``: читает только форму редактора,
        пропускает выборки в скрытых группах, сохраняет снятые чекбоксы пустой
        строкой и заполняет ``LotEditor.currency`` и ``LotEditor.stored_amount``.
        Возвращённый объект можно менять через его свойства и сохранять через ``save_lot``.

        Args:
            lot_id (int | str): ID лота.
        Returns:
            LotEditor: форма лота.
        Raises:
            FpxAuthError: сессия не авторизована.
            FpxLotNotFoundError: FunPay отдал страницу ошибки (лот удалён или чужой).
            FpxGetLotEditorInfoError: ошибка запроса или парсинга формы.
        """
        try:
            stage = "запроса данных с FunPay"
            html = await self._account._client.get_lot_editor_data(lot_id)
            stage = "парсинга данных"
            data = self._account._parser.parse_lot_fields(html)
        except fpx_err.FpxAuthError:
            raise
        except fpx_err.FpxLotNotFoundError as e:
            raise fpx_err.FpxLotNotFoundError(
                f"Лот {lot_id} не открылся в редакторе: {e.error_message}",
                lot_id=str(lot_id),
                error_message=e.error_message,
            ) from e
        except Exception as e:
            raise fpx_err.FpxGetLotEditorInfoError(f"При выполнении {stage} произошла ошибка: {e}") from e
        fields = dict(data["fields"])
        base = {key: str(fields.pop(key, "")) for key in _EDITOR_BASE_FIELDS}
        return LotEditor(
            csrf_token=base["csrf_token"],
            form_created_at=base["form_created_at"],
            offer_id=base["offer_id"] or str(lot_id),
            node_id=base["node_id"],
            location=base["location"],
            deleted=base["deleted"],
            fields=fields,
            currency=data["currency"],
            stored_amount=data["stored_amount"],
        )

    def _check_save_response(self, response: Any, lot_id: int | str, *, strict: bool = False) -> None:
        """
        Проверяет ответ на ``POST /lots/offerSave``, как ``save_offer`` в FunPayAPI.

        Args:
            response: ответ FunPay.
            lot_id (int | str): ID лота (для текста ошибки).
            strict (bool): True — ответ не 200 или не JSON-объект считается
                неизвестным исходом и поднимает FpxRequestError. False — такие
                ответы пропускаются (их проверяют сами хелперы редактора).
        Raises:
            FpxLotSaveError: FunPay вернул ``error`` или ``errors``.
            FpxRequestError: (только strict) ответ не 200 или не JSON-объект.
        """
        try:
            body = response.json()
        except Exception:
            body = None
        rejection = self._account._parser.parse_lot_save_response(body) if isinstance(body, dict) else None
        if rejection is not None:
            error_message, errors = rejection
            details = "; ".join(f"{k}: {v}" if k else v for k, v in errors.items())
            reason = ". ".join(part for part in (error_message, details) if part) or "без описания"
            raise fpx_err.FpxLotSaveError(
                f"FunPay не сохранил лот {lot_id}: {reason}",
                lot_id=str(lot_id),
                error_message=error_message,
                errors=errors,
            )
        if not strict:
            return
        status = getattr(response, "status_code", None)
        if status != 200:
            raise fpx_err.FpxRequestError(f"Сохранение лота {lot_id}: FunPay ответил статусом {status}")
        if not isinstance(body, dict):
            raise fpx_err.FpxRequestError(
                f"Сохранение лота {lot_id}: FunPay ответил не JSON-объектом, результат неизвестен"
            )

    async def save_lot(self, lot: LotEditor) -> None:
        """
        Сохраняет отредактированный лот целиком (``POST /lots/offerSave``),
        как ``Account.save_lot`` в FunPayAPI. Отправляет ``lot.fields`` как есть,
        поэтому поля, которые не менялись (например, снятый чекбокс «Активное»
        или пустое «Наличие»), уходят такими, какими пришли из редактора.

        Args:
            lot (LotEditor): форма из ``get_lot_fields``, изменённая через свойства.
        Raises:
            FpxLotSaveError: FunPay отклонил сохранение (``error``/``errors`` в ответе);
                ошибки по полям — в ``errors``.
            FpxRequestError: запрос не выполнен или ответ не позволяет понять исход
                (статус не 200, ответ не JSON).
            FpxAuthError: сессия не авторизована.
        """
        try:
            response = await self._account._client.edit_lot(lot)
        except fpx_err.FpxError:
            raise
        except Exception as e:
            raise fpx_err.FpxRequestError(f"Запрос сохранения лота {lot.offer_id} не выполнен: {e}") from e
        self._check_save_response(response, lot.offer_id, strict=True)

    async def get_lot_secrets(self, lot_id: int | str) -> list[str]:
        """
        Запрос данных автовыдачи лота.

        Args:
            lot_id (int | str): ID лота
        Returns:
            list[str]: Список строк товаров автовыдачи.
        Raises:
            FpxGetLotInfoError: Ошибка запроса данных лота
        """
        try:
            stage = "запросе данных"
            data = await self._get_lot_editor_details(lot_id)
        except Exception as e:
            raise fpx_err.FpxGetLotInfoError(f"При {stage} произошла ошибка: {e}") from e
        return str(data.fields["secrets"]).split("\n")

    async def get_lot_info(self, lot_id: int | str) -> CurrentLotInfo:
        """
        Собирает данные лота.

        Args:
            lot_id (str | int): ID лота.
        Returns:
            CurrentLotInfo: Объект с этими данными:
                - short_desc (str): Краткое описание.
                - description (str): Полное описание.
                - price (float): Цена лота.
        Raises:
            FpxGetLotInfoError: Ошибка запроса данных лота
        """
        try:
            stage = "запроса данных"
            html = await self._account._client.get_lot_info(lot_id)
            stage = "парсинга данных"
            data = self._account._parser.parse_current_lot_menu(html)
            stage = "типизации данных"
            lot = CurrentLotInfo(
                id=str(lot_id),
                short_desc=data["short_desc"],
                description=data["description"],
                price=float(data["price"]),
            )
            lot._client = self._account
        except Exception as e:
            raise fpx_err.FpxGetLotInfoError(f"При выполнении {stage} произошла ошибка: {e}") from e
        return lot

    async def raise_lots(self) -> list[Any]:
        """
        Поднимает все лоты.

        Returns:
            list: Ответы от сервера.
        Raises:
            FpxRaisingLotError: Лот не поднят.
        """
        if not self._account.data._csrf_token:
            await self._account.profile.get_user_data()
        try:
            profile = await self._account.profile.profile()
            category_list = profile.category_ids
            if not category_list:
                raise fpx_err.FpxRaisingLotError("Нам нечего поднимать")
            response = []
            for node_id in category_list:
                game_id = await self._account.addons.get_game_id(node_id)
                response.append(await self._account._client.raise_lot(node_id, game_id))
            return response
        except Exception as e:
            raise fpx_err.FpxRaisingLotError(message=str(e)) from e

    async def get_node_editor_data(self, node_id: int | str) -> LotCreationFields:
        """
        Запрос нужных филдов для создания лота

        Args:
            node_id (int | str): Айди категории лота
        Returns:
            LotCreationFields: Объект, который нужно редактировать
                встроенными в него функциями
                подробнее в https://fpx.readthedocs.io/ru/latest/lot_creator/
        Raises:
            FpxGetLotEditorInfoError: Ошибка запроса данных редактора лота
        """
        try:
            stage = "запроса данных с FunPay"
            html = await self._account._client.get_node_editor_data(node_id)
            stage = "парсинга данных"
            data = self._account._parser.parse_create_lot_page(html)
        except Exception as e:
            raise fpx_err.FpxGetLotEditorInfoError(f"При выполнении {stage} произошла ошибка: {e}") from e
        base_fields = ["csrf_token", "form_created_at", "offer_id", "node_id", "location", "deleted"]
        main_data = {f"_{k}": v for k, v in data.items() if k in base_fields}
        other_fields: list[LotField] = []
        for k, v in data.items():
            if k not in base_fields:
                field_options: list[FieldOptions] | None = None
                if v:
                    field_options = []
                    for option in v:
                        field_options.append(FieldOptions(key=list(option.values())[0], value=list(option.keys())[0]))
                other_fields.append(LotField(key=k, options=field_options))
        lot = LotCreationFields(fields=other_fields, **main_data)
        return lot

    async def create_lot(self, lot_creation_fields: LotCreationFields) -> bool:
        """
        Создание лота.
        Args:
            lot_creation_fields (LotCreationFields): Объект,
                получаемый в self.get_node_editor_data,
                и настраиваемый там же, подробнее о настройке
                в https://fpx.readthedocs.io/ru/latest/lot_creator/
        Returns:
            bool: True если всё удалось
        Raises:
            FpxLotCreateError: Создание лота не удалось
        """
        try:
            if not lot_creation_fields.validate():
                raise fpx_err.FpxValidateError(
                    "Не удалось валидировать объект,"
                    "Вы не передали что-то из этого списка:"
                    "self.price, self.amount, self.short_desc_ru, self.short_desc_en"
                    "где self это ваш объект LotCreationFields"
                )
            response = await self._account._client.create_lot(lot_creation_fields)
            if response.status_code == 200:
                return True
            else:
                raise fpx_err.FpxRequestError(f"Сервер не ответил успешно. Код ошибки: {response.status_code}")
        except Exception as e:
            raise fpx_err.FpxLotCreateError(f"При создании лота произошла ошибка: {e}") from e

    async def set_offers_hidden(self, hide: bool):
        """
        Массово скрывает или показывает все лоты аккаунта через настройки профиля.

        Args:
            hide (bool): True - скрыть лоты, False - показать лоты
        Retruns:
            bool: True если удалось скрыть.
        Raises:
            FpxRequestError: Ошибка отправки запроса.
            FpxLotEditingError: Не удалось скрыть все лоты.
        """
        if self._account.data.user_id is None:
            await self._account.profile.get_user_data()
        try:
            r = await self._account._client.set_offers_hidden(self._account.data.user_id, hide)
            if r.status_code == 200:
                return True
            else:
                raise fpx_err.FpxRequestError(f"Сервер не ответил успешно. Код ошибки: {r.status_code} - {r.json()}")
        except Exception as e:
            raise fpx_err.FpxLotEditingError("Не удалось скрыть все лоты") from e
