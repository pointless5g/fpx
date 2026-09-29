"""Тесты иерархии исключений fpx."""

import pytest

from fpx.utils import errors as fpx_err


class TestErrors:
    def test_base_error_message(self):
        with pytest.raises(fpx_err.FpxError) as exc:
            raise fpx_err.FpxError("Что-то сломалось")
        assert "Что-то сломалось" in str(exc.value)

    def test_parse_error_inheritance(self):
        with pytest.raises(fpx_err.FpxError):
            raise fpx_err.FpxParseError("HTML сломан")

    def test_account_error_inheritance(self):
        with pytest.raises(fpx_err.FpxError):
            raise fpx_err.FpxAccountError("Не удалось войти")

    def test_runner_error_inheritance(self):
        with pytest.raises(fpx_err.FpxError):
            raise fpx_err.FpxRunnerError("Раннер упал")

    def test_specific_errors_all_inherit_fpxerror(self):
        errors = [
            fpx_err.FpxGetChatsError(),
            fpx_err.FpxMessageDeliverError(),
            fpx_err.FpxRaisingLotError(),
            fpx_err.FpxRefundError(),
            fpx_err.FpxRequestError(),
            fpx_err.FpxLotEditingError(),
            fpx_err.FpxAnswerReviewError(),
            fpx_err.FpxDeleteReviewError(),
            fpx_err.FpxClientNotAttachedError(),
            fpx_err.FpxGetGameIDError(),
            fpx_err.FpxGetLastCategoryLotError(),
            fpx_err.FpxGetChatDataError(),
            fpx_err.FpxBanChatError(),
            fpx_err.FpxGetLotEditorInfoError(),
            fpx_err.FpxGetLotInfoError(),
            fpx_err.FpxGetOrderInfoError(),
            fpx_err.FpxGetUserDataError(),
            fpx_err.FpxGetUserSellsError(),
            fpx_err.FpxGetProfileError(),
            fpx_err.FpxNullDataError(),
            fpx_err.FpxCriticalRunnerError(),
            fpx_err.FpxAttributeError(),
            fpx_err.FpxCommandArgsError("cmd", "arg"),
        ]
        for err in errors:
            assert isinstance(err, fpx_err.FpxError)
            assert str(err)

    def test_null_data_error_is_parse_error(self):
        err = fpx_err.FpxNullDataError("Нет данных")
        assert isinstance(err, fpx_err.FpxParseError)
        assert isinstance(err, fpx_err.FpxError)

    def test_critical_runner_error_is_runner_error(self):
        err = fpx_err.FpxCriticalRunnerError("Раннер упал")
        assert isinstance(err, fpx_err.FpxRunnerError)
        assert isinstance(err, fpx_err.FpxError)

    def test_client_not_attached_is_account_error(self):
        err = fpx_err.FpxClientNotAttachedError()
        assert isinstance(err, fpx_err.FpxAccountError)

    def test_delete_review_error_is_account_error(self):
        err = fpx_err.FpxDeleteReviewError()
        assert isinstance(err, fpx_err.FpxAccountError)
        assert str(err)

    def test_lot_not_found_is_lot_editor_info_error(self):
        err = fpx_err.FpxLotNotFoundError(lot_id="1", error_message="Лот не найден")
        assert isinstance(err, fpx_err.FpxGetLotEditorInfoError)
        assert isinstance(err, fpx_err.FpxAccountError)
        assert (err.lot_id, err.error_message) == ("1", "Лот не найден")
        assert str(err)

    def test_lot_save_error_is_lot_editing_error(self):
        err = fpx_err.FpxLotSaveError(lot_id="1", errors={"price": "Слишком низкая"})
        assert isinstance(err, fpx_err.FpxLotEditingError)
        assert err.errors == {"price": "Слишком низкая"}
        assert err.error_message is None
        assert fpx_err.FpxLotSaveError().errors == {}

    def test_get_my_lots_error_is_account_error(self):
        err = fpx_err.FpxGetMyLotsError()
        assert isinstance(err, fpx_err.FpxAccountError)
        assert str(err)
