"""Lógica de apresentação do painel: funções puras (sem Streamlit), cobertas por testes.

Não muda nenhuma regra de negócio: só interpreta dados que já existem
(nota, motivos, status, datas) para mostrar na tela.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from vagas import relatorios

FUSO = relatorios.FUSO
DIAS_PARA_COBRAR = relatorios.DIAS_PARA_COBRAR
SEM_MODALIDADE = "nao_informado"

# Faixas usadas só para rotular a nota na tela (a nota em si vem de vagas/pontuacao/nota.py).
NOTA_ALTA, NOTA_MEDIA = 75, 60

# Prefixos que vagas/pontuacao/nota.py usa nos motivos
_POSITIVOS = ("✅", "➕", "🏠", "📍")
_ATENCAO = ("⚠️", "❔", "🚗")


def classificar_nota(n) -> tuple[str, str]:
    """(rótulo, tom) da nota de compatibilidade."""
    if n is None or pd.isna(n):
        return "Sem nota", "neutro"
    if n >= NOTA_ALTA:
        return "Alta", "sucesso"
    if n >= NOTA_MEDIA:
        return "Média", "atencao"
    return "Baixa", "erro"


def separar_motivos(motivos) -> tuple[list[str], list[str]]:
    """Divide os motivos da nota em pontos positivos e pontos de atenção (sem o emoji)."""
    positivos, atencao = [], []
    for m in motivos if isinstance(motivos, (list, tuple)) else []:
        texto = m.split(" ", 1)[1] if " " in m else m
        if m.startswith(_POSITIVOS):
            positivos.append(texto)
        elif m.startswith(_ATENCAO):
            atencao.append(texto)
        else:
            positivos.append(m)
    return positivos, atencao


def proxima_acao(status: str, dias: int | None) -> tuple[str, str]:
    """Próxima ação recomendada para uma vaga marcada. Só usa status que existem no sistema."""
    if status == "candidatei":
        if dias is not None and dias >= DIAS_PARA_COBRAR:
            return "Cobrar retorno do recrutador", "atencao"
        faltam = DIAS_PARA_COBRAR - (dias or 0)
        return f"Aguardar retorno ({faltam} dia{'s' if faltam != 1 else ''} para cobrar)", "neutro"
    if status == "entrevista":
        return "Preparar a entrevista e agradecer depois", "info"
    if status == "proposta":
        return "Avaliar a proposta e responder", "sucesso"
    if status == "recusado":
        return "Pedir feedback (opcional) e seguir", "neutro"
    if status == "interessa":
        return "Adaptar o currículo e se candidatar", "primario"
    return "", "neutro"


@dataclass
class Filtros:
    busca: str = ""
    so_perfil: bool = True
    dias: int | None = 90
    modalidades: list[str] = field(default_factory=list)   # vazio = todas
    niveis: list[str] = field(default_factory=list)
    tecnologias: list[str] = field(default_factory=list)
    fontes: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    dia: date | None = None   # dia em que a vaga entrou no radar (modo "Por dia")


def dia_encontrada(df: pd.DataFrame) -> pd.Series:
    """Dia (no fuso de Brasília) em que cada vaga entrou no radar."""
    return df["primeira_coleta"].dt.tz_convert(FUSO).dt.date


def filtrar_vagas(df: pd.DataFrame, f: Filtros, agora: pd.Timestamp | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    agora = agora or pd.Timestamp.now(tz=FUSO)
    r = df
    if f.so_perfil:
        r = r[r["alvo"]]
    if f.dia:
        r = r[dia_encontrada(r) == f.dia]
    if f.dias:
        r = r[r["publicada_em"] >= agora - pd.Timedelta(days=f.dias)]
    if f.status:
        r = r[r["status"].isin(f.status)]
    if f.modalidades:
        modal = r["modelo_trabalho"].fillna(SEM_MODALIDADE)
        r = r[modal.isin(f.modalidades)]
    if f.niveis:
        r = r[r["nivel"].fillna(SEM_MODALIDADE).isin(f.niveis)]
    if f.tecnologias:
        quer = set(f.tecnologias)
        r = r[r["tecnologias"].apply(lambda ts: bool(quer & set(ts or [])))]
    if f.fontes:
        quer = set(f.fontes)
        r = r[r["fontes"].apply(lambda fs: bool(quer & set(fs or [])))]
    if f.busca.strip():
        termo = f.busca.strip().lower()
        texto = (r["titulo"].fillna("") + " " + r["empresa"].fillna("") + " " + r["descricao"].fillna("")
                 + " " + r["tecnologias"].apply(lambda ts: " ".join(ts or []))).str.lower()
        r = r[texto.str.contains(termo, regex=False)]
    return r


ORDENACOES = {
    "compatibilidade": ("Maior compatibilidade", ["compatibilidade", "publicada_em"], False),
    "publicacao": ("Publicação mais recente", ["publicada_em", "compatibilidade"], False),
    "radar": ("Entrada mais recente no radar", ["primeira_coleta", "compatibilidade"], False),
    "empresa": ("Empresa (A–Z)", ["empresa", "compatibilidade"], True),
}


def ordenar(df: pd.DataFrame, criterio: str) -> pd.DataFrame:
    _, colunas, crescente = ORDENACOES.get(criterio, ORDENACOES["compatibilidade"])
    if crescente:
        return df.sort_values(colunas, ascending=[True, False], na_position="last")
    return df.sort_values(colunas, ascending=False, na_position="last")


def filtros_ativos(f: Filtros, padrao: Filtros) -> int:
    """Quantos filtros estão diferentes do padrão (para mostrar no botão de limpar)."""
    return sum(getattr(f, c) != getattr(padrao, c) for c in Filtros.__dataclass_fields__)


def dias_com_vagas(df: pd.DataFrame, limite: int = 7) -> list[tuple[date, int]]:
    """Os dias mais recentes em que o radar encontrou vagas, com quantas (mais recente primeiro)."""
    if df.empty:
        return []
    contagem = dia_encontrada(df).value_counts().sort_index(ascending=False)
    return [(d, int(n)) for d, n in contagem.head(limite).items()]


def dia_padrao(df: pd.DataFrame, hoje: date | None = None) -> date:
    """Hoje, se o radar já encontrou vagas hoje; senão, o último dia em que encontrou."""
    hoje = hoje or pd.Timestamp.now(tz=FUSO).date()
    dias = [d for d, _ in dias_com_vagas(df, limite=1000) if d <= hoje]
    return hoje if not dias or dias[0] == hoje else dias[0]


def historico_da_vaga(hist: pd.DataFrame, vaga_id: str) -> pd.DataFrame:
    if hist.empty:
        return hist
    return hist[hist["vaga_id"] == vaga_id].sort_values("em", ascending=False)
