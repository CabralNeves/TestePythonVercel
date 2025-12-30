from pydantic import BaseModel, Field
from typing import List, Optional


class BudgetItem(BaseModel):
	description: str = Field(min_length=1)
	quantity: int = Field(ge=1, description="Quantidade do item")
	unit_price: float = Field(ge=0, description="Preço unitário")


class BudgetRequest(BaseModel):
	company_name: Optional[str] = "Minha Empresa"
	company_email: Optional[str] = None
	client_name: Optional[str] = None
	client_email: Optional[str] = None
	currency: str = "R$"
	discount_percent: Optional[float] = 0.0
	tax_percent: Optional[float] = 0.0
	notes: Optional[str] = None
	items: List[BudgetItem]


