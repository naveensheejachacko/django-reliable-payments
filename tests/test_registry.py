import pytest

from payments.registry import PaymentHandler, UnknownPaymentKind, get_handler, register, registered_kinds


def test_built_in_handlers_are_registered():
    assert {"booking", "subscription"} <= set(registered_kinds())


def test_unknown_kind_raises():
    with pytest.raises(UnknownPaymentKind):
        get_handler("does-not-exist")


def test_a_kind_can_only_be_registered_once():
    with pytest.raises(ValueError):

        @register("booking")
        class Duplicate(PaymentHandler):
            def on_paid(self, order):
                pass
