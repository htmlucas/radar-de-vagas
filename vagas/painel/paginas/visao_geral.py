"""Visão geral: um resumo inteligente da busca, para abrir o dia."""

import altair as alt
import pandas as pd
import streamlit as st

from vagas import relatorios as r
from vagas.painel import graficos, logica, ui
from vagas.painel.acoes import dialogo_detalhes
from vagas.painel.comum import EM_ANDAMENTO, carregar_base, carregar_vagas, historico, quando
from vagas.painel.navegacao import ir_para

SEMANAS_EVOLUCAO = 12


def _evolucao(df: pd.DataFrame) -> pd.DataFrame:
    corte = pd.Timestamp.now(tz=r.FUSO) - pd.Timedelta(weeks=SEMANAS_EVOLUCAO)
    f = df[df["publicada_em"] >= corte].dropna(subset=["publicada_em"])
    if f.empty:
        return pd.DataFrame()
    semana = f["publicada_em"].dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    return (pd.DataFrame({"semana": semana, "Todas as vagas": 1, "No seu perfil": f["alvo"].astype(int)})
            .groupby("semana").sum().reset_index())


def _linha_vaga(v: dict, prefixo: str, extra: str = "") -> None:
    rotulo, tom = logica.classificar_nota(v.get("compatibilidade"))
    modal = ui.MODALIDADE_UI.get(v.get("modelo_trabalho"), ui.MODALIDADE_UI[None])[0]
    c1, c2, c3 = st.columns([1, 6, 1.6], vertical_alignment="center", gap="small")
    c1.html(ui.nota_bloco(v.get("compatibilidade"), rotulo, tom, compacto=True))
    c2.html(
        f'<div class="rv-linha-txt"><div class="rv-linha-tit"><a href="{ui.url_segura(v["url"])}" target="_blank" '
        f'rel="noopener noreferrer">{ui.esc(v["titulo"])}</a></div>'
        f'<div class="rv-linha-sub">{ui.esc(v.get("empresa") or "Empresa não identificada")} · {modal}'
        f' · {quando(v.get("publicada_em"))}{extra}</div></div>'
    )
    if c3.button("Detalhes", key=f"{prefixo}-{v['id']}", width="stretch", type="tertiary",
                 icon=":material/visibility:"):
        dialogo_detalhes(v)


def pagina() -> None:
    df = carregar_vagas()
    hoje = pd.Timestamp.now(tz=r.FUSO)
    ui.cabecalho("Visão geral", f"Resumo da sua busca · {hoje.strftime('%d/%m/%Y')}", "layout-dashboard")
    if df.empty:
        ui.vazio("Seu radar ainda está vazio",
                 "Vá em <b>Configurações</b> e clique em <b>Coletar agora</b> para buscar as primeiras vagas.")
        return

    hist = historico()
    ativas = df[df["status"] != "descartada"]
    perfil = ativas[ativas["alvo"]]
    semana = perfil[perfil["publicada_em"] >= hoje - pd.Timedelta(days=7)]
    andamento = df[df["status"].isin(EM_ANDAMENTO)]
    cobrar = r.aguardando_retorno(df, hist)
    cobrar = cobrar[cobrar["dias_sem_retorno"] >= r.DIAS_PARA_COBRAR] if not cobrar.empty else cobrar
    entrevistas = int((df["status"] == "entrevista").sum())
    fontes = sorted({f for fs in df["fontes"] for f in fs})

    ui.kpis([
        {"rotulo": "Vagas encontradas", "valor": len(df), "icone": "radar", "tom": "primario",
         "detalhe": f"em {len(fontes)} fontes"},
        {"rotulo": "No seu perfil", "valor": len(perfil), "icone": "target", "tom": "primario",
         "detalhe": f"{len(perfil) / max(len(ativas), 1):.0%} das vagas ativas",
         "ajuda": "Laravel júnior/pleno (e PHP de alertas por e-mail), sem as descartadas."},
        {"rotulo": "Novas na semana", "valor": len(semana), "icone": "sparkles", "tom": "sucesso",
         "detalhe": f"{int((semana['status'] == 'nova').sum())} ainda sem avaliação"},
        {"rotulo": "Candidaturas em andamento", "valor": len(andamento), "icone": "send", "tom": "info",
         "detalhe": f"{entrevistas} em entrevista" if entrevistas else "nenhuma entrevista ainda"},
        {"rotulo": "Precisam de acompanhamento", "valor": len(cobrar), "icone": "triangle-alert",
         "tom": "atencao" if len(cobrar) else "sucesso",
         "detalhe": f"sem retorno há {r.DIAS_PARA_COBRAR}+ dias" if len(cobrar) else "tudo em dia"},
    ])

    e, d = st.columns([1.7, 1], gap="medium")
    with e, st.container(border=True):
        ui.secao("Evolução da busca", "trending-up", f"Vagas por semana de publicação (últimas {SEMANAS_EVOLUCAO} semanas)")
        evol = _evolucao(df)
        if evol.empty:
            ui.vazio("Sem vagas recentes", "Nenhuma vaga publicada nas últimas semanas.", "trending-up")
        else:
            graficos.mostrar(graficos.linhas_semanais(evol, ["Todas as vagas", "No seu perfil"], "Vagas", altura=230))
    with d, st.container(border=True):
        ui.secao("Acompanhamento", "list-checks", "O que pede uma ação sua")
        inter = r.interessadas_pendentes(df, hist)
        if cobrar.empty and inter.empty:
            ui.vazio("Tudo em dia", "Nenhuma candidatura sem retorno e nenhuma vaga parada em interesse.", "circle-check")
        for _, c in cobrar.head(4).iterrows():
            _linha_vaga(c.to_dict(), "vg-cob", f' · <b style="color:#b45309">{int(c["dias_sem_retorno"])} dias sem retorno</b>')
        for _, i in inter.head(3).iterrows():
            _linha_vaga(i.to_dict(), "vg-int", " · com interesse, sem candidatura")
        if not cobrar.empty or not inter.empty:
            if st.button("Ver todas as candidaturas", icon=":material/arrow_forward:", type="tertiary"):
                ir_para("candidaturas")

    e, d = st.columns([1.7, 1], gap="medium")
    with e, st.container(border=True):
        ui.secao("Melhores oportunidades", "star", "Do seu perfil, ainda sem candidatura, publicadas nos últimos 30 dias")
        melhores = perfil[perfil["status"].isin(["nova", "interessa"]) &
                          (perfil["publicada_em"] >= hoje - pd.Timedelta(days=30))]
        melhores = melhores.sort_values(["compatibilidade", "publicada_em"], ascending=False).head(6)
        if melhores.empty:
            ui.vazio("Nenhuma oportunidade pendente", "Você já avaliou todas as vagas recentes do seu perfil.", "inbox")
        for _, v in melhores.iterrows():
            _linha_vaga(v.to_dict(), "vg-top")
        if st.button("Ver todas as vagas", icon=":material/arrow_forward:", type="tertiary", key="vg-todas"):
            ir_para("vagas")
    with d, st.container(border=True):
        ui.secao("Mercado", "chart-column", "Tecnologias mais pedidas nas vagas do seu perfil")
        tec = r.tecnologias(perfil, (carregar_base() or {}).get("pontuacao", {})).head(8)
        if tec.empty:
            ui.vazio("Sem dados", "Ainda não há vagas no seu perfil.", "chart-column")
        else:
            dica = [alt.Tooltip("tecnologia:N", title="Tecnologia"),
                    alt.Tooltip("pct:Q", title="Das vagas", format=".0%"),
                    alt.Tooltip("situacao:N", title="No seu perfil")]
            graficos.mostrar(graficos.barras(tec, "tecnologia", "pct", "Das vagas", cor_por="situacao",
                                             dominio=["Você domina", "Você conhece", "Não está no seu perfil"],
                                             formato=".0%", dica=dica, largura_rotulo=110,
                                             legenda_vertical=True))
            recentes = perfil[perfil["publicada_em"] >= hoje - pd.Timedelta(days=90)]
            remoto = (recentes["modelo_trabalho"] == "remoto").mean() if len(recentes) else 0
            st.caption(f"**{remoto:.0%}** das vagas do perfil nos últimos 90 dias são remotas · "
                       f"cerca de **{len(recentes) / 13:.0f}** por semana.")
