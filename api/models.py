from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import String, Text, ForeignKey, Numeric, Date, DateTime, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'usuarios'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Category(Base):
    __tablename__ = 'categorias'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal('0'), nullable=False)
    expenses: Mapped[list['Expense']] = relationship(back_populates='category')


class Expense(Base):
    __tablename__ = 'orcamentos'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    supplier: Mapped[str] = mapped_column(String(300), default='', nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey('categorias.id', ondelete='RESTRICT'), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default='Cotado', nullable=False)
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default='', nullable=False)
    source: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    item_name: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    cash_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    installment_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20), default='avista', nullable=False)
    installments_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    installments: Mapped[list['Installment']] = relationship(back_populates='expense', cascade='all, delete-orphan', order_by='Installment.number')
    category: Mapped['Category'] = relationship(back_populates='expenses')


class Revision(Base):
    __tablename__ = 'revisao'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Installment(Base):
    __tablename__ = 'parcelas'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[str] = mapped_column(ForeignKey('orcamentos.id', ondelete='CASCADE'), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    expense: Mapped['Expense'] = relationship(back_populates='installments')
