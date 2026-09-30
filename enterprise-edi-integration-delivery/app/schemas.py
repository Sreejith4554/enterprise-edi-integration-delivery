"""Version-one transport-independent canonical purchase order."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Code = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Address(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    street: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=80)
    postal_code: str = Field(min_length=1, max_length=20)
    country: str = Field(pattern=r"^[A-Z]{2}$")


class Item(StrictModel):
    line_number: int = Field(gt=0, strict=True)
    sku: Code
    description: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: Literal["EA"]
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class CanonicalPurchaseOrder(StrictModel):
    external_order_id: Code
    customer_id: Code
    order_date: date
    currency: Literal["EUR", "USD", "GBP"]
    requested_delivery_date: date
    ship_to: Address
    items: list[Item] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def coherent(self):
        if self.requested_delivery_date < self.order_date:
            raise ValueError("Delivery date must not precede order date")
        if len({i.line_number for i in self.items}) != len(self.items):
            raise ValueError("Line numbers must be unique")
        return self


def business_validate(order: CanonicalPurchaseOrder):
    if order.customer_id != "NORDIC-001":
        raise ValueError("Unknown customer; use NORDIC-001")
    for item in order.items:
        if item.sku not in {"ATLAS-100", "ATLAS-200"}:
            raise ValueError(f"Unknown SKU: {item.sku}")
