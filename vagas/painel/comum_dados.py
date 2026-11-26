"""Dados e rótulos do painel da trilha de Engenharia de Dados (somente leitura).

Lê SÓ gold.dados_vagas e silver.dados_* (pelo vagas.trilhas.dados.db): nada da trilha Laravel.
NÃO cria schema e NÃO dispara coleta. Se as tabelas dados_* ainda não existem, as páginas mostram uma
mensagem explicando como inicializar a trilha, em vez de um erro.
"""

import json
import os
import subprocess

import pandas as pd
import psycopg
import streamlit as st

from vagas import relatorios
from vagas.painel import ui
from vagas.painel.comum import CANDIDATURA, EM_ANDAMENTO, FUSO, ha_quanto, quando, situacao_execucao  # noqa: F401
from vagas.trilhas.dados import coleta as coleta_mod
from vagas.trilhas.dados import curriculo as curriculo_dados
from vagas.trilhas.dados import db as dados_db

# --------------------------------------------------------------------------- rótulos
CATEGORIAS = {"engenharia_dados": "Engenharia de Dados", "analytics_engineer": "Analytics Engineer",
              "dev_etl": "Dev ETL", "relacionada": "Relacionada"}
CATEGORIAS_ALVO = ["engenharia_dados", "analytics_engineer", "dev_etl"]
NIVEIS = {"estagio": "Estágio", "trainee": "Trainee", "junior": "Júnior", "pleno": "Pleno", "senior": "Sênior"}
SEM_NIVEL = "nao_informado"
MODALIDADES = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}
CONFIANCA = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
ELEGIBILIDADE = {"ok": "Elegível", "alerta": "Com alerta", "nao_se_aplica": "Sem exigência"}
FAIXAS = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
TOM_CONFIANCA = {"alta": "sucesso", "media": "atencao", "baixa": "erro"}
TOM_ELEGIBILIDADE = {"ok": "sucesso", "alerta": "atencao", "nao_se_aplica": "neutro"}
STATUS = ["nova", "interessa", "descartada", "candidatei", "entrevista", "proposta", "recusado"]
SEM_MOTIVO = relatorios.SEM_MOTIVO
MOTIVOS_DESCARTE = [
    "Nível acima do meu (pleno/sênior)", "Não é Engenharia de Dados (cargo diferente)",
    "Presencial ou híbrido (prefiro 100% remoto)", "Localização fora do Brasil", "Exige experiência que ainda não tenho",
    "Exige inglês avançado", "Exige graduação em curso", "Salário ou contrato não atende", "Empresa não me interessa",
    "Vaga encerrada ou muito antiga", "Repetida / já me candidatei antes", "Outro",
]
FONTES_COLETA = list(coleta_mod.COLETORES)
DESCRICAO_FONTE = {
    "github": ("GitHub", "github", "Issues abertas do repositório backend-br/vagas, classificadas pela trilha de dados."),
    "adzuna": ("Adzuna", "globe", "API que agrega vagas de vários sites do Brasil (buscas por cargo)."),
    "gmail": ("Gmail", "mail", "Alertas de vaga de dados do LinkedIn, Glassdoor e Indeed no seu e-mail (só leitura)."),
}
TAREFA_AGENDADA = ("\\RadarDeVagas\\", "ColetaDados")
COMANDO_INICIALIZAR = "python -m vagas.trilhas.dados.pipeline"
COMANDO_AGENDAR = r"powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agendar.ps1 -Dados"

_LISTAS = ["tecnologias", "conceitos", "req_obrigatorios", "req_desejaveis", "citados_em_atividades", "motivos", "alertas",
           "confianca_motivos", "fontes", "parcelas"]
_TEXTOS = ["empresa", "nivel", "modelo_trabalho", "descricao", "localizacao", "nota", "motivo_descarte", "detalhe_descarte",
           "faixa", "confianca_nivel", "elegibilidade", "formacao_exigida"]


# --------------------------------------------------------------------------- preparo (puro, testável)
def preparar_vagas_dados(linhas: list[dict]) -> pd.DataFrame:
    """Linhas de gold.dados_vagas -> DataFrame no formato que as funções de relatório e de filtro esperam."""
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    for col in ("publicada_em", "primeira_coleta", "status_em"):
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(FUSO)
    df[_TEXTOS] = df[_TEXTOS].astype(object).where(df[_TEXTOS].notna(), None)
    for col in _LISTAS:
        df[col] = df[col].apply(lambda t: list(t) if t is not None else [])
    return df


# --------------------------------------------------------------------------- leitura (sempre sem criar nada)
@st.cache_data(ttl=30)
def inicializada() -> bool:
    """As tabelas e visões dados_* existem? (Consulta o catálogo; não cria nada.)"""
    try:
        with dados_db.conectar() as conn:
            linha = conn.execute(
                "select to_regclass('gold.dados_vagas') is not null and to_regclass('silver.dados_execucoes') is not null "
                "and to_regclass('silver.dados_vaga_status') is not null as ok").fetchone()
        return bool(linha["ok"])
    except psycopg.Error:
        return False


@st.cache_data(ttl=60, show_spinner="Carregando vagas de dados...")
def carregar_vagas() -> pd.DataFrame:
    try:
        with dados_db.conectar() as conn:
            linhas = conn.execute(
                """
                select g.*, f.fontes
                  from gold.dados_vagas g
                  join (select chave_dedupe, array_agg(distinct fonte order by fonte) as fontes
                          from silver.dados_vagas group by chave_dedupe) f using (chave_dedupe)
                 order by g.publicada_em desc nulls last
                """).fetchall()
    except psycopg.errors.UndefinedTable:
        return pd.DataFrame()
    return preparar_vagas_dados(linhas)


@st.cache_data(ttl=60)
def historico() -> pd.DataFrame:
    try:
        return relatorios.preparar_historico(dados_db.carregar_historico())
    except psycopg.errors.UndefinedTable:
        return relatorios.preparar_historico([])


@st.cache_data(ttl=60)
def execucoes() -> pd.DataFrame:
    try:
        return pd.DataFrame(dados_db.carregar_execucoes())
    except psycopg.errors.UndefinedTable:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def ultimas_execucoes() -> pd.DataFrame:
    """Última execução de cada fonte."""
    try:
        with dados_db.conectar() as conn:
            return pd.DataFrame(conn.execute(
                "select distinct on (fonte) fonte, iniciada_em, finalizada_em, qtd_coletada, qtd_nova, erro "
                "from silver.dados_execucoes order by fonte, id desc").fetchall())
    except psycopg.errors.UndefinedTable:
        return pd.DataFrame()


def limpar_cache() -> None:
    """Só as caches da trilha de dados (as da Laravel não são tocadas)."""
    for f in (inicializada, carregar_vagas, historico, execucoes, ultimas_execucoes):
        f.clear()


@st.cache_data(ttl=60)
def curriculo_combinado() -> dict | None:
    """curriculo.yaml + curriculo_dados.yaml combinados sobre cópias (None se faltar algum arquivo)."""
    try:
        return curriculo_dados.carregar_combinado()
    except (FileNotFoundError, curriculo_dados.OrigemNaoEncontrada):
        return None


@st.cache_data(ttl=300)
def agendamento() -> dict | None:
    """Estado da tarefa \\RadarDeVagas\\ColetaDados no Agendador do Windows (somente leitura; None se não registrada)."""
    if os.name != "nt":
        return None
    caminho, nome = TAREFA_AGENDADA
    comando = (
        f"$t = Get-ScheduledTask -TaskPath '{caminho}' -TaskName '{nome}' -ErrorAction Stop; $i = $t | Get-ScheduledTaskInfo; "
        "[pscustomobject]@{ horario = ([datetime]$t.Triggers[0].StartBoundary).ToString('HH:mm'); gatilhos = @($t.Triggers).Count; "
        "proxima = $i.NextRunTime.ToString('o'); ultima = $i.LastRunTime.ToString('o'); resultado = $i.LastTaskResult; "
        "estado = [string]$t.State } | ConvertTo-Json -Compress")
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True, timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if saida.returncode != 0 or not saida.stdout.strip():
        return None
    dados = json.loads(saida.stdout)
    for chave in ("proxima", "ultima"):
        ts = pd.Timestamp(dados[chave])
        dados[chave] = None if ts.year < 2000 else ts.tz_localize(FUSO) if ts.tzinfo is None else ts.tz_convert(FUSO)
    return dados


# --------------------------------------------------------------------------- apresentação
def trilha_pronta(titulo: str, descricao: str, nome_icone: str) -> bool:
    """Cabeçalho da página + verificação do banco. Se a trilha ainda não foi inicializada, explica como
    inicializar e devolve False (a página deve parar). Nunca cria schema nem coleta."""
    ui.cabecalho(titulo, descricao, nome_icone)
    if inicializada():
        return True
    ui.vazio(
        "A trilha de Engenharia de Dados ainda não foi inicializada",
        "As tabelas <code>dados_*</code> ainda não existem no banco. Este painel não cria o schema nem coleta sozinho. "
        f"Quando a trilha for liberada, rode <code>{COMANDO_INICIALIZAR}</code>: ele cria o esquema e faz a primeira coleta. "
        "Depois disso, as páginas passam a mostrar as vagas. Veja <b>Configurações</b> para o que será coletado.",
        "database")
    return False


def sem_vagas() -> None:
    ui.vazio("Nenhuma vaga de Engenharia de Dados coletada ainda",
             f"A trilha está inicializada, mas ainda não há vagas. Rode <code>{COMANDO_INICIALIZAR}</code> "
             "(ou aguarde a coleta agendada).", "inbox")


def alvo_ativas(df: pd.DataFrame) -> pd.DataFrame:
    """Vagas-alvo que não foram descartadas (relacionadas, pleno e sênior nunca entram)."""
    return df[df["alvo"] & (df["status"] != "descartada")] if not df.empty else df


def remotas_compativeis(df: pd.DataFrame) -> pd.DataFrame:
    """Só remoto confirmado conta: modalidade não informada, híbrida e presencial não são compatíveis."""
    a = alvo_ativas(df)
    return a[a["modelo_trabalho"] == "remoto"] if not a.empty else a


def termos_de_busca() -> dict:
    return {"adzuna": list(coleta_mod.BUSCAS_ADZUNA), "github": list(coleta_mod.REPOSITORIOS_GITHUB),
            "gmail": coleta_mod.CONSULTA_GMAIL, "paginas_adzuna": coleta_mod.MAX_PAGINAS_ADZUNA}
