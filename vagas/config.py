import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


@dataclass(frozen=True)
class Config:
    db_nome: str = os.getenv("POSTGRES_DB", "vagas")
    db_usuario: str = os.getenv("POSTGRES_USER", "vagas")
    db_senha: str = os.getenv("POSTGRES_PASSWORD", "")
    db_host: str = os.getenv("POSTGRES_HOST", "localhost")
    db_porta: int = int(os.getenv("POSTGRES_PORT", "5440"))

    github_token: str = os.getenv("GITHUB_TOKEN", "")
    adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
    adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")

    pasta_dados: Path = RAIZ / os.getenv("DATA_DIR", "dados")

    @property
    def conninfo(self) -> str:
        return (
            f"host={self.db_host} port={self.db_porta} dbname={self.db_nome} "
            f"user={self.db_usuario} password={self.db_senha}"
        )


config = Config()
