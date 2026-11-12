from datetime import date
from api.db import engine
from api.models import Expense
from test_api import client_auth
from sqlalchemy.orm import Session


def test_three_quotes_approved_only_one_and_payments():
    client, h = client_auth()
    client.post('/api/categorias', headers=h, json={'name':'Marcenaria','limit':'50000'})
    for name, status, cash, credit in [('Fornecedor A', 'Recusado', '1000', '1200'), ('Fornecedor B', 'Cotado', '900', '1100'), ('Fornecedor C', 'Aprovado', '950', '1100')]:
        response = client.post('/api/orcamentos', headers=h, json={
            'description': 'Armarios', 'item_name': 'Armarios da cozinha', 'category': 'Marcenaria',
            'supplier': name, 'status': status, 'amount': cash, 'cash_price': cash,
            'installment_total': credit, 'payment_method': 'parcelado',
            'installments_count': 10, 'first_due_date': '2027-01-31', 'date': '2026-11-12'
        })
        assert response.status_code == 201, response.text
        if name == 'Fornecedor C':
            chosen = response.json()
    assert chosen['amount'] == 1100
    assert len(chosen['installments']) == 10
    assert chosen['installments'][1]['due_date'] == '2027-02-28'
    assert sum(p['amount'] for p in chosen['installments']) == 1100
    assert client.get('/api/dashboard', headers=h).json()['comprometido'] >= 1100
    twice = client.post('/api/orcamentos', headers=h, json={
        'description':'Armarios','item_name':'Armarios da cozinha','category':'Marcenaria',
        'amount': '1000', 'status': 'Aprovado'
    })
    assert twice.status_code == 409, twice.text
    first_id = chosen['installments'][0]['id']
    paid = client.patch(f'/api/parcelas/{first_id}', headers=h, json={'paid': True, 'paid_at':'2027-01-31'})
    assert paid.status_code == 200, paid.text
    assert paid.json()['amount_paid'] == 110
    summary = client.get('/api/dashboard', headers=h).json()
    assert summary['pago'] >= 110
    # Não permitir apagar lançamento já pago.
    assert client.delete('/api/orcamentos/'+chosen['id'], headers=h).status_code == 409
    # Não permitir alterar cronograma depois de registrar pagamento.
    update = client.patch('/api/orcamentos/'+chosen['id'], headers=h, json={
        'description':'Armarios','item_name':'Armarios da cozinha','category':'Marcenaria',
        'amount': '1500', 'cash_price': '950','installment_total':'1500',
        'status':'Aprovado', 'payment_method':'parcelado','installments_count':10,'first_due_date':'2027-01-31'
    })
    assert update.status_code == 409, update.text
    second_user = client.post('/api/auth/login', json={'email':'esposa@example.com','senha':'outra-senha-de-teste-longa'})
    assert second_user.status_code == 200
    other_h = {'Authorization': 'Bearer '+second_user.json()['access_token']}
    installments = client.get('/api/parcelas', headers=other_h).json()
    assert any(p['id']==first_id and p['paid_at']=='2027-01-31' for p in installments)
