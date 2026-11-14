from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload
from .models import Category, Expense, Revision, Installment
from .schemas import CategoryInput, ExpenseInput, StateInput


def revision_locked(db: Session) -> Revision:
    version = db.scalar(select(Revision).where(Revision.id == 1).with_for_update())
    if version is None:
        # Inicializado em scripts/init_db.py, e preenchido aqui como fallback.
        version = Revision(id=1, version=0)
        db.add(version)
        db.flush()
    return version


def list_categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)).all())


def list_expenses(db: Session) -> list[Expense]:
    return list(db.scalars(select(Expense).options(joinedload(Expense.category), selectinload(Expense.installments)).order_by(Expense.date.desc(), Expense.created_at.desc())).all())


def cat_to_dict(cat: Category):
    return {'id': cat.id, 'name': cat.name, 'limit': float(cat.limit)}


def installment_to_dict(i: Installment):
    return {'id': i.id, 'expense_id': i.expense_id, 'number': i.number,
            'amount': float(i.amount), 'due_date': i.due_date.isoformat(),
            'paid_at': i.paid_at.isoformat() if i.paid_at else None,
            'amount_paid': float(i.amount_paid) if i.amount_paid is not None else None,
            'status': 'Pago' if i.paid_at else ('Atrasado' if i.due_date < date.today() else 'Pendente')}


def expense_to_dict(e: Expense):
    return {'id': e.id, 'description': e.description, 'supplier': e.supplier,
            'category': e.category.name, 'amount': float(e.amount), 'status': e.status,
            'date': e.date.isoformat(), 'notes': e.notes, 'source': e.source, 'product_url': e.product_url,
            'item_name': e.item_name or e.description,
            'cash_price': float(e.cash_price) if e.cash_price is not None else float(e.amount),
            'installment_total': float(e.installment_total) if e.installment_total is not None else None,
            'payment_method': e.payment_method, 'installments_count': e.installments_count,
            'first_due_date': e.first_due_date.isoformat() if e.first_due_date else None,
            'installments': [installment_to_dict(i) for i in e.installments]}


def month_due(day: date, offset: int) -> date:
    from calendar import monthrange
    month_index = day.year * 12 + day.month - 1 + offset
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def approved_status(e: Expense):
    return e.status in ('Aprovado', 'Pago')


def apply_expense(e: Expense, item: ExpenseInput, category: Category):
    e.description = item.description
    e.supplier = item.supplier
    e.category_id = category.id
    e.date = item.date
    e.notes = item.notes
    e.source = item.source
    e.product_url = item.product_url
    e.item_name = item.item_name.strip() or item.description
    e.cash_price = item.cash_price if item.cash_price is not None else item.amount
    e.installment_total = item.installment_total if item.installment_total is not None else (item.amount if item.payment_method == 'parcelado' else None)
    e.payment_method = item.payment_method
    e.installments_count = item.installments_count if item.payment_method == 'parcelado' else 1
    e.first_due_date = item.first_due_date
    e.status = item.status
    if e.status == 'Pago' and not e.installments:
        # Compatibilidade com dados legados: gerar parcela quitada posteriormente.
        e.payment_method = 'avista'
        e.installments_count = 1
    e.amount = e.installment_total if e.payment_method == 'parcelado' else e.cash_price
    if e.amount <= 0:
        raise HTTPException(422, 'O valor contratado deve ser positivo')
    if e.status in ('Aprovado', 'Pago') and e.payment_method == 'parcelado' and not e.first_due_date:
        raise HTTPException(422, 'Informe a data do primeiro vencimento para compras parceladas')


def reconcile_installments(db: Session, e: Expense):
    if e.status not in ('Aprovado', 'Pago'):
        if any(i.paid_at for i in e.installments):
            raise HTTPException(409, 'Não é possível cancelar proposta com parcelas pagas')
        e.installments.clear()
        return
    count = e.installments_count
    due = e.first_due_date or (min(i.due_date for i in e.installments) if e.installments else date.today())
    cents = int((e.amount * 100).quantize(Decimal('1')))
    base, remainder = divmod(cents, count)
    expected = [(month_due(due, n), Decimal(base + (1 if n < remainder else 0)) / 100) for n in range(count)]
    existing = sorted(e.installments, key=lambda x: x.number)
    if any(i.paid_at for i in existing):
        if len(existing) != count or any(i.amount != amount or i.due_date != dt for i, (dt, amount) in zip(existing, expected)):
            raise HTTPException(409, 'Parcelas já pagas: não é possível alterar valor, quantidade ou vencimentos')
        return
    e.installments.clear()
    db.flush()
    for n, (dt, amount) in enumerate(expected, 1):
        obj = Installment(number=n, amount=amount, due_date=dt)
        if e.status == 'Pago':
            obj.paid_at = e.date
            obj.amount_paid = amount
        e.installments.append(obj)


def assert_single_approved(db: Session):
    # Agrupamento por categoria + nome do item. Um único contrato ativo por item.
    approved = list(db.scalars(select(Expense).where(Expense.status.in_(['Aprovado', 'Pago']))).all())
    names = set()
    for e in approved:
        key = (e.category_id, (e.item_name or e.description).strip().casefold())
        if key in names:
            raise HTTPException(409, f'Mais de uma proposta aprovada para o mesmo item: {e.item_name}')
        names.add(key)


def resolve_cat(db: Session, name: str) -> Category:
    cat = db.scalar(select(Category).where(Category.name == name))
    if not cat:
        raise HTTPException(422, detail=f'Categoria nao encontrada: {name}')
    return cat


def summary(db: Session):
    categories = list_categories(db)
    expenses = list_expenses(db)
    by_cat = {c.name: {'planned': float(c.limit), 'quoted': 0.0, 'approved': 0.0, 'paid': 0.0} for c in categories}
    proposals = {}
    selected = set()
    for e in expenses:
        key = (e.category_id, (e.item_name or e.description).strip().casefold())
        if approved_status(e):
            selected.add(key)
            by_cat[e.category.name]['approved'] += float(e.amount)
            by_cat[e.category.name]['paid'] += sum(float(i.amount_paid or 0) for i in e.installments if i.paid_at)
        elif e.status == 'Cotado':
            value = e.cash_price if e.cash_price is not None else e.amount
            proposals[key] = (e.category.name, min(value, proposals[key][1]) if key in proposals else value)
    quoted = Decimal('0')
    for key, (category, price) in proposals.items():
        if key not in selected:
            quoted += price
            by_cat[category]['quoted'] += float(price)
    planned = sum((c.limit for c in categories), Decimal('0'))
    paid = sum((i.amount_paid or Decimal('0') for e in expenses for i in e.installments if i.paid_at), Decimal('0'))
    approved = sum((e.amount for e in expenses if approved_status(e)), Decimal('0'))
    return {'planejado': float(planned), 'pago': float(paid), 'aprovado': float(approved),
            'cotado': float(quoted), 'comprometido': float(approved), 'a_pagar': float(approved-paid),
            'saldo': float(planned-approved),
            'percentual_utilizado': round(float(approved / planned * 100), 2) if planned else 0,
            'categorias': by_cat, 'total_orcamentos': len(expenses)}


def replace_state(db: Session, body: StateInput, actor_id: int):
    """Reconcilia o snapshot com versao otimista, mantendo IDs e registros existentes."""
    rev = revision_locked(db)
    if rev.version != body.version:
        raise HTTPException(409, detail=f'Conflito de edicao: servidor na versao {rev.version}. Recarregue os dados antes de salvar.')
    cat_names = [c.name for c in body.categories]
    expense_ids = [e.id for e in body.expenses]
    if len(cat_names) != len(set(cat_names)) or len(expense_ids) != len(set(expense_ids)):
        raise HTTPException(422, detail='Categorias ou IDs de orcamento duplicados')
    if any(e.category not in cat_names for e in body.expenses):
        raise HTTPException(422, detail='Orcamento com categoria ausente no planejamento')

    # Atualizar somente linhas alteradas para preservar IDs de itens existentes
    # e created_by/created_at. Nao apagamos e recriamos todas as linhas.
    existing_cats = {c.name: c for c in list_categories(db)}
    for c in body.categories:
        if c.name in existing_cats:
            existing_cats[c.name].limit = c.limit
        else:
            new_category = Category(name=c.name, limit=c.limit)
            db.add(new_category)
    db.flush()
    current_cats = {c.name: c for c in list_categories(db)}

    old_expenses = {e.id: e for e in list_expenses(db)}
    for item in body.expenses:
        e = old_expenses.get(item.id)
        if e is None:
            e = Expense(id=item.id, created_by_id=actor_id)
            db.add(e)
        apply_expense(e, item, current_cats[item.category])
    for expense_id, e in old_expenses.items():
        if expense_id not in expense_ids:
            if any(i.paid_at for i in e.installments):
                raise HTTPException(409, 'Há pagamentos no lançamento excluído. Não é possível apagá-lo.')
            db.delete(e)
    db.flush()

    for name, cat in existing_cats.items():
        if name not in cat_names:
            db.delete(cat)
    assert_single_approved(db)
    for e in list_expenses(db):
        reconcile_installments(db, e)
    rev.version += 1
    db.commit()
    return rev.version
