# src/core/config.py
from pydantic import BaseModel
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal


class RunConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8015


class ApiV1Prefix(BaseModel):
    prefix: str = "/v1"
    users: str = "/users"
    auth: str = "/auth"


class ApiPrefix(BaseModel):
    prefix: str = "/api"
    v1: ApiV1Prefix = ApiV1Prefix()


class DatabaseConfig(BaseModel):
    url: PostgresDsn
    echo: bool = False
    echo_pool: bool = False
    pool_size: int = 50
    max_overflow: int = 10

    naming_convention: dict[str, str] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }

class AuthConfig(BaseModel):
    secret_key: str = "CHANGE_ME"                # общий секрет (JWT/CSRF/сессии)
    algorithm: str = "HS256"
    access_token_minutes: int = 60
    email_verify_secret: str = "CHANGE_ME_EMAIL" # отдельный секрет для ссылок
    verify_token_ttl_hours: int = 48


class EmailConfig(BaseModel):
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    use_tls: bool = False
    use_ssl: bool = False
    from_email: str = "noreply@example.com"


class SiteConfig(BaseModel):
    # если нужно строить абсолютные ссылки вне Request (опционально)
    base_url: str = "http://127.0.0.1:8000"


class QdrantConfig(BaseModel):
    host: str = "localhost"          # в docker-сети будет "qdrant"
    port: int = 6333
    timeout_s: int = 300

class FsnbConfig(BaseModel):
    fsnb_dir: str = "FSNB-2022_28_08_25"
    weights_dir: str = "weights"
    model_giga_dir: str = "weights/Giga-Embeddings-instruct"
    similarity_threshold: float = 0.70
    embed_batch_size: int = 128

    # Тонкие настройки/инференс
    gpu_slots: int = 1
    giga_query_bs: int = 2
    giga_index_bs: int = 8
    hf_embed_device: Literal["auto", "cuda", "cpu"] = "auto"
    hf_embed_fp16: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.example", ".env"),
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="APP_CONFIG__",
    )
    run: RunConfig = RunConfig()
    api: ApiPrefix = ApiPrefix()
    db: DatabaseConfig

    auth: AuthConfig = AuthConfig()
    email: EmailConfig = EmailConfig()
    site: SiteConfig = SiteConfig()

    qdrant: QdrantConfig = QdrantConfig()
    fsnb: FsnbConfig = FsnbConfig()

settings = Settings()
