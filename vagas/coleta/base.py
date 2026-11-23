"""Utilidades comuns aos coletores (camada bronze)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from vagas.config import config

USER_AGENT = "vagas-laravel/0.1 (radar pessoal de vagas)"


class FonteIgnorada(Exception):
    """A fonte não está configurada (ex.: falta chave de API). Não é erro."""


def sessao_http() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def salvar_bronze(fonte: str, dados) -> Path:
    """Guarda a resposta bruta da fonte, sem mexer em nada.

    Assim dá para reprocessar a silver depois (ex.: quando as regras de
    tratamento mudarem) sem precisar coletar de novo.
    """
    agora = datetime.now(timezone.utc)
    pasta = config.pasta_dados / "bronze" / fonte / agora.strftime("%Y-%m-%d")
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{agora.strftime('%H%M%S')}.json"
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return caminho
