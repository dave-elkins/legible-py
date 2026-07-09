from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Pet:
    available: bool
    price: float


@dataclass
class InventoryState:
    catalogue: Dict[str, Pet] = field(default_factory=lambda: {
        "pet_1": Pet(available=True, price=250.0),
        "pet_2": Pet(available=False, price=0.0),
    })


def check(
    state: InventoryState,
    inputs: dict,
) -> tuple[InventoryState, dict]:
    pet_id = inputs.get("pet_id", "")
    pet = state.catalogue.get(pet_id)

    if pet is None:
        return state, {"error": f"Pet '{pet_id}' not found in catalogue"}

    return state, {"available": pet.available, "price": pet.price}
