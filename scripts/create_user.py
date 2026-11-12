from getpass import getpass
from sqlalchemy import select
from sqlalchemy.orm import Session
from api.auth import hash_password
from api.db import engine
from api.models import User


def main():
    email = input('Email do usuario: ').strip().lower()
    if not email or '@' not in email:
        raise SystemExit('Email invalido')
    pw = getpass('Senha (minimo 12 caracteres): ')
    if len(pw) < 12:
        raise SystemExit('Senha muito curta')
    if pw != getpass('Confirme a senha: '):
        raise SystemExit('As senhas nao conferem')
    with Session(engine()) as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit('Email ja cadastrado')
        db.add(User(email=email, password_hash=hash_password(pw)))
        db.commit()
    print('Usuario criado com sucesso. Nenhuma senha foi armazenada em texto claro.')


if __name__ == '__main__':
    main()
