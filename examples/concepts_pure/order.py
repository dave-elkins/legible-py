from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Order:
    pet_id: str
    customer_id: str
    amount: float
    status: str


@dataclass
class OrderState:
    orders: Dict[str, Order] = field(default_factory=dict)
    next_id: int = 1


def create(
    state: OrderState,
    inputs: dict,
) -> tuple[OrderState, dict]:
    order_id = f"ord_{state.next_id:04d}"
    order = Order(
        pet_id=inputs.get("pet_id", ""),
        customer_id=inputs.get("customer_id", ""),
        amount=inputs.get("amount", 0.0),
        status="pending",
    )
    new_orders = {**state.orders, order_id: order}
    new_state = OrderState(orders=new_orders, next_id=state.next_id + 1)
    return new_state, {"order_id": order_id, "status": "pending"}
