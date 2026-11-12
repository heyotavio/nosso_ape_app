from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .auth import current_user, verify_password, make_token
from .config import settings
from .db import get_db
from .models import User, Category, Expense, Revision, Installment
from .schemas import LoginInput, CategoryInput, ExpenseInput, StateInput, InstallmentPayment
from .service import (
    revision_locked, list_categories, list_expenses, cat_to_dict, expense_to_dict,
    resolve_cat, apply_expense, reconcile_installments, assert_single_approved, installment_to_dict, summary, replace_state,
)

# Evita inicializar um DB sem as variaveis de ambiente em /docs e em teste automatizado.
app = FastAPI(title='Nosso Apê API', version='3.0.0', docs_url='/docs')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().origins,
    allow_credentials=False,  # Autenticacao com Authorization: Bearer, nao cookies cross-site
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type'],
)


@app.get('/health')
def health():
    return {'status': 'ok', 'app': 'nosso-ape-api'}


@app.post('/api/auth/login')
def login(body: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    # Nao diferencia usuario inexistente de senha errada.
    if not user or not user.active or not verify_password(body.senha, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Email ou senha invalidos')
    return {'access_token': make_token(user.id), 'token_type': 'bearer',
            'expires_in': settings().token_expiration_minutes * 60}


@app.get('/api/me')
def whoami(user: User = Depends(current_user)):
    return {'id': user.id, 'email': user.email}


@app.get('/api/categorias')
def categories(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [cat_to_dict(c) for c in list_categories(db)]


@app.post('/api/categorias', status_code=201)
def add_category(body: CategoryInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rev = revision_locked(db)
    cat = Category(name=body.name, limit=body.limit)
    db.add(cat)
    rev.version += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Categoria ja cadastrada')
    return cat_to_dict(cat)


@app.put('/api/categorias/{category_id}')
def update_category(category_id: int, body: CategoryInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rev = revision_locked(db)
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, 'Categoria nao encontrada')
    cat.name, cat.limit = body.name, body.limit
    rev.version += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Nome de categoria duplicado')
    return cat_to_dict(cat)


@app.delete('/api/categorias/{category_id}', status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rev = revision_locked(db)
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, 'Categoria nao encontrada')
    if db.scalar(select(Expense.id).where(Expense.category_id == category_id).limit(1)):
        raise HTTPException(409, 'Categoria possui orcamentos. Mova-os antes de excluir.')
    db.delete(cat)
    rev.version += 1
    db.commit()


@app.get('/api/orcamentos')
def expenses(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [expense_to_dict(e) for e in list_expenses(db)]


@app.post('/api/orcamentos', status_code=201)
def add_expense(body: ExpenseInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rev = revision_locked(db)
    category = resolve_cat(db, body.category)
    obj = Expense(id=str(uuid4()), created_by_id=user.id)
    apply_expense(obj, body, category)
    db.add(obj)
    db.flush()
    assert_single_approved(db)
    reconcile_installments(db, obj)
    rev.version += 1
    db.commit()
    db.refresh(obj)
    return expense_to_dict(obj)


@app.patch('/api/orcamentos/{expense_id}')
def update_expense(expense_id: str, body: ExpenseInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rev = revision_locked(db)
    obj = db.get(Expense, expense_id)
    if not obj:
        raise HTTPException(404, 'Orcamento nao encontrado')
    category = resolve_cat(db, body.category)
    apply_expense(obj, body, category)
    db.flush()
    assert_single_approved(db)
    reconcile_installments(db, obj)
    rev.version += 1
    db.commit()
    db.refresh(obj)
    return expense_to_dict(obj)


@app.delete('/api/orcamentos/{expense_id}', status_code=204)
def delete_expense(expense_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rev = revision_locked(db)
    obj = db.get(Expense, expense_id)
    if not obj:
        raise HTTPException(404, 'Orcamento nao encontrado')
    if any(i.paid_at for i in obj.installments):
        raise HTTPException(409, 'Não exclua propostas com pagamentos registrados')
    db.delete(obj)
    rev.version += 1
    db.commit()


@app.get('/api/dashboard')
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return summary(db)


@app.get('/api/estado')
def get_state(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rev = db.get(Revision, 1)
    return {'version': rev.version if rev else 0, 'categories': [cat_to_dict(c) for c in list_categories(db)],
            'expenses': [expense_to_dict(e) for e in list_expenses(db)], 'demo': False}


@app.put('/api/estado')
def put_state(body: StateInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {'version': replace_state(db, body, user.id), 'saved': True}


@app.get('/api/parcelas')
def installments(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Installment).order_by(Installment.due_date, Installment.id)).all()
    return [installment_to_dict(i) for i in rows]


@app.patch('/api/parcelas/{installment_id}')
def mark_installment(installment_id: int, body: InstallmentPayment, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from datetime import date
    rev = revision_locked(db)
    row = db.get(Installment, installment_id)
    if not row:
        raise HTTPException(404, 'Parcela não encontrada')
    if not body.paid and row.paid_at is None:
        return installment_to_dict(row)
    row.paid_at = (body.paid_at or date.today()) if body.paid else None
    row.amount_paid = row.amount if body.paid else None
    rev.version += 1
    db.commit()
    db.refresh(row)
    return installment_to_dict(row)
