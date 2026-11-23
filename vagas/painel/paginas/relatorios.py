"""Relatórios: seis categorias, todas na tela. Os cálculos ficam em vagas/relatorios.py."""

import altair as alt
import pandas as pd
import streamlit as st

from vagas import db
from vagas import relatorios as r
from vagas.painel import graficos as g
from vagas.painel import ui
from vagas.painel.comum import (
    MODELOS, MOTIVOS_DESCARTE, NIVEIS, SEM_MOTIVO, carregar_base, dados_relatorios,
)
from vagas.painel.navegacao import ir_para
from vagas.painel.paginas.candidaturas import salvou_tabela, tabela_candidaturas, versao_tabela

ORDEM_FONTES = ["adzuna", "linkedin", "glassdoor", "indeed", "github", "gupy", "catho", "infojobs"]
SITUACOES = ["Você domina", "Você conhece", "Não está no seu perfil"]
PERIODOS = {7: "7 dias", 30: "30 dias", 90: "90 dias", 365: "1 ano", None: "Tudo"}

DICAS_DESCARTE = {
    "Nível acima do meu (sênior/especialista)":
        "Vagas sênior já ficam fora do filtro \"Só meu perfil\". As que você descartou por nível "
        "não diziam o nível no título: vale abrir a descrição antes de descartar.",
    "Não é Laravel/PHP (stack diferente)":
        "Se isso vem muito de alertas por e-mail, ajuste o termo do alerta (ex.: \"Laravel\" em vez de "
        "\"desenvolvedor backend\").",
    "Presencial ou híbrido fora da minha região":
        "Deixe só \"Remoto\" no filtro de modalidade da página Vagas para esconder essas.",
    "Repetida / já me candidatei antes":
        "Vagas repetidas entre fontes são unidas pelo título e empresa. As que escapam costumam ter o "
        "título escrito diferente em cada site; anote no detalhe qual era a original.",
}


def _cartao(titulo: str, icone: str, descricao: str | None = None):
    """Contêiner branco com título de seção (use com `with`)."""
    c = st.container(border=True)
    with c:
        ui.secao(titulo, icone, descricao)
    return c


def _tabela_vagas(df: pd.DataFrame, colunas: dict) -> None:
    config = {"url": st.column_config.LinkColumn("Vaga", display_text="abrir ↗", width="small")}
    for col, rotulo in colunas.items():
        if col == "compatibilidade":
            config[col] = st.column_config.ProgressColumn(rotulo, min_value=0, max_value=100, format="%d")
        elif col.endswith("_em"):
            config[col] = st.column_config.DatetimeColumn(rotulo, format="DD/MM/YYYY")
        else:
            config[col] = st.column_config.Column(rotulo)
    st.dataframe(df[list(colunas) + ["url"]], hide_index=True, width="stretch", column_config=config)


def tabela_descartadas(desc: pd.DataFrame) -> None:
    opcoes = MOTIVOS_DESCARTE + [SEM_MOTIVO]
    tabela = pd.DataFrame({
        "id": desc["id"], "restaurar": False, "descartada_em": desc["status_em"],
        "empresa": desc["empresa"].fillna("—"), "titulo": desc["titulo"],
        "motivo": desc["motivo_descarte"].where(desc["motivo_descarte"].isin(opcoes), SEM_MOTIVO),
        "detalhe": desc["detalhe_descarte"].fillna(""), "compatibilidade": desc["compatibilidade"],
        "url": desc["url"],
    }).reset_index(drop=True)
    editado = st.data_editor(
        tabela, key=f"desc-{versao_tabela('desc')}", hide_index=True, width="stretch",
        column_order=["restaurar", "descartada_em", "empresa", "titulo", "motivo", "detalhe", "compatibilidade", "url"],
        disabled=["descartada_em", "empresa", "titulo", "compatibilidade", "url"],
        column_config={
            "restaurar": st.column_config.CheckboxColumn("Restaurar", help="Volta a vaga para 'nova'", width="small"),
            "descartada_em": st.column_config.DatetimeColumn("Descartada em", format="DD/MM/YYYY"),
            "empresa": "Empresa", "titulo": "Cargo",
            "motivo": st.column_config.SelectboxColumn("Motivo", options=opcoes, required=True, width="medium"),
            "detalhe": st.column_config.TextColumn("Detalhe", width="medium"),
            "compatibilidade": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%d"),
            "url": st.column_config.LinkColumn("Vaga", display_text="abrir ↗", width="small"),
        },
    )
    mudou = False
    for antes, depois in zip(tabela.itertuples(), editado.itertuples()):
        if depois.restaurar:
            db.definir_status(antes.id, None)
            mudou = True
        elif depois.motivo != antes.motivo or (depois.detalhe or "") != antes.detalhe:
            db.definir_motivo(antes.id, None if depois.motivo == SEM_MOTIVO else depois.motivo, depois.detalhe)
            mudou = True
    if mudou:
        salvou_tabela("desc", "Descartadas atualizadas")


# =========================================================================== página
def pagina() -> None:
    ui.cabecalho("Relatórios", "Entenda sua busca, o mercado e onde estão as melhores oportunidades.",
                 "chart-column")
    vagas, hist, execucoes = dados_relatorios()
    if vagas.empty:
        ui.vazio("Sem dados para relatórios", "Rode uma coleta em <b>Configurações</b> para começar.", "chart-column")
        return

    fontes_disp = [x for x in ORDEM_FONTES if x in set(vagas["fonte"])] + \
                  sorted(set(vagas["fonte"]) - set(ORDEM_FONTES))
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns([1.1, 1.3, 1.8, 1.8], vertical_alignment="bottom")
        dias = f1.selectbox("Período", list(PERIODOS), index=2, format_func=PERIODOS.get)
        escopo = f2.segmented_control("Vagas", ["Meu perfil", "Todas"], default="Meu perfil",
                                      help="Meu perfil = Laravel júnior/pleno (e PHP dos alertas de e-mail).")
        fontes = f3.multiselect("Fontes", fontes_disp, placeholder="Todas",
                                format_func=lambda f: ui.FONTE_UI.get(f, (f,))[0])
        modelos = f4.multiselect("Modalidade", list(MODELOS), format_func=MODELOS.get, placeholder="Todas")
    so_alvo = escopo != "Todas"

    df = r.filtrar(vagas, dias=dias, so_alvo=so_alvo, fontes=fontes, modelos=modelos)
    # Candidaturas e descartes valem mesmo fora do perfil
    df_cand = r.filtrar(vagas, dias=dias, so_alvo=False, fontes=fontes, modelos=modelos)
    perfil = (carregar_base() or {}).get("pontuacao", {})
    st.caption(f"**{len(df)}** vagas no recorte · o período considera a data de publicação "
               "(vagas que você marcou no período também entram).")

    abas = st.tabs([":material/send: Candidaturas", ":material/delete: Descartadas", ":material/trending_up: Mercado",
                    ":material/code: Stack", ":material/apartment: Empresas", ":material/hub: Fontes"])
    with abas[0]:
        aba_candidaturas(df, df_cand, hist)
    with abas[1]:
        aba_descartadas(df_cand)
    with abas[2]:
        aba_mercado(df, fontes_disp)
    with abas[3]:
        aba_stack(df, perfil)
    with abas[4]:
        aba_empresas(df)
    with abas[5]:
        aba_fontes(vagas, fontes_disp)


# --------------------------------------------------------------------------- abas
def aba_candidaturas(df: pd.DataFrame, df_cand: pd.DataFrame, hist: pd.DataFrame) -> None:
    s = r.resumo_candidaturas(df_cand, hist)
    pct = lambda x: "—" if x is None else f"{x:.0%}"  # noqa: E731
    tempo = r.tempo_ate_candidatar(df_cand, hist)
    ui.kpis([
        {"rotulo": "Candidaturas", "valor": s["candidaturas"], "icone": "send"},
        {"rotulo": "Taxa de resposta", "valor": pct(s["taxa_resposta"]), "icone": "message-square", "tom": "info",
         "ajuda": "Candidaturas que tiveram retorno (entrevista, proposta ou recusa)."},
        {"rotulo": "Entrevistas", "valor": s["entrevistas"], "icone": "message-square",
         "tom": "info", "detalhe": f"{pct(s['taxa_entrevista'])} das candidaturas"},
        {"rotulo": "Propostas", "valor": s["propostas"], "icone": "award", "tom": "sucesso"},
        {"rotulo": "Interessadas", "valor": s["interessa"], "icone": "star", "tom": "atencao",
         "ajuda": "Marcadas com interesse e ainda sem candidatura."},
        {"rotulo": "Dias até se candidatar", "valor": "—" if tempo is None else f"{tempo:g}", "icone": "clock",
         "tom": "neutro", "ajuda": "Mediana de dias entre a vaga aparecer no radar e você se candidatar."},
    ])
    if s["candidaturas"] and not s["entrevistas"] and not s["recusados"]:
        st.info("Quando uma empresa responder, mude o **Status** da candidatura (tabela abaixo ou página "
                "Candidaturas). É isso que alimenta a taxa de resposta e o funil.", icon=":material/lightbulb:")

    e, d = st.columns(2, gap="medium")
    with e, _cartao("Funil", "list-checks", f"De {len(df_cand)} vagas no período, quantas chegaram a cada etapa"):
        dados = r.funil(df_cand, hist)
        g.mostrar(g.barras(dados, "etapa", "vagas", "Vagas", ordenar=False), dados, "funil")
    with d, _cartao("Candidaturas por semana", "calendar"):
        dados = r.candidaturas_por_semana(df_cand, hist)
        if dados.empty:
            ui.vazio("Nenhuma candidatura no período", "As candidaturas registradas aparecem aqui por semana.", "calendar")
        else:
            g.mostrar(g.colunas_semanais(dados, "candidaturas", "Candidaturas"), dados, "cand-semana")

    with _cartao("Empresas em que me candidatei", "clipboard-list",
                 "Edite <b>Status</b> e <b>Observação</b> direto na tabela. Salva na hora."):
        cands = r.minhas_candidaturas(df_cand, hist)
        if cands.empty:
            ui.vazio("Nenhuma candidatura no período", "Registre candidaturas na página Vagas.", "send")
        else:
            tabela_candidaturas(cands, chave="rel-cand")

    e, d = st.columns(2, gap="medium")
    with e, _cartao("Interessei, mas não me candidatei", "star"):
        inter = r.interessadas_pendentes(df_cand, hist)
        if inter.empty:
            ui.vazio("Nenhuma vaga parada", "Vagas com interesse e sem candidatura aparecem aqui.", "star")
        else:
            _tabela_vagas(inter, {"compatibilidade": "Nota", "titulo": "Cargo", "empresa": "Empresa",
                                  "dias_parada": "Dias parada"})
    with d, _cartao("Boas vagas que você ainda não marcou", "eye", "Nota ≥ 75, publicadas nos últimos 14 dias"):
        esq = r.esquecidas(df)
        if esq.empty:
            ui.vazio("Nada esquecido", "Nenhuma vaga boa e recente esperando você.", "circle-check")
        else:
            _tabela_vagas(esq.head(15), {"compatibilidade": "Nota", "titulo": "Cargo", "empresa": "Empresa",
                                         "publicada_em": "Publicada em"})


def aba_descartadas(df_cand: pd.DataFrame) -> None:
    desc = r.descartadas(df_cand)
    if desc.empty:
        ui.vazio("Nenhuma vaga descartada no período",
                 "Ao descartar uma vaga, o motivo escolhido aparece aqui.", "trash-2")
        return
    motivos = r.motivos_descarte(desc)
    com_motivo = desc[desc["motivo_descarte"] != SEM_MOTIVO]
    marcadas = df_cand[df_cand["status"] != "nova"]
    top = motivos[motivos["motivo"] != SEM_MOTIVO]
    ui.kpis([
        {"rotulo": "Descartadas", "valor": len(desc), "icone": "trash-2", "tom": "neutro"},
        {"rotulo": "Das vagas que você avaliou", "valor": f"{len(desc) / len(marcadas):.0%}" if len(marcadas) else "—",
         "icone": "activity", "tom": "neutro",
         "ajuda": "Descartadas ÷ vagas que você marcou de alguma forma."},
        {"rotulo": "Motivo mais comum", "valor": top.iloc[0]["motivo"].split(" (")[0] if not top.empty else "—",
         "icone": "info", "tom": "atencao" if not top.empty else "neutro"},
    ])
    sem = len(desc) - len(com_motivo)
    if sem:
        st.info(f"{sem} vaga(s) foram descartadas antes de existir o motivo. Preencha a coluna **Motivo** na "
                "tabela abaixo para o gráfico ficar completo.", icon=":material/edit_note:")

    e, d = st.columns([3, 2], gap="medium")
    with e, _cartao("Por que você descarta", "chart-column"):
        g.mostrar(g.barras(motivos, "motivo", "vagas", "Vagas"), motivos, "motivos")
    with d, _cartao("Dica", "lightbulb"):
        if not top.empty and top.iloc[0]["motivo"] in DICAS_DESCARTE:
            st.markdown(DICAS_DESCARTE[top.iloc[0]["motivo"]])
        else:
            st.caption("Registre o motivo dos descartes para receber uma dica sobre o mais frequente.")

    with _cartao("Vagas descartadas", "trash-2",
                 "Marque <b>Restaurar</b> para a vaga voltar como nova, ou corrija o motivo e o detalhe."):
        tabela_descartadas(desc)


def aba_mercado(df: pd.DataFrame, fontes_disp: list[str]) -> None:
    if df.empty:
        ui.vazio("Sem vagas no recorte", "Ajuste os filtros acima.", "trending-up")
        return
    semanas = max(1, (df["publicada_em"].max() - df["publicada_em"].min()).days / 7)
    ui.kpis([
        {"rotulo": "Vagas no recorte", "valor": len(df), "icone": "briefcase-business"},
        {"rotulo": "Média por semana", "valor": f"{len(df) / semanas:.0f}", "icone": "calendar"},
        {"rotulo": "Remotas", "valor": f"{(df['modelo_trabalho'] == 'remoto').mean():.0%}", "icone": "house",
         "tom": "sucesso"},
        {"rotulo": "Júnior/pleno no título", "valor": f"{df['nivel'].isin(['junior', 'pleno']).mean():.0%}",
         "icone": "award", "tom": "neutro", "ajuda": "O resto não informa o nível (ou é sênior, no escopo Todas)."},
    ])
    with _cartao("Vagas novas por semana", "trending-up", "Por fonte, pela data de publicação"):
        dados = r.vagas_por_semana(df)
        g.mostrar(g.colunas_semanais(dados, "vagas", "Vagas", cor_por="fonte", dominio=fontes_disp), dados, "semana")

    e, d = st.columns(2, gap="medium")
    with e:
        with _cartao("Modalidade", "house"):
            dados = r.distribuicao(df, "modelo_trabalho", {k: v for k, v in MODELOS.items() if k})
            g.mostrar(g.barras(dados, "categoria", "vagas", "Vagas", ordenar=False), dados, "modelo")
        with _cartao("Dia da semana em que as vagas saem", "calendar"):
            dados = r.por_dia_da_semana(df)
            g.mostrar(g.barras(dados, "dia", "vagas", "Vagas", ordenar=False), dados, "dia")
    with d:
        with _cartao("Nível", "award"):
            dados = r.distribuicao(df, "nivel", {k: v for k, v in NIVEIS.items() if k})
            g.mostrar(g.barras(dados, "categoria", "vagas", "Vagas", ordenar=False), dados, "nivel")
        with _cartao("Onde estão as vagas híbridas e presenciais", "map-pin"):
            dados = r.locais(df)
            if dados.empty:
                ui.vazio("Nenhuma com local informado", "As vagas do recorte são remotas ou sem local.", "map-pin")
            else:
                g.mostrar(g.barras(dados, "local", "vagas", "Vagas"), dados, "locais")


def aba_stack(df: pd.DataFrame, perfil: dict) -> None:
    if df.empty:
        ui.vazio("Sem vagas no recorte", "Ajuste os filtros acima.", "code-xml")
        return
    tec = r.tecnologias(df, perfil)
    lacunas = tec[tec["situacao"] == "Não está no seu perfil"]
    ui.kpis([
        {"rotulo": "Nota média", "valor": f"{df['compatibilidade'].mean():.0f}", "icone": "target"},
        {"rotulo": "Vagas com nota alta (≥ 75)", "valor": f"{(df['compatibilidade'] >= 75).mean():.0%}",
         "icone": "circle-check", "tom": "sucesso"},
        {"rotulo": "Tecnologias fora do seu perfil", "valor": len(lacunas), "icone": "graduation-cap",
         "tom": "atencao" if len(lacunas) else "sucesso"},
    ])
    with _cartao("O que as vagas pedem", "code-xml",
                 "% das vagas que citam cada tecnologia; a cor mostra como ela está no seu perfil. "
                 "Vagas de e-mail só têm o título e contribuem pouco aqui."):
        top = tec.head(18)
        dica = [alt.Tooltip("tecnologia:N", title="Tecnologia"), alt.Tooltip("vagas:Q", title="Vagas"),
                alt.Tooltip("pct:Q", title="Das vagas", format=".0%"), alt.Tooltip("situacao:N", title="No seu perfil")]
        g.mostrar(g.barras(top, "tecnologia", "pct", "Das vagas", cor_por="situacao", dominio=SITUACOES,
                           formato=".0%", dica=dica), top, "tec")

    e, d = st.columns(2, gap="medium")
    with e, _cartao("O que estudar", "graduation-cap", "Fora do seu perfil, das mais pedidas para as menos"):
        if lacunas.empty:
            ui.vazio("Nada pendente", "Todas as tecnologias pedidas já estão no seu perfil.", "circle-check")
        else:
            st.html(ui.lista_itens([f"{l['tecnologia']} — {l['pct']:.0%} das vagas ({l['vagas']})"
                                    for _, l in lacunas.head(8).iterrows()], "graduation-cap", "atencao"))
            st.caption("Se você já usou alguma, inclua no currículo base: a nota e as sugestões passam a considerar.")
    with d, _cartao("Distribuição das notas", "chart-column"):
        dados = r.faixas_de_nota(df)
        g.mostrar(g.barras(dados, "faixa", "vagas", "Vagas", ordenar=False), dados, "notas")


def aba_empresas(df: pd.DataFrame) -> None:
    emp = r.empresas(df)
    if emp.empty:
        ui.vazio("Sem empresas identificadas", "As vagas do recorte não informam a empresa.", "building-2")
        return
    with _cartao("Quem mais anuncia vagas", "building-2"):
        top = emp.head(12)
        g.mostrar(g.barras(top, "empresa", "vagas", "Vagas"), top, "empresas-graf")
    with _cartao("Detalhe por empresa", "clipboard-list",
                 "Sua situação = a etapa mais avançada que você atingiu em alguma vaga da empresa."):
        tabela = emp.assign(sua_situacao=emp["sua_situacao"].map(lambda s: ui.STATUS_UI.get(s, ui.STATUS_UI["nova"])[0]))
        st.dataframe(
            tabela, hide_index=True, width="stretch",
            column_config={
                "empresa": "Empresa", "vagas": "Vagas",
                "nota_media": st.column_config.ProgressColumn("Nota média", min_value=0, max_value=100, format="%d"),
                "ultima_vaga": st.column_config.DatetimeColumn("Última vaga", format="DD/MM/YYYY"),
                "sua_situacao": "Sua situação",
            },
        )


def aba_fontes(vagas: pd.DataFrame, fontes_disp: list[str]) -> None:
    pf = r.por_fonte(vagas)
    pf["nota_media_alvo"] = pf["nota_media_alvo"].astype("Int64")  # fonte sem vaga no perfil fica em branco
    melhor = pf.sort_values("pct_alvo", ascending=False).iloc[0]
    ui.kpis([
        {"rotulo": "Fontes ativas", "valor": len(pf), "icone": "layers"},
        {"rotulo": "Vagas coletadas", "valor": int(pf["vagas"].sum()), "icone": "database"},
        {"rotulo": "Fonte mais certeira", "valor": ui.FONTE_UI.get(melhor["fonte"], (melhor["fonte"],))[0],
         "icone": "target", "tom": "sucesso", "detalhe": f"{melhor['pct_alvo']:.0%} das vagas no seu perfil"},
    ])
    with _cartao("Qual fonte traz vagas que importam para você", "layers",
                 "Todas as vagas já coletadas, sem os filtros acima. Muito volume e pouco perfil = alerta para ajustar."):
        dica = [alt.Tooltip("fonte:N", title="Fonte"), alt.Tooltip("no_alvo:Q", title="No perfil"),
                alt.Tooltip("vagas:Q", title="Total coletado"), alt.Tooltip("pct_alvo:Q", title="% no perfil", format=".0%"),
                alt.Tooltip("nota_media_alvo:Q", title="Nota média no perfil")]
        g.mostrar(g.barras(pf, "fonte", "no_alvo", "Vagas no seu perfil", cor_por="fonte", dominio=fontes_disp,
                           dica=dica))
        st.dataframe(
            pf, hide_index=True, width="stretch",
            column_config={
                "fonte": "Fonte", "vagas": "Coletadas", "no_alvo": "No perfil",
                "pct_alvo": st.column_config.ProgressColumn("% no perfil", min_value=0, max_value=1, format="percent"),
                "nota_media_alvo": st.column_config.NumberColumn("Nota média no perfil", format="%d"),
            },
        )
    if st.button("Ver saúde da coleta e histórico de execuções", icon=":material/monitor_heart:", type="tertiary"):
        ir_para("configuracoes")
