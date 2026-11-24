"""Dados e rótulos usados pelas páginas do painel (somente leitura, exceto ações explícitas)."""

import json
import os
import subprocess

import pandas as pd
import psycopg
import streamlit as st

from vagas import db, relatorios
from vagas.config import config
from vagas.curriculo import base as curriculo_base
from vagas.curriculo.base import CurriculoNaoEncontrado

FUSO = relatorios.FUSO
NIVEIS = {"junior": "Júnior", "pleno": "Pleno", "senior": "Sênior", None: "Não informado"}
MODELOS = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial", None: "Não informado"}
STATUS = {
    "nova": "🆕 Nova",
    "interessa": "⭐ Interessa",
    "candidatei": "📨 Candidatei",
    "entrevista": "🗣️ Entrevista",
    "proposta": "🎉 Proposta",
    "recusado": "❌ Recusado",
    "descartada": "🗑️ Descartada",
}
# Status que significam "já me candidatei" (com o andamento depois disso)
CANDIDATURA = relatorios.CANDIDATURA
EM_ANDAMENTO = ["candidatei", "entrevista", "proposta"]

# Motivos de descarte: lista fixa para dar para contar e comparar nos relatórios.
MOTIVOS_DESCARTE = [
    "Nível acima do meu (sênior/especialista)",
    "Não é Laravel/PHP (stack diferente)",
    "Presencial ou híbrido fora da minha região",
    "Salário ou contrato não atende",
    "Exige inglês avançado",
    "Empresa não me interessa",
    "Vaga encerrada ou muito antiga",
    "Repetida / já me candidatei antes",
    "Outro",
]
SEM_MOTIVO = relatorios.SEM_MOTIVO
FONTES_COLETA = ["github", "adzuna", "gmail"]  # coletores (o gmail traz linkedin/glassdoor/indeed)


def banco_disponivel() -> tuple[bool, str | None]:
    """O banco responde? (True, None) ou (False, mensagem técnica). Falha rápido (2 s por endereço)."""
    try:
        with psycopg.connect(config.conninfo, connect_timeout=2) as conn:
            conn.execute("select 1")
        return True, None
    except psycopg.Error as e:
        return False, " ".join(str(e).split())


# --------------------------------------------------------------------------- vagas
@st.cache_data(ttl=60, show_spinner="Carregando vagas...")
def carregar_vagas() -> pd.DataFrame:
    """Todas as vagas do gold (uma por vaga real) + em quais fontes cada uma apareceu."""
    with db.conectar() as conn:
        linhas = conn.execute(
            """
            select g.*, f.fontes
              from gold.vagas g
              join (select chave_dedupe, array_agg(distinct fonte order by fonte) as fontes
                      from silver.vagas group by chave_dedupe) f using (chave_dedupe)
             order by g.publicada_em desc nulls last
            """
        ).fetchall()
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    for col in ("publicada_em", "primeira_coleta", "status_em"):
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(FUSO)
    # Campos vazios chegam como NaN no pandas; volta para None (NaN é "verdadeiro" em `or`).
    texto = ["empresa", "nivel", "modelo_trabalho", "descricao", "localizacao", "nota",
             "motivo_descarte", "detalhe_descarte"]
    df[texto] = df[texto].astype(object).where(df[texto].notna(), None)
    df["tecnologias"] = df["tecnologias"].apply(lambda t: list(t) if t is not None else [])
    df["fontes"] = df["fontes"].apply(lambda t: list(t) if t is not None else [])
    return df


@st.cache_data(ttl=60)
def historico() -> pd.DataFrame:
    return relatorios.preparar_historico(db.carregar_historico())


@st.cache_data(ttl=60, show_spinner="Carregando relatórios...")
def dados_relatorios() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with db.conectar() as conn:
        vagas = conn.execute("select * from gold.vagas").fetchall()
    return (relatorios.preparar_vagas(vagas),
            relatorios.preparar_historico(db.carregar_historico()),
            pd.DataFrame(db.carregar_execucoes()))


# --------------------------------------------------------------------------- coleta e pipeline
@st.cache_data(ttl=60)
def ultimas_execucoes() -> pd.DataFrame:
    with db.conectar() as conn:
        return pd.DataFrame(
            conn.execute(
                """
                select distinct on (fonte) fonte, iniciada_em, finalizada_em, qtd_coletada, qtd_nova, erro
                  from silver.execucoes order by fonte, id desc
                """
            ).fetchall()
        )


def situacao_execucao(execucao) -> tuple[str, str]:
    """(rótulo, tom) de uma execução: concluída, ignorada, com erro ou não concluída."""
    erro = execucao.get("erro")
    if execucao.get("finalizada_em") is None or pd.isna(execucao.get("finalizada_em")):
        return "Não concluída", "erro"
    if isinstance(erro, str) and erro.startswith("ignorada"):
        return "Ignorada", "atencao"
    if isinstance(erro, str) and erro:
        return "Erro", "erro"
    return "OK", "sucesso"


@st.cache_data(ttl=60)
def estado_pipeline() -> dict:
    """Números de cada camada. Bronze = arquivos em disco; Silver/Gold = banco."""
    bronze = {}
    raiz = config.pasta_dados / "bronze"
    for fonte in FONTES_COLETA:
        arquivos = sorted((raiz / fonte).glob("*/*.json")) if (raiz / fonte).exists() else []
        bronze[fonte] = {
            "arquivos": len(arquivos),
            "ultimo": pd.Timestamp(os.path.getmtime(arquivos[-1]), unit="s", tz="UTC").tz_convert(FUSO)
            if arquivos else None,
            "tamanho_mb": round(sum(a.stat().st_size for a in arquivos) / 1_048_576, 1),
        }
    with db.conectar() as conn:
        silver = conn.execute(
            "select fonte, count(*) as vagas, max(ultima_coleta) as ultima from silver.vagas group by 1 order by 2 desc"
        ).fetchall()
        gold = conn.execute(
            """
            select count(*) as vagas, count(*) filter (where alvo) as alvo,
                   count(*) filter (where alvo and status <> 'descartada') as alvo_ativas,
                   (select max(calculado_em) from silver.vaga_pontuacao) as pontuado_em,
                   (select count(*) from silver.vaga_status) as marcadas
              from gold.vagas
            """
        ).fetchone()
    return {"bronze": bronze, "silver": silver, "gold": gold}


TAREFA_AGENDADA = ("\\RadarDeVagas\\", "ColetaDiaria")


@st.cache_data(ttl=300)
def agendamento() -> dict | None:
    """Estado da coleta automática no Agendador de Tarefas do Windows (None se não agendada)."""
    if os.name != "nt":
        return None
    caminho, nome = TAREFA_AGENDADA
    comando = (
        f"$t = Get-ScheduledTask -TaskPath '{caminho}' -TaskName '{nome}' -ErrorAction Stop; "
        "$i = $t | Get-ScheduledTaskInfo; "
        "[pscustomobject]@{ horario = ([datetime]$t.Triggers[0].StartBoundary).ToString('HH:mm'); "
        "proxima = $i.NextRunTime.ToString('o'); ultima = $i.LastRunTime.ToString('o'); "
        "resultado = $i.LastTaskResult; estado = [string]$t.State } | ConvertTo-Json -Compress"
    )
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True,
                               text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if saida.returncode != 0 or not saida.stdout.strip():
        return None
    dados = json.loads(saida.stdout)
    for chave in ("proxima", "ultima"):
        ts = pd.Timestamp(dados[chave])
        dados[chave] = None if ts.year < 2000 else ts.tz_localize(FUSO) if ts.tzinfo is None else ts.tz_convert(FUSO)
    return dados


# --------------------------------------------------------------------------- perfil
def carregar_base() -> dict | None:
    try:
        return curriculo_base.carregar()
    except CurriculoNaoEncontrado:
        return None


def perfil_publico() -> dict:
    """Só nome e título (nada de e-mail/telefone) para o rodapé da barra lateral."""
    base = carregar_base() or {}
    contato = base.get("contato", {})
    return {"nome": contato.get("nome") or "Meu radar", "titulo": contato.get("titulo") or ""}


# --------------------------------------------------------------------------- utilidades
def limpar_cache() -> None:
    carregar_vagas.clear()
    historico.clear()
    dados_relatorios.clear()
    ultimas_execucoes.clear()
    estado_pipeline.clear()


def quando(ts, agora: pd.Timestamp | None = None) -> str:
    """'15/11 (há 8 dias)', '23/11 (hoje)', '22/11 (ontem)'. Ano só se não for o atual."""
    if ts is None or pd.isna(ts):
        return "sem data"
    agora = agora or pd.Timestamp.now(tz=FUSO)
    dias = (agora.normalize() - ts.normalize()).days
    relativo = "hoje" if dias <= 0 else "ontem" if dias == 1 else f"há {dias} dias"
    data = ts.strftime("%d/%m") if ts.year == agora.year else ts.strftime("%d/%m/%Y")
    return f"{data} ({relativo})"


def ha_quanto(ts, agora: pd.Timestamp | None = None) -> str:
    """'agora', 'há 5 min', 'há 3 h', 'há 2 dias'."""
    if ts is None or pd.isna(ts):
        return "nunca"
    agora = agora or pd.Timestamp.now(tz=FUSO)
    seg = (agora - pd.Timestamp(ts).tz_convert(FUSO)).total_seconds()
    if seg < 60:
        return "agora"
    if seg < 3600:
        return f"há {int(seg // 60)} min"
    if seg < 86400:
        return f"há {int(seg // 3600)} h"
    return f"há {int(seg // 86400)} dia{'s' if seg >= 172800 else ''}"
