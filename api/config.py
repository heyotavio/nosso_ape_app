from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    db_host: str = '127.0.0.1'
    db_port: int = 5432
    db_name: str = 'nosso_ape'
    db_user: str = 'nosso_ape_app'
    db_password: str = ''
    app_secret_key: str = ''
    cors_origins: str = 'http://localhost:8080,http://127.0.0.1:8080'
    token_expiration_minutes: int = 480

    # Permite teste automatizado com SQLite sem PostgreSQL instalado no ambiente de teste.
    database_url: str | None = None
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def sqlalchemy_url(self):
        if self.database_url:
            return self.database_url
        if not self.db_password or self.db_password.startswith('SUBSTITUA'):
            raise RuntimeError('Configure DB_PASSWORD no .env antes de iniciar a API.')
        return URL.create(
            drivername='postgresql+psycopg', username=self.db_user,
            password=self.db_password, host=self.db_host,
            port=self.db_port, database=self.db_name,
        )

    def validated_secret(self):
        if len(self.app_secret_key) < 32 or self.app_secret_key.startswith('SUBSTITUA'):
            raise RuntimeError('Defina APP_SECRET_KEY com pelo menos 32 caracteres aleatorios no .env.')
        return self.app_secret_key

    @property
    def origins(self) -> list[str]:
        return [s.strip().rstrip('/') for s in self.cors_origins.split(',') if s.strip()]


@lru_cache
def settings():
    return Settings()
