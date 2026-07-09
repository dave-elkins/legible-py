from __future__ import annotations

from legible.engine import ActionPattern, Sync, Var


def get_purchase_rules():
    return [
        Sync("CheckInventory")
        .when(ActionPattern(
            "Web/purchase_request",
            inputs={"pet_id": Var("pet_id"), "customer_id": Var("cust_id")},
            outputs={},
        ))
        .then(ActionPattern("Inventory/check", inputs={"pet_id": Var("pet_id")}))
        .build(),

        Sync("PlaceOrderIfInStock")
        .when(
            ActionPattern(
                "Web/purchase_request",
                inputs={"pet_id": Var("pet_id"), "customer_id": Var("cust_id")},
                outputs={},
            ),
            ActionPattern(
                "Inventory/check",
                inputs={"pet_id": Var("pet_id")},
                outputs={"available": True, "price": Var("price")},
            ),
        )
        .then(ActionPattern(
            "Order/create",
            inputs={
                "pet_id": Var("pet_id"),
                "customer_id": Var("cust_id"),
                "amount": Var("price"),
            },
        ))
        .build(),

        Sync("RejectIfOutOfStock")
        .when(
            ActionPattern(
                "Web/purchase_request",
                inputs={"pet_id": Var("pet_id")},
                outputs={},
            ),
            ActionPattern(
                "Inventory/check",
                inputs={"pet_id": Var("pet_id")},
                outputs={"available": False},
            ),
        )
        .then(ActionPattern(
            "Web/respond",
            inputs={"status": 404, "message": "Pet is out of stock."},
        ))
        .build(),

        Sync("BillCustomer")
        .when(ActionPattern(
            "Order/create",
            inputs={"amount": Var("price")},
            outputs={"order_id": Var("order_id")},
        ))
        .then(ActionPattern(
            "Billing/charge",
            inputs={"order_id": Var("order_id"), "amount": Var("price")},
        ))
        .build(),

        Sync("SendReceipt")
        .when(ActionPattern(
            "Billing/charge",
            inputs={"order_id": Var("order_id")},
            outputs={"status": "paid", "receipt_id": Var("rcpt")},
        ))
        .then(ActionPattern(
            "Web/respond",
            inputs={"status": 200, "message": "Pet purchased!", "receipt": Var("rcpt")},
        ))
        .build(),

        Sync("HandleLlmRecommendation")
        .when(ActionPattern(
            "Llm/response",
            inputs={"conversation_id": Var("conv_id")},
            outputs={},
        ))
        .then(ActionPattern(
            "Web/respond",
            inputs={"status": 200, "source": "llm", "conversation_id": Var("conv_id")},
        ))
        .build(),
    ]
