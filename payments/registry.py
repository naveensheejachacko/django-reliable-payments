"""Handler registry: one class per payment kind, looked up by a string key.

The webhook and the confirmation service never know what is being paid for.
Adding a new product means writing one handler class; nothing else changes.
"""

from abc import ABC, abstractmethod

_HANDLERS: dict[str, type["PaymentHandler"]] = {}


class UnknownPaymentKind(LookupError):
    pass


class PaymentHandler(ABC):
    kind: str

    @abstractmethod
    def on_paid(self, order) -> None:
        """Fulfil the order. Runs inside the confirmation transaction."""

    def on_failed(self, order) -> None:
        """Optional clean-up when a payment fails."""


def register(kind: str):
    def decorator(cls: type[PaymentHandler]) -> type[PaymentHandler]:
        if kind in _HANDLERS:
            raise ValueError(f"A handler is already registered for {kind!r}")
        cls.kind = kind
        _HANDLERS[kind] = cls
        return cls

    return decorator


def get_handler(kind: str) -> PaymentHandler:
    try:
        return _HANDLERS[kind]()
    except KeyError:
        raise UnknownPaymentKind(kind) from None


def registered_kinds() -> list[str]:
    return sorted(_HANDLERS)
