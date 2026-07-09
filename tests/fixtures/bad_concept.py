import asyncio

from concepts.order import OrderState

_registry: OrderState = {}


async def get(inputs: dict):
    return {"name": inputs["name"]}


async def process(inputs: dict) -> None:
    pass


def bad_where(bindings: dict):
    _registry["last"] = bindings["val"]

    async def _fetch():
        await asyncio.sleep(0.01)

    return [bindings]
