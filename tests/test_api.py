import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

TMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(TMP.name) / 'test.db')
os.environ['APP_SECRET_KEY'] = 'test-only-secret-for-automated-checks-987654321'
os.environ['CORS_ORIGINS'] = 'http://localhost:8080'
from api.db import Base, engine  # noqa: E402
from api.models import User, Revision  # noqa: E402
from api.auth import hash_password  # noqa: E402
from api.main import app  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def setup_module(module):
    db_engine = engine()
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as session:
        session.add(Revision(id=1, version=0))
        session.add(User(email='casal@example.com', password_hash=hash_password('uma-senha-de-teste-longa')))
        session.add(User(email='esposa@example.com', password_hash=hash_password('outra-senha-de-teste-longa')))
        session.commit()


def client_auth():
    client = TestClient(app)
    result = client.post('/api/auth/login', json={'email': 'casal@example.com', 'senha': 'uma-senha-de-teste-longa'})
    assert result.status_code == 200, result.text
    return client, {'Authorization': 'Bearer ' + result.json()['access_token']}


def test_auth_required():
    client = TestClient(app)
    assert client.get('/health').json()['status'] == 'ok'
    assert client.get('/api/orcamentos').status_code in (401, 403)
    assert client.post('/api/auth/login', json={'email': 'casal@example.com', 'senha': 'errada'}).status_code == 401


def test_crud_dashboard_and_conflict():
    client, h = client_auth()
    c = client.post('/api/categorias', json={'name': 'Marcenaria', 'limit': '30000.00'}, headers=h)
    assert c.status_code == 201, c.text
    assert client.post('/api/categorias', json={'name': 'Marcenaria', 'limit': 10}, headers=h).status_code == 409
    cid = c.json()['id']
    q = client.post('/api/orcamentos', json={
        'description': 'Armarios cozinha', 'category': 'Marcenaria',
        'amount': '18000.34', 'status': 'Cotado', 'date': '2026-11-11',
        'supplier': 'Marcenaria A'
    }, headers=h)
    assert q.status_code == 201, q.text
    qid = q.json()['id']
    assert client.get('/api/dashboard', headers=h).json()['cotado'] == 18000.34
    edit = client.patch(f'/api/orcamentos/{qid}', json={
        'description': 'Armarios cozinha', 'category': 'Marcenaria',
        'amount': '17000.00', 'status': 'Aprovado', 'date': '2026-11-11',
    }, headers=h)
    assert edit.status_code == 200, edit.text
    result = client.get('/api/dashboard', headers=h).json()
    assert result['comprometido'] == 17000.00
    assert result['saldo'] == 13000.00
    state = client.get('/api/estado', headers=h).json()
    old_version = state['version']
    body = {
        'version': old_version, 'categories': [{'name': 'Reforma', 'limit': '1000.00'}],
        'expenses': [{'id': qid, 'description': 'Tinta', 'category': 'Reforma',
                      'amount': '120.00', 'status': 'Pago', 'date': '2026-11-11'}],
    }
    updated = client.put('/api/estado', json=body, headers=h)
    assert updated.status_code == 200, updated.text
    assert updated.json()['version'] == old_version + 1
    assert client.put('/api/estado', json=body, headers=h).status_code == 409
    assert client.get('/api/dashboard', headers=h).json()['pago'] == 120.00
    reforma_id = client.get('/api/categorias', headers=h).json()[0]['id']
    assert client.delete(f'/api/categorias/{reforma_id}', headers=h).status_code == 409
    invalid = client.post('/api/orcamentos', json={'description': 'A', 'category': 'Reforma', 'amount': -2}, headers=h)
    assert invalid.status_code == 422
    assert client.get('/api/estado', headers=h).json()['expenses'][0]['id'] == qid


def test_second_user_reads_same_budget():
    client = TestClient(app)
    token = client.post('/api/auth/login', json={'email': 'esposa@example.com', 'senha': 'outra-senha-de-teste-longa'})
    assert token.status_code == 200
    result = client.get('/api/dashboard', headers={'Authorization': 'Bearer ' + token.json()['access_token']})
    assert result.status_code == 200
    assert result.json()['planejado'] == 1000.00
    assert result.json()['pago'] == 120.00
