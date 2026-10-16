class FakeGateway:
    """Records refunds instead of calling Razorpay."""

    refunds: list[dict] = []

    def refund(self, payment_id: str, amount_paise: int, reason: str) -> dict:
        record = {"payment_id": payment_id, "amount": amount_paise, "reason": reason}
        FakeGateway.refunds.append(record)
        return {"id": f"rfnd_{len(FakeGateway.refunds)}", **record}
