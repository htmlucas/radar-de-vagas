"""Leitura do currículo base (curriculo/base/curriculo.yaml)."""

from functools import lru_cache
from pathlib import Path

import yaml

from vagas.config import RAIZ

CAMINHO_BASE = RAIZ / "curriculo" / "base" / "curriculo.yaml"
CAMINHO_EXEMPLO = RAIZ / "curriculo" / "exemplo.yaml"


class CurriculoNaoEncontrado(FileNotFoundError):
    pass


@lru_cache(maxsize=1)
def carregar(caminho: Path | None = None) -> dict:
    caminho = caminho or CAMINHO_BASE
    if not caminho.exists():
        raise CurriculoNaoEncontrado(
            f"Currículo base não encontrado em {caminho}. "
            f"Copie {CAMINHO_EXEMPLO.name} para curriculo/base/curriculo.yaml e preencha."
        )
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))
