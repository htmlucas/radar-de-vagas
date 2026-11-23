"""Coletor da API pública da Adzuna (agrega vagas de vários sites brasileiros).

Precisa de chave gratuita: https://developer.adzuna.com/
Observação: a API devolve só um trecho da descrição, não o texto completo.
"""

from vagas.coleta.base import FonteIgnorada, salvar_bronze, sessao_http
from vagas.config import config
from vagas.tratamento.normalizar import montar_vaga

FONTE = "adzuna"
URL = "https://api.adzuna.com/v1/api/jobs/br/search/{pagina}"
BUSCAS = ["laravel"]
MAX_PAGINAS = 4
POR_PAGINA = 50
DIAS = 14


def coletar() -> tuple[list[dict], list[str]]:
    if not (config.adzuna_app_id and config.adzuna_app_key):
        raise FonteIgnorada("ADZUNA_APP_ID/ADZUNA_APP_KEY não configurados no .env")

    sessao = sessao_http()
    brutos, vagas = {}, []
    for termo in BUSCAS:
        resultados = []
        for pagina in range(1, MAX_PAGINAS + 1):
            resp = sessao.get(
                URL.format(pagina=pagina),
                params={
                    "app_id": config.adzuna_app_id,
                    "app_key": config.adzuna_app_key,
                    "what": termo,
                    "results_per_page": POR_PAGINA,
                    "max_days_old": DIAS,
                    "sort_by": "date",
                },
                timeout=30,
            )
            resp.raise_for_status()
            lote = resp.json().get("results", [])
            resultados += lote
            if len(lote) < POR_PAGINA:
                break
        brutos[termo] = resultados
        for r in resultados:
            vagas.append(
                montar_vaga(
                    fonte=FONTE,
                    id_externo=str(r["id"]),
                    titulo=r.get("title", ""),
                    url=r.get("redirect_url", ""),
                    empresa=(r.get("company") or {}).get("display_name"),
                    descricao=r.get("description"),
                    localizacao=(r.get("location") or {}).get("display_name"),
                    publicada_em=r.get("created"),
                )
            )
    return vagas, [str(salvar_bronze(FONTE, brutos))]
