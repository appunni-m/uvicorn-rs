"""FastAPI workloads for comparing identical Python framework code on ASGI servers."""

from fastapi import FastAPI, Query
from pydantic import BaseModel


app = FastAPI()


class ItemResponse(BaseModel):
    item_id: int
    name: str
    active: bool
    labels: list[str]


class CpuResponse(BaseModel):
    iterations: int
    checksum: int


@app.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int, repeat: int = Query(default=1, ge=1, le=5)
) -> ItemResponse:
    """Exercise route matching, parameter validation, and response serialization."""
    return ItemResponse(
        item_id=item_id * repeat,
        name=f"item-{item_id}",
        active=True,
        labels=["python", "asgi"],
    )


@app.get("/cpu/{iterations}", response_model=CpuResponse)
def python_cpu(iterations: int) -> CpuResponse:
    """Exercise a deterministic Python-heavy sync route and response validation."""
    checksum = 0
    for index in range(iterations):
        checksum = (checksum + (index * 17) % 251) % 1_000_003
    return CpuResponse(iterations=iterations, checksum=checksum)
