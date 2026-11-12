from functools import lru_cache
from typing import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    url = settings().sqlalchemy_url()
    kwargs = {'pool_pre_ping': True}
    if not str(url).startswith('sqlite:'):
        kwargs.update(pool_size=5, max_overflow=5)
    return create_engine(url, **kwargs)


def get_db() -> Iterator[Session]:
    session_factory = sessionmaker(engine(), expire_on_commit=False)
    with session_factory() as session:
        yield session
