"""Cálculos dos relatórios do painel. Funções puras sobre DataFrames (testáveis sem banco/tela)."""

import pandas as pd

FUSO = "America/Sao_Paulo"

# Etapas da candidatura, em ordem. 'recusado' conta como candidatura que teve resposta.
ETAPAS = ["interessa", "candidatei", "entrevista", "proposta"]
ORDEM = {"interessa": 1, "candidatei": 2, "recusado": 2, "entrevista": 3, "proposta": 4}
RESPOSTA = {"entrevista", "proposta", "recusado"}

DIAS_PARA_COBRAR = 7
CANDIDATURA = ["candidatei", "entrevista", "proposta", "recusado"]
SEM_MOTIVO = "Sem motivo registrado"

NIVEIS = {"junior": "Júnior", "pleno": "Pleno", "senior": "Sênior"}
MODELOS = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}
DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


# --------------------------------------------------------------------------- preparo e filtro
def preparar_vagas(linhas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    for col in ("publicada_em", "primeira_coleta", "status_em"):
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(FUSO)
    texto = ["empresa", "nivel", "modelo_trabalho", "localizacao", "nota", "motivo_descarte", "detalhe_descarte"]
    df[texto] = df[texto].astype(object).where(df[texto].notna(), None)
    df["tecnologias"] = df["tecnologias"].apply(lambda t: list(t) if t is not None else [])
    return df


def preparar_historico(linhas: list[dict]) -> pd.DataFrame:
    h = pd.DataFrame(linhas, columns=["vaga_id", "status", "em"])
    if not h.empty:
        h["em"] = pd.to_datetime(h["em"], utc=True).dt.tz_convert(FUSO)
    return h


def filtrar(df: pd.DataFrame, *, dias: int | None, so_alvo: bool, fontes: list[str], modelos: list) -> pd.DataFrame:
    """Filtros da página. O período considera a data de publicação, mas uma vaga com que
    você interagiu no período (status mudou) também entra, mesmo publicada antes."""
    f = df
    if so_alvo:
        f = f[f["alvo"]]
    if fontes:
        f = f[f["fonte"].isin(fontes)]
    if modelos:
        f = f[f["modelo_trabalho"].isin([m for m in modelos if m]) |
              (f["modelo_trabalho"].isna() & (None in modelos))]
    if dias:
        corte = pd.Timestamp.now(tz=FUSO) - pd.Timedelta(days=dias)
        f = f[(f["publicada_em"] >= corte) | (f["status_em"] >= corte)]
    return f


# --------------------------------------------------------------------------- candidaturas
def etapa_maxima(hist: pd.DataFrame) -> pd.Series:
    """A etapa mais avançada que cada vaga já atingiu (pelo histórico, não só pelo status atual)."""
    if hist.empty:
        return pd.Series(dtype=object)
    h = hist[hist["status"].isin(ORDEM)].copy()
    h["ordem"] = h["status"].map(ORDEM)
    return h.sort_values(["ordem", "em"]).groupby("vaga_id")["status"].last()


def resumo_candidaturas(df: pd.DataFrame, hist: pd.DataFrame) -> dict:
    h = hist[hist["vaga_id"].isin(df["id"])]
    passou = set(h["vaga_id"][h["status"].isin({"candidatei", "entrevista", "proposta", "recusado"})])
    respondeu = set(h["vaga_id"][h["status"].isin(RESPOSTA)])
    entrevistas = set(h["vaga_id"][h["status"].isin({"entrevista", "proposta"})])
    return {
        "interessa": int((df["status"] == "interessa").sum()),
        "candidaturas": len(passou),
        "entrevistas": len(entrevistas),
        "propostas": int(h.loc[h["status"] == "proposta", "vaga_id"].nunique()),
        "recusados": int(h.loc[h["status"] == "recusado", "vaga_id"].nunique()),
        "taxa_resposta": (len(respondeu) / len(passou)) if passou else None,
        "taxa_entrevista": (len(entrevistas) / len(passou)) if passou else None,
    }


def funil(df: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Quantas vagas chegaram a cada etapa (uma vaga em 'entrevista' também conta em 'candidatei')."""
    maxima = etapa_maxima(hist[hist["vaga_id"].isin(df["id"])]).map(ORDEM)
    linhas = []
    for nome, rotulo in zip(ETAPAS, ["Interessei", "Me candidatei", "Entrevista", "Proposta"]):
        linhas.append({"etapa": rotulo, "vagas": int((maxima >= ORDEM[nome]).sum())})
    return pd.DataFrame(linhas)


def _data_do_status(hist: pd.DataFrame, status: str) -> pd.Series:
    """Data da última vez que cada vaga entrou no status."""
    h = hist[hist["status"] == status]
    return h.groupby("vaga_id")["em"].max()


def aguardando_retorno(df: pd.DataFrame, hist: pd.DataFrame, agora: pd.Timestamp | None = None) -> pd.DataFrame:
    agora = agora or pd.Timestamp.now(tz=FUSO)
    c = df[df["status"] == "candidatei"].copy()
    if c.empty:
        return c
    c["candidatou_em"] = c["id"].map(_data_do_status(hist, "candidatei")).fillna(c["status_em"])
    c["dias_sem_retorno"] = (agora - c["candidatou_em"]).dt.days
    c["acao"] = c["dias_sem_retorno"].apply(
        lambda d: "📞 Cobrar retorno" if d >= DIAS_PARA_COBRAR else "⏳ Aguardar")
    return c.sort_values("dias_sem_retorno", ascending=False)


def interessadas_pendentes(df: pd.DataFrame, hist: pd.DataFrame, agora: pd.Timestamp | None = None) -> pd.DataFrame:
    agora = agora or pd.Timestamp.now(tz=FUSO)
    i = df[df["status"] == "interessa"].copy()
    if i.empty:
        return i
    i["marcada_em"] = i["id"].map(_data_do_status(hist, "interessa")).fillna(i["status_em"])
    i["dias_parada"] = (agora - i["marcada_em"]).dt.days
    return i.sort_values(["compatibilidade", "dias_parada"], ascending=False)


def tempo_ate_candidatar(df: pd.DataFrame, hist: pd.DataFrame) -> float | None:
    """Mediana de dias entre a vaga aparecer no radar e você se candidatar."""
    cand = _data_do_status(hist, "candidatei")
    base = df.set_index("id")["primeira_coleta"]
    dias = (cand - base.reindex(cand.index)).dropna().dt.total_seconds() / 86400
    return round(float(dias.median()), 1) if len(dias) else None


def candidaturas_por_semana(df: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    h = hist[(hist["status"] == "candidatei") & hist["vaga_id"].isin(df["id"])]
    h = h.drop_duplicates("vaga_id", keep="first")
    if h.empty:
        return pd.DataFrame(columns=["semana", "candidaturas"])
    semana = h["em"].dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    return semana.value_counts().sort_index().rename_axis("semana").reset_index(name="candidaturas")


def minhas_candidaturas(df: pd.DataFrame, hist: pd.DataFrame, agora: pd.Timestamp | None = None) -> pd.DataFrame:
    """Todas as vagas em que você se candidatou, com o andamento atual."""
    agora = agora or pd.Timestamp.now(tz=FUSO)
    c = df[df["status"].isin(CANDIDATURA)].copy()
    if c.empty:
        return c
    primeira = hist[hist["status"] == "candidatei"].groupby("vaga_id")["em"].min()
    c["candidatou_em"] = c["id"].map(primeira).fillna(c["status_em"])
    c["dias_desde"] = (agora - c["candidatou_em"]).dt.days
    return c.sort_values("candidatou_em", ascending=False)


def descartadas(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["status"] == "descartada"].copy()
    d["motivo_descarte"] = d["motivo_descarte"].fillna(SEM_MOTIVO)
    return d.sort_values("status_em", ascending=False)


def motivos_descarte(desc: pd.DataFrame) -> pd.DataFrame:
    if desc.empty:
        return pd.DataFrame(columns=["motivo", "vagas"])
    return desc["motivo_descarte"].value_counts().rename_axis("motivo").reset_index(name="vagas")


def esquecidas(df: pd.DataFrame, nota_minima: int = 75, dias: int = 14) -> pd.DataFrame:
    """Vagas boas e recentes que você ainda nem marcou."""
    corte = pd.Timestamp.now(tz=FUSO) - pd.Timedelta(days=dias)
    f = df[(df["status"] == "nova") & (df["compatibilidade"] >= nota_minima) & (df["publicada_em"] >= corte)]
    return f.sort_values(["compatibilidade", "publicada_em"], ascending=False)


# --------------------------------------------------------------------------- mercado
def vagas_por_semana(df: pd.DataFrame) -> pd.DataFrame:
    f = df.dropna(subset=["publicada_em"])
    if f.empty:
        return pd.DataFrame(columns=["semana", "fonte", "vagas"])
    semana = f["publicada_em"].dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    return (f.assign(semana=semana).groupby(["semana", "fonte"]).size()
            .reset_index(name="vagas").sort_values("semana"))


def distribuicao(df: pd.DataFrame, coluna: str, rotulos: dict) -> pd.DataFrame:
    valores = df[coluna].map(lambda v: rotulos.get(v, "Não informado") if v else "Não informado")
    contagem = valores.value_counts()
    ordem = [r for r in list(rotulos.values()) + ["Não informado"] if r in contagem.index]
    return pd.DataFrame({"categoria": ordem, "vagas": [int(contagem[o]) for o in ordem]})


def por_dia_da_semana(df: pd.DataFrame) -> pd.DataFrame:
    f = df.dropna(subset=["publicada_em"])
    contagem = f["publicada_em"].dt.dayofweek.value_counts()
    return pd.DataFrame({"dia": DIAS_SEMANA, "vagas": [int(contagem.get(i, 0)) for i in range(7)]})


def locais(df: pd.DataFrame, limite: int = 10) -> pd.DataFrame:
    """Onde estão as vagas que exigem ir ao escritório (híbridas e presenciais)."""
    f = df[df["modelo_trabalho"].isin(["hibrido", "presencial"]) & df["localizacao"].notna()]
    local = f["localizacao"].str.replace(r"\s*\(.*\)$", "", regex=True).str.strip()
    return local.value_counts().head(limite).rename_axis("local").reset_index(name="vagas")


# --------------------------------------------------------------------------- stack e perfil
def tecnologias(df: pd.DataFrame, perfil: dict) -> pd.DataFrame:
    """Frequência de cada tecnologia nas vagas e como ela está no seu perfil."""
    if df.empty:
        return pd.DataFrame(columns=["tecnologia", "vagas", "pct", "situacao"])
    dominio, conhece = set(perfil.get("dominio", [])), set(perfil.get("conhecimento", []))
    contagem = df["tecnologias"].explode().dropna().value_counts()
    t = contagem.rename_axis("tecnologia").reset_index(name="vagas")
    t["pct"] = t["vagas"] / len(df)
    t["situacao"] = t["tecnologia"].map(
        lambda x: "Você domina" if x in dominio else "Você conhece" if x in conhece else "Não está no seu perfil")
    return t


def faixas_de_nota(df: pd.DataFrame) -> pd.DataFrame:
    notas = df["compatibilidade"].dropna()
    faixas = pd.cut(notas, bins=range(0, 101, 10), right=False, include_lowest=True,
                    labels=[f"{i}–{i + 9}" for i in range(0, 100, 10)])
    # 100 fica de fora do último intervalo [90, 100): soma nele
    contagem = faixas.value_counts().sort_index()
    contagem.iloc[-1] += int((notas == 100).sum())
    return contagem.rename_axis("faixa").reset_index(name="vagas")


# --------------------------------------------------------------------------- empresas e fontes
def empresas(df: pd.DataFrame, limite: int = 15) -> pd.DataFrame:
    f = df[df["empresa"].notna()]
    if f.empty:
        return pd.DataFrame(columns=["empresa", "vagas", "nota_media", "ultima_vaga", "sua_situacao"])
    g = f.groupby("empresa").agg(
        vagas=("id", "count"),
        nota_media=("compatibilidade", "mean"),
        ultima_vaga=("publicada_em", "max"),
    )
    situacao = f.assign(o=f["status"].map(ORDEM).fillna(0)).sort_values("o").groupby("empresa")["status"].last()
    g["sua_situacao"] = situacao
    g["nota_media"] = g["nota_media"].round(0)
    return g.sort_values(["vagas", "nota_media"], ascending=False).head(limite).reset_index()


def por_fonte(df_todas: pd.DataFrame) -> pd.DataFrame:
    """Qual fonte traz vagas que importam para você (volume, % no alvo, nota)."""
    if df_todas.empty:
        return pd.DataFrame()
    g = df_todas.groupby("fonte").agg(
        vagas=("id", "count"),
        no_alvo=("alvo", "sum"),
        nota_media_alvo=("compatibilidade", lambda s: s[df_todas.loc[s.index, "alvo"]].mean()),
    )
    g["pct_alvo"] = g["no_alvo"] / g["vagas"]
    g["nota_media_alvo"] = g["nota_media_alvo"].round(0)
    return g.sort_values("no_alvo", ascending=False).reset_index()
