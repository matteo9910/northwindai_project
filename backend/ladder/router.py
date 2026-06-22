from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.config import Settings, get_settings
from backend.ladder.supplier_products import (
    SupplierProductsResponse,
    answer_supplier_products,
)
from backend.ladder.top_customers import TopCustomersResponse, answer_top_customers

router = APIRouter(prefix="/ladder", tags=["ladder"])


@router.get("/top-customers", response_model=TopCustomersResponse)
def top_customers(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TopCustomersResponse:
    return answer_top_customers(settings=settings)


@router.get("/supplier-products", response_model=SupplierProductsResponse)
def supplier_products(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SupplierProductsResponse:
    return answer_supplier_products(settings=settings)
