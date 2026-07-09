from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Charge:
    order_id: str
    amount: float
    receipt_id: str


@dataclass
class BillingState:
    charges: Dict[str, Charge] = field(default_factory=dict)
    next_receipt: int = 1


def charge(
    state: BillingState,
    inputs: dict,
) -> tuple[BillingState, dict]:
    receipt_id = f"rcpt_{state.next_receipt:04d}"
    order_id = inputs.get("order_id", "")
    new_charge = Charge(
        order_id=order_id,
        amount=inputs.get("amount", 0.0),
        receipt_id=receipt_id,
    )
    new_charges = {**state.charges, receipt_id: new_charge}
    new_state = BillingState(
        charges=new_charges,
        next_receipt=state.next_receipt + 1,
    )
    return new_state, {"status": "paid", "receipt_id": receipt_id}
