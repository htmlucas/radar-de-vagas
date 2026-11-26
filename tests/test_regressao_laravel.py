"""Rede de segurança da trilha PHP/Laravel.

Roda o código REAL da trilha (coletores, normalização, nota, filtros e relatórios) sobre
amostras fictícias em tests/fixtures/laravel/ e compara o resultado com a "fotografia" salva
em tests/snapshots/laravel_referencia.json. Se qualquer coisa que a trilha Laravel produz
mudar (uma vaga a mais ou a menos, uma nota diferente, um filtro, um relatório), o teste falha.

A fotografia só é regravada de propósito, por quem aprovou a mudança:
    python -m tests.test_regressao_laravel --gravar

Não toca no banco nem na rede: as respostas das fontes são simuladas.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from vagas import relatorios
from vagas.coleta import adzuna, github
from vagas.coleta.emails import extrair_vagas
from vagas.coleta.gmail import juntar
from vagas.painel import logica
from vagas.pontuacao.nota import calcular
from vagas.tratamento.normalizar import chave_dedupe, montar_vaga

FIXTURES = Path(__file__).parent / "fixtures" / "laravel"
SNAPSHOT = Path(__file__).parent / "snapshots" / "laravel_referencia.json"
FUSO = relatorios.FUSO
AGORA = pd.Timestamp("2026-11-24 12:00", tz=FUSO)
DATA_EMAIL = "2026-11-22T08:00:00+00:00"


# --------------------------------------------------------------------------- fontes simuladas
class _Resposta:
    def __init__(self, dados):
        self._dados, self.links = dados, {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._dados


class _Sessao:
    """Responde no lugar da rede: issues do GitHub por repositório, ou resultados da Adzuna."""

    def __init__(self, github_issues=None, adzuna=None):
        self.headers = {}
        self._github, self._adzuna = github_issues, adzuna

    def get(self, url, params=None, timeout=None):
        if self._github is not None:
            repo = url.split("/repos/")[1].removesuffix("/issues")
            return _Resposta(self._github[repo])
        return _Resposta(self._adzuna)


def _ler(nome: str):
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


def coletar_github(monkeypatch=None) -> list[dict]:
    issues = _ler("github_issues.json")
    original = (github.sessao_http, github.salvar_bronze, github.config)
    github.sessao_http = lambda: _Sessao(github_issues=issues)
    github.salvar_bronze = lambda fonte, dados: Path("simulado.json")
    github.config = SimpleNamespace(github_token="")
    try:
        return github.coletar()[0]
    finally:
        github.sessao_http, github.salvar_bronze, github.config = original


def coletar_adzuna() -> list[dict]:
    resultados = _ler("adzuna_resultados.json")
    original = (adzuna.sessao_http, adzuna.salvar_bronze, adzuna.config)
    adzuna.sessao_http = lambda: _Sessao(adzuna=resultados)
    adzuna.salvar_bronze = lambda fonte, dados: Path("simulado.json")
    adzuna.config = SimpleNamespace(adzuna_app_id="x", adzuna_app_key="y")
    try:
        return adzuna.coletar()[0]
    finally:
        adzuna.sessao_http, adzuna.salvar_bronze, adzuna.config = original


def coletar_emails() -> list[dict]:
    vagas: dict[str, dict] = {}
    for arquivo, remetente in (("alerta_linkedin.html", "jobalerts-noreply@linkedin.com"),
                               ("alerta_glassdoor.html", "noreply@glassdoor.com"),
                               ("alerta_indeed.html", "alert@indeed.com")):
        html = (FIXTURES / arquivo).read_text(encoding="utf-8")
        for v in extrair_vagas(html, remetente, "x", DATA_EMAIL):
            juntar(vagas, v)
    return list(vagas.values())


# --------------------------------------------------------------------------- regras espelhadas do gold
def e_alvo(v: dict) -> bool:
    """Espelha a coluna `alvo` de gold.vagas (sql/schema.sql). O banco real é conferido
    por scripts/conferir_laravel.py; aqui o objetivo é detectar mudança no resultado."""
    return bool((v["cita_laravel"] or (v["so_titulo"] and "PHP" in v["tecnologias"]))
                and (v["nivel"] or "pleno") in ("junior", "pleno"))


def escolher_por_vaga_real(vagas: list[dict]) -> list[dict]:
    """Espelha `distinct on (chave_dedupe)` do gold: fica a cópia que cita Laravel,
    depois a de descrição mais longa, depois a mais recente."""
    grupos: dict[str, list[dict]] = {}
    for v in vagas:
        grupos.setdefault(v["chave_dedupe"], []).append(v)
    return [min(g, key=lambda v: (not v["cita_laravel"], -len(v["descricao"] or ""),
                                  -(pd.Timestamp(v["publicada_em"]).timestamp() if v["publicada_em"] else 0)))
            for _, g in sorted(grupos.items())]


def _texto(valor):
    return valor if valor is None else str(valor)


# --------------------------------------------------------------------------- DataFrame no formato do painel
def dataframe_do_painel(vagas: list[dict], perfil: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monta o que o painel lê de gold.vagas, com status e histórico determinísticos."""
    status = {0: "interessa", 1: "candidatei", 2: "entrevista", 3: "descartada", 4: "candidatei", 5: "recusado"}
    linhas, historico = [], []
    for i, v in enumerate(sorted(vagas, key=lambda x: x["id"])):
        nota, motivos = calcular(v, perfil)
        st = status.get(i, "nova")
        em = pd.Timestamp(f"2026-11-{12 + i:02d} 10:00", tz=FUSO)
        publicada = pd.Timestamp(v["publicada_em"]) if v["publicada_em"] else pd.NaT
        linhas.append({
            **{k: v[k] for k in ("id", "fonte", "titulo", "empresa", "descricao", "localizacao", "modelo_trabalho",
                                 "nivel", "tecnologias")},
            "fontes": [v["fonte"]], "compatibilidade": nota, "motivos": motivos, "status": st,
            "status_em": em if st != "nova" else pd.NaT, "alvo": e_alvo(v), "publicada_em": publicada,
            "primeira_coleta": publicada if pd.notna(publicada) else em, "nota": None,
            "motivo_descarte": "Empresa não me interessa" if st == "descartada" else None, "detalhe_descarte": None,
        })
        if st in ("candidatei", "entrevista", "recusado"):
            historico.append({"vaga_id": v["id"], "status": "candidatei", "em": em})
        if st in ("interessa", "entrevista"):
            historico.append({"vaga_id": v["id"], "status": "interessa", "em": em - pd.Timedelta(days=1)})
        if st in ("entrevista", "recusado"):
            historico.append({"vaga_id": v["id"], "status": st, "em": em + pd.Timedelta(days=3)})
    df = relatorios.preparar_vagas(linhas)
    return df, relatorios.preparar_historico(historico)


def _json(df: pd.DataFrame):
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def _painel(vagas: list[dict], perfil: dict) -> dict:
    df, hist = dataframe_do_painel(vagas, perfil)
    padrao = logica.Filtros()
    filtros = {
        "padrao": padrao,
        "todas": logica.Filtros(so_perfil=False, dias=None),
        "remoto": logica.Filtros(so_perfil=False, dias=None, modalidades=["remoto"]),
        "junior": logica.Filtros(so_perfil=False, dias=None, niveis=["junior"]),
        "laravel": logica.Filtros(so_perfil=False, dias=None, tecnologias=["Laravel"]),
        "busca": logica.Filtros(so_perfil=False, dias=None, busca="acme"),
        "dia": logica.Filtros(so_perfil=False, dias=None, dia=pd.Timestamp("2026-11-21").date()),
    }
    return {
        "filtros": {nome: sorted(logica.filtrar_vagas(df, f, AGORA)["id"]) for nome, f in filtros.items()},
        "ordem_compatibilidade": list(logica.ordenar(df, "compatibilidade")["id"]),
        "ordem_empresa": list(logica.ordenar(df, "empresa")["id"]),
        "relatorio_filtrar": sorted(relatorios.filtrar(df, dias=None, so_alvo=True, fontes=[], modelos=[])["id"]),
        "resumo_candidaturas": relatorios.resumo_candidaturas(df, hist),
        "funil": _json(relatorios.funil(df, hist)),
        "aguardando_retorno": _json(relatorios.aguardando_retorno(df, hist, AGORA)[["id", "dias_sem_retorno"]]),
        "minhas_candidaturas": sorted(relatorios.minhas_candidaturas(df, hist, AGORA)["id"]),
        "tempo_ate_candidatar": relatorios.tempo_ate_candidatar(df, hist),
        "descartadas": sorted(relatorios.descartadas(df)["id"]),
        "esquecidas": sorted(relatorios.esquecidas(df, nota_minima=60, dias=30)["id"]),
        "vagas_por_semana": _json(relatorios.vagas_por_semana(df)),
        "distribuicao_nivel": _json(relatorios.distribuicao(df, "nivel", relatorios.NIVEIS)),
        "distribuicao_modelo": _json(relatorios.distribuicao(df, "modelo_trabalho", relatorios.MODELOS)),
        "tecnologias": _json(relatorios.tecnologias(df[df["alvo"]], perfil)),
        "faixas_de_nota": _json(relatorios.faixas_de_nota(df)),
        "empresas": _json(relatorios.empresas(df)),
        "por_fonte": _json(relatorios.por_fonte(df)),
        "classificacao": {str(n): logica.classificar_nota(n) for n in (0, 59, 60, 74, 75, 100)},
    }


# --------------------------------------------------------------------------- a fotografia
def calcular_referencia() -> dict:
    perfil = _ler("perfil.json")
    github_, adzuna_, emails_ = coletar_github(), coletar_adzuna(), coletar_emails()
    todas = github_ + adzuna_ + emails_
    por_vaga = []
    for v in sorted(todas, key=lambda x: x["id"]):
        nota, motivos = calcular(v, perfil)
        por_vaga.append({**{k: (_texto(x) if k == "publicada_em" else x) for k, x in v.items()},
                         "nota": nota, "motivos": motivos, "alvo": e_alvo(v),
                         "chave_dedupe_recalculada": chave_dedupe(v["titulo"], v["empresa"])})
    gold = escolher_por_vaga_real(todas)
    return {
        "contagem_por_fonte": {f: sum(1 for v in todas if v["fonte"] == f) for f in sorted({v["fonte"] for v in todas})},
        "vagas": por_vaga,
        "gold_ids": sorted(v["id"] for v in gold),
        "alvo_ids": sorted(v["id"] for v in gold if e_alvo(v)),
        "painel": _painel(gold, perfil),
    }


def _normalizar(dados) -> dict:
    """Passa por JSON para comparar do mesmo jeito que o arquivo (tuplas viram listas etc.)."""
    return json.loads(json.dumps(dados, ensure_ascii=False, default=str, sort_keys=True))


def test_trilha_laravel_igual_a_fotografia():
    esperado = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    atual = _normalizar(calcular_referencia())
    assert atual["contagem_por_fonte"] == esperado["contagem_por_fonte"], "mudou quantas vagas cada fonte entrega"
    assert atual["gold_ids"] == esperado["gold_ids"], "mudou a deduplicação"
    assert atual["alvo_ids"] == esperado["alvo_ids"], "mudou quais vagas são alvo"
    assert atual["vagas"] == esperado["vagas"], "mudou a normalização ou a nota de alguma vaga"
    assert atual["painel"] == esperado["painel"], "mudou algum filtro, ordenação ou relatório"


def test_a_fotografia_cobre_os_casos_importantes():
    """Garante que a fotografia continua sendo uma boa rede de segurança (não ficou vazia)."""
    esperado = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    ids = {v["id"] for v in esperado["vagas"]}
    assert len(ids) >= 12
    assert {v["fonte"] for v in esperado["vagas"]} >= {"github", "adzuna", "linkedin", "glassdoor", "indeed"}
    assert len(esperado["gold_ids"]) < len(ids), "a amostra precisa ter ao menos uma vaga repetida entre fontes"
    assert any(v["alvo"] for v in esperado["vagas"]) and any(not v["alvo"] for v in esperado["vagas"])
    # Comportamento atual preservado de propósito: vaga de dados do GitHub entra na silver como "não alvo".
    dados = next(v for v in esperado["vagas"] if "Engenheiro de Dados" in v["titulo"])
    assert dados["alvo"] is False and dados["cita_laravel"] is False


if __name__ == "__main__":
    if "--gravar" not in sys.argv:
        raise SystemExit("Isto regrava a fotografia de referência da trilha Laravel. "
                         "Só faça se a mudança foi aprovada: python -m tests.test_regressao_laravel --gravar")
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(_normalizar(calcular_referencia()), ensure_ascii=False, indent=1, sort_keys=True),
                        encoding="utf-8")
    print("Fotografia gravada em", SNAPSHOT)
