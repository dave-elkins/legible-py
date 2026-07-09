# Pet Store — Concept Design Reference Application

A running demonstration of the WYSIWID sync engine, showing how
independent concepts are composed through declarative sync rules.

## Concepts

| File | Actions | Purpose |
|---|---|---|
| `concepts/inventory.py` | `Inventory/check` | Checks pet availability and price |
| `concepts/order.py` | `Order/create` | Creates a purchase order |
| `concepts/billing.py` | `Billing/charge` | Charges the customer |
| `concepts/web.py` | `Web/respond` | Sends HTTP response |

## Sync Rules

Defined in `syncs/purchase.py` — the six rules that coordinate the
purchase flow:

1. `CheckInventory` — trigger inventory lookup on purchase request
2. `PlaceOrderIfInStock` — create order when stock confirmed
3. `RejectIfOutOfStock` — return 404 when unavailable
4. `BillCustomer` — charge after order creation
5. `SendReceipt` — respond with receipt on payment
6. `HandleLlmRecommendation` — handle async LLM recommendations

## Running

```bash
# From the repo root — install with web extras
pip install -e ".[web]"

# FastAPI server
uvicorn examples.petstore.app:app --reload
```

### Three purchase paths

```bash
# 200 — pet_1 is in stock
curl -X POST http://localhost:8000/purchase \
  -H 'Content-Type: application/json' \
  -d '{"pet_id":"pet_1","customer_id":"alice"}'

# 404 — pet_2 is out of stock
curl -X POST http://localhost:8000/purchase \
  -H 'Content-Type: application/json' \
  -d '{"pet_id":"pet_2","customer_id":"bob"}'

# 500 — pet_3 triggers a simulated infrastructure error
curl -X POST http://localhost:8000/purchase \
  -H 'Content-Type: application/json' \
  -d '{"pet_id":"pet_3","customer_id":"charlie"}'
```

### LLM trigger (fire-and-observe)

```bash
curl -X POST http://localhost:8000/llm/response \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"conv_1","text":"recommendation"}'
```

### Trace endpoint

```bash
# After a purchase, inspect the flow
curl http://localhost:8000/trace/<flow_token>
```

### CLI (no server needed)

```bash
python -m examples.petstore.cli pet_1 alice
python -m examples.petstore.cli pet_2 bob
```

## Testing

```bash
# From repo root
python -m pytest tests/test_petstore.py --asyncio-mode=auto -v
```
