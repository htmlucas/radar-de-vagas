"""Coletor de repositórios de vagas no GitHub (cada vaga é uma issue aberta).

Usa a API oficial do GitHub. Sem token o limite é 60 requisições/hora,
o que basta para rodar algumas vezes por dia.
"""

import re

from vagas.coleta.base import salvar_bronze, sessao_http
from vagas.config import config
from vagas.tratamento.normalizar import detectar_tecnologias, montar_vaga, sem_acento

FONTE = "github"
REPOSITORIOS = ["backend-br/vagas", "phpdevbr/vagas"]
MAX_PAGINAS = 3  # 100 issues por página


def _buscar_issues(sessao, repo: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/issues"
    params = {"state": "open", "per_page": 100, "sort": "created", "direction": "desc"}
    issues = []
    for _ in range(MAX_PAGINAS):
        resp = sessao.get(url, params=params, timeout=30)
        resp.raise_for_status()
        issues += [i for i in resp.json() if "pull_request" not in i]
        proxima = resp.links.get("next", {}).get("url")
        if not proxima:
            break
        url, params = proxima, None
    return issues


_NAO_EMPRESA = re.compile(
    r"presencial|remot|hibrid|home.?office|\bpj\b|\bclt\b|latam|brasil|sao paulo|"
    r"desenvolvedor|developer|engineer|engenheir|analista|programador|"
    r"back.?end|front.?end|full.?stack|junior|pleno|senior|"
    r"^[a-z]{2}$|\d",
)


def _parece_empresa(candidato: str) -> bool:
    c = candidato.strip(" .)")
    if not c or len(c) > 40 or "," in c or "+" in c:
        return False
    if detectar_tecnologias(c):  # "(Node.js + React)", "(PHP e Laravel)"
        return False
    return not _NAO_EMPRESA.search(sem_acento(c))


def extrair_empresa(titulo: str) -> str | None:
    """Os títulos seguem formatos livres. Tenta os mais comuns:
    "Cargo na Empresa", "Cargo (Empresa)", "Cargo - Empresa".
    É uma heurística: quando não tem certeza, devolve None.
    """
    t = re.sub(r"^\s*\[[^\]]*\]\s*", "", titulo).strip()
    # Tira parênteses finais que não são empresa, ex.: "na PlanitEasy (PJ, LATAM)"
    while (m := re.search(r"\s*\(([^()]*)\)\s*\)?$", t)) and not _parece_empresa(m.group(1)):
        t = t[: m.start()].strip()
    for padrao in (r"\(([^()]+)\)\s*\)?$", r"\s(?:na|no|at|@)\s+([^\-–|(]+)$", r"\s[-–|]\s*([^-–|]+)$"):
        m = re.search(padrao, t, re.IGNORECASE)
        if m and _parece_empresa(m.group(1)):
            return m.group(1).strip(" .)")
    return None


def _e_aviso_do_repositorio(titulo: str) -> bool:
    return bool(re.search(r"regras para divulga|rules for advertis", titulo, re.IGNORECASE))


def _localizacao(titulo: str) -> str | None:
    m = re.match(r"^\s*\[([^\]]+)\]", titulo)
    return m.group(1).strip() if m else None


def coletar() -> tuple[list[dict], list[str]]:
    sessao = sessao_http()
    if config.github_token:
        sessao.headers["Authorization"] = f"Bearer {config.github_token}"
    sessao.headers["Accept"] = "application/vnd.github+json"

    brutos, vagas, arquivos = {}, [], []
    for repo in REPOSITORIOS:
        issues = _buscar_issues(sessao, repo)
        brutos[repo] = issues
        for i in issues:
            if _e_aviso_do_repositorio(i["title"]):
                continue
            rotulos = [r["name"] for r in i.get("labels", [])]
            vagas.append(
                montar_vaga(
                    fonte=FONTE,
                    id_externo=f"{repo}#{i['number']}",
                    titulo=i["title"],
                    url=i["html_url"],
                    empresa=extrair_empresa(i["title"]),
                    descricao=i.get("body"),
                    localizacao=_localizacao(i["title"]),
                    publicada_em=i["created_at"],
                    rotulos=rotulos,
                )
            )
    arquivos.append(str(salvar_bronze(FONTE, brutos)))
    return vagas, arquivos
