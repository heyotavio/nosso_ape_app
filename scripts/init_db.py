from sqlalchemy import text, inspect
from api.db import Base, engine
from api.models import Revision, User, Category, Expense
from sqlalchemy.orm import Session


def main():
    db_engine = engine()
    old = inspect(db_engine).get_table_names()
    if 'orcamentos' in old and 'cash_price' not in {c['name'] for c in inspect(db_engine).get_columns('orcamentos')}:
        raise RuntimeError('Banco v2 detectado. Execute primeiro: python -m scripts.migrate_v3')
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as session:
        if session.get(Revision, 1) is None:
            session.add(Revision(id=1, version=0))
            session.commit()
        print('Banco inicializado: tabelas usuarios, categorias, orcamentos, revisao.')


if __name__ == '__main__':
    main()
