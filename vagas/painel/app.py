"""Painel de vagas. Rodar com:  streamlit run vagas/painel/app.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from vagas import db  # noqa: E402
from vagas.pipeline import rodar  # noqa: E402

st.set_page_config(page_title="Radar de vagas Laravel", page_icon="🎯", layout="wide")

NIVEIS = {"junior": "Júnior", "pleno": "Pleno", "senior": "Sênior", None: "Não informado"}
MODELOS = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial", None: "Não informado"}
FUSO = "America/Sao_Paulo"
STATUS = {"nova": "🆕 Nova", "interessa": "⭐ Interessa", "candidatei": "📨 Candidatei", "descartada": "🗑️ Descartada"}


@st.cache_data(ttl=60)
def carregar(so_alvo: bool) -> pd.DataFrame:
    visao = "gold.vagas_alvo" if so_alvo else "gold.vagas"
    with db.conectar() as conn:
        linhas = conn.execute(f"select * from {visao} order by publicada_em desc nulls last").fetchall()
    df = pd.DataFrame(linhas)
    if not df.empty:
        df["publicada_em"] = pd.to_datetime(df["publicada_em"], utc=True).dt.tz_convert(FUSO)
        # Campos vazios chegam como NaN no pandas; volta para None (NaN é "verdadeiro" em `or`).
        texto = ["empresa", "nivel", "modelo_trabalho", "descricao", "localizacao"]
        df[texto] = df[texto].astype(object).where(df[texto].notna(), None)
    return df


@st.cache_data(ttl=60)
def ultimas_execucoes() -> pd.DataFrame:
    with db.conectar() as conn:
        return pd.DataFrame(
            conn.execute(
                """
                select distinct on (fonte) fonte, finalizada_em, qtd_coletada, qtd_nova, erro
                  from silver.execucoes order by fonte, id desc
                """
            ).fetchall()
        )


def mudar_status(vaga_id: str, status: str | None) -> None:
    db.definir_status(vaga_id, status)
    carregar.clear()


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("Filtros")
    so_alvo = st.toggle("Só Laravel júnior/pleno", value=True,
                        help="Desligue para ver todas as vagas coletadas, de qualquer stack e nível.")
    dias = st.selectbox("Publicadas nos últimos", [7, 30, 90, 365, None], index=2,
                        format_func=lambda d: "Qualquer data" if d is None else f"{d} dias")
    status_sel = st.multiselect("Status", list(STATUS), default=["nova", "interessa"],
                                format_func=STATUS.get)
    modelos_sel = st.multiselect("Modelo de trabalho", list(MODELOS), format_func=MODELOS.get,
                                 placeholder="Todos")
    busca = st.text_input("Buscar no título, empresa ou descrição")

    st.divider()
    if st.button("🔄 Coletar vagas agora", use_container_width=True):
        with st.spinner("Coletando..."):
            resumo = rodar()
        carregar.clear()
        ultimas_execucoes.clear()
        st.success("\n".join(f"**{k}**: {v}" for k, v in resumo.items()))

    execs = ultimas_execucoes()
    if not execs.empty:
        st.caption("Última coleta por fonte")
        for _, e in execs.iterrows():
            fim = e["finalizada_em"]
            quando = pd.Timestamp(fim).tz_convert(FUSO).strftime("%d/%m %H:%M") if pd.notna(fim) else "—"
            if e["erro"]:
                st.caption(f"⚠️ {e['fonte']} ({quando}): {e['erro']}")
            else:
                st.caption(f"✅ {e['fonte']} ({quando}): {e['qtd_coletada']} vagas, {e['qtd_nova']} novas")

# ---------------------------------------------------------------- dados filtrados
df = carregar(so_alvo)
st.title("🎯 Radar de vagas Laravel")

if df.empty:
    st.info("Nenhuma vaga no banco ainda. Clique em **Coletar vagas agora** na barra lateral.")
    st.stop()

agora = pd.Timestamp.now(tz=FUSO)
f = df
if dias:
    f = f[f["publicada_em"] >= agora - pd.Timedelta(days=dias)]
if status_sel:
    f = f[f["status"].isin(status_sel)]
if modelos_sel:
    f = f[f["modelo_trabalho"].isin([m for m in modelos_sel if m]) |
          (f["modelo_trabalho"].isna() & (None in modelos_sel))]
if busca:
    texto = (f["titulo"].fillna("") + " " + f["empresa"].fillna("") + " " + f["descricao"].fillna(""))
    f = f[texto.str.contains(busca, case=False, regex=False)]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vagas na lista", len(f))
c2.metric("Publicadas nos últimos 7 dias", int((df["publicada_em"] >= agora - pd.Timedelta(days=7)).sum()))
c3.metric("⭐ Interessa", int((df["status"] == "interessa").sum()))
c4.metric("📨 Candidatei", int((df["status"] == "candidatei").sum()))

if f.empty:
    st.warning("Nenhuma vaga com esses filtros. Tente aumentar o período ou incluir outros status.")
    st.stop()

# ---------------------------------------------------------------- lista de vagas
for _, v in f.iterrows():
    with st.container(border=True):
        topo, acoes = st.columns([4, 1.4])
        with topo:
            st.markdown(f"#### [{v['titulo']}]({v['url']})")
            data = v["publicada_em"].strftime("%d/%m/%Y") if pd.notna(v["publicada_em"]) else "sem data"
            st.caption(
                f"**{v['empresa'] or 'Empresa não identificada'}** · {NIVEIS.get(v['nivel'])} · "
                f"{MODELOS.get(v['modelo_trabalho'])} · {data} · fonte: {v['fonte']} · {STATUS[v['status']]}"
            )
            if len(v["tecnologias"]):
                st.markdown(" ".join(f"`{t}`" for t in v["tecnologias"]))
        with acoes:
            b1, b2 = st.columns(2)
            b1.button("⭐", key=f"i-{v['id']}", help="Interessa", on_click=mudar_status, args=(v["id"], "interessa"),
                      use_container_width=True)
            b2.button("📨", key=f"c-{v['id']}", help="Candidatei", on_click=mudar_status, args=(v["id"], "candidatei"),
                      use_container_width=True)
            b3, b4 = st.columns(2)
            b3.button("🗑️", key=f"d-{v['id']}", help="Descartar", on_click=mudar_status, args=(v["id"], "descartada"),
                      use_container_width=True)
            b4.button("↩️", key=f"n-{v['id']}", help="Voltar para nova", on_click=mudar_status, args=(v["id"], None),
                      use_container_width=True, disabled=v["status"] == "nova")
        if v["descricao"]:
            with st.expander("Ver descrição"):
                st.markdown(v["descricao"])
