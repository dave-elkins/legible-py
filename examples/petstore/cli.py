from __future__ import annotations

import sys

from examples.petstore.concepts.billing import charge as billing_charge
from examples.petstore.concepts.inventory import check as inventory_check
from examples.petstore.concepts.order import create as order_create
from examples.petstore.concepts.web import respond as web_respond
from examples.petstore.syncs.purchase import get_purchase_rules
from legible.engine import (
    AppDispatcher,
    CliTrigger,
    FlowGateway,
    InMemoryBus,
    SQLiteFlowStore,
    SyncEngine,
)


def main() -> None:
    bus = InMemoryBus()
    dispatcher = AppDispatcher(bus)
    gateway = FlowGateway(bus, terminal_namespace="Web/respond")

    dispatcher.register_action("Inventory/check", inventory_check)
    dispatcher.register_action("Order/create", order_create)
    dispatcher.register_action("Billing/charge", billing_charge)
    dispatcher.register_action("Web/respond", web_respond)

    async def _boot():
        store = await SQLiteFlowStore.create(":memory:")
        engine = SyncEngine(bus, store, dispatcher, get_purchase_rules())
        await engine.start()
        await gateway.listen()

    trigger = CliTrigger(
        bus=bus,
        gateway=gateway,
        namespace="Web/purchase_request",
        engine_starters=[_boot],
    )

    pet_id = sys.argv[1] if len(sys.argv) > 1 else "pet_1"
    customer_id = sys.argv[2] if len(sys.argv) > 2 else "cli_user"

    trigger.run({"pet_id": pet_id, "customer_id": customer_id})


if __name__ == "__main__":
    main()
