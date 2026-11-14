"""Migração aditiva: link do produto no orçamento. Execute após backup."""
from sqlalchemy import inspect, text
from api.db import engine

def main():
    eng = engine()
    if eng.dialect.name != 'postgresql':
        raise RuntimeError('Esta migração exige PostgreSQL')
    with eng.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(38762026)'))
        columns = {c['name'] for c in inspect(connection).get_columns('orcamentos')}
        if 'product_url' not in columns:
            connection.execute(text('ALTER TABLE orcamentos ADD COLUMN product_url VARCHAR(2048)'))
    print('Migração 3.4 concluída. Dados antigos preservados.')

if __name__ == '__main__':
    main()
