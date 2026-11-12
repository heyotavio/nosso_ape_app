"""Migração aditiva v2 -> v3. Nunca remove tabelas ou dados.
Execute backup pg_dump ANTES de executar. Idempotente no PostgreSQL.
"""
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from api.db import engine, Base
from api.models import Revision

ADDITIONS = {
    'item_name': "VARCHAR(500) NOT NULL DEFAULT ''",
    'cash_price': 'NUMERIC(14,2)',
    'installment_total': 'NUMERIC(14,2)',
    'payment_method': "VARCHAR(20) NOT NULL DEFAULT 'avista'",
    'installments_count': 'INTEGER NOT NULL DEFAULT 1',
    'first_due_date': 'DATE',
}

def main():
    eng = engine()
    if eng.dialect.name != 'postgresql':
        raise RuntimeError('Migração de produção exige PostgreSQL')
    with eng.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(38762026)'))
        tables = inspect(connection).get_table_names()
        if 'orcamentos' not in tables:
            raise RuntimeError('Banco não inicializado: execute scripts.init_db da versão 2 primeiro')
        cols = {c['name'] for c in inspect(connection).get_columns('orcamentos')}
        for name, definition in ADDITIONS.items():
            if name not in cols:
                connection.execute(text(f'ALTER TABLE orcamentos ADD COLUMN {name} {definition}'))
        connection.execute(text("UPDATE orcamentos SET item_name = description WHERE item_name = ''"))
        connection.execute(text('UPDATE orcamentos SET cash_price = amount WHERE cash_price IS NULL'))
        connection.execute(text('UPDATE orcamentos SET installment_total = amount WHERE installment_total IS NULL'))
    Base.metadata.create_all(eng, checkfirst=True)
    # Preserva estado legado Pago como parcela quitada; outros aprovados como parcelas pendentes.
    from api.models import Expense, Installment
    from sqlalchemy import select
    with Session(eng) as session:
        expenses = session.scalars(select(Expense).where(Expense.status.in_(['Pago','Aprovado']))).all()
        for e in expenses:
            exists = session.scalar(select(Installment.id).where(Installment.expense_id==e.id).limit(1))
            if exists is not None:
                continue
            session.add(Installment(expense_id=e.id, number=1, amount=e.amount,
                                    due_date=e.date, paid_at=e.date if e.status=='Pago' else None,
                                    amount_paid=e.amount if e.status=='Pago' else None))
        session.commit()
    print('Migração 3.0 concluída. Dados antigos preservados.')

if __name__ == '__main__':
    main()
