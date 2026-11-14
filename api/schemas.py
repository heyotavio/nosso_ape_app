from datetime import date as DateType
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

Money = Decimal
Status = Literal['Cotado', 'Aprovado', 'Recusado', 'Pago']


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=1)


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    limit: Money = Field(ge=0, le=999999999999)

    @field_validator('name')
    @classmethod
    def strip_name(cls, s):
        if not s.strip():
            raise ValueError('Informe o nome da categoria')
        return s.strip()


class ExpenseInput(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=120)
    amount: Money = Field(gt=0, le=999999999999)
    status: Status = 'Cotado'
    item_name: str = Field(default='', max_length=500)
    cash_price: Money | None = Field(default=None, ge=0, le=999999999999)
    installment_total: Money | None = Field(default=None, ge=0, le=999999999999)
    payment_method: Literal['avista', 'parcelado'] = 'avista'
    installments_count: int = Field(default=1, ge=1, le=120)
    first_due_date: DateType | None = None
    date: DateType = Field(default_factory=DateType.today)
    supplier: str = Field(default='', max_length=300)
    notes: str = Field(default='', max_length=10000)
    source: str = Field(default='', max_length=500)
    product_url: str | None = Field(default=None, max_length=2048)

    @field_validator('product_url')
    @classmethod
    def validate_product_url(cls, value):
        if not value or not value.strip():
            return None
        from urllib.parse import urlsplit
        url = value.strip()
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            raise ValueError('Informe um link HTTP ou HTTPS valido')
        return url

    @model_validator(mode='after')
    def check_payment(self):
        if self.payment_method == 'parcelado' and (self.installment_total is None or self.installment_total <= 0):
            raise ValueError('Valor total a prazo obrigatorio para pagamento parcelado')
        return self

    @field_validator('description', 'category')
    @classmethod
    def not_blank(cls, s):
        if not s.strip():
            raise ValueError('Campo obrigatorio')
        return s.strip()


class ExpenseState(ExpenseInput):
    id: str = Field(min_length=1, max_length=64)


class StateInput(BaseModel):
    version: int = Field(ge=0)
    categories: list[CategoryInput] = Field(max_length=500)
    expenses: list[ExpenseState] = Field(max_length=10000)


class InstallmentPayment(BaseModel):
    paid: bool
    paid_at: DateType | None = None
