"""Candidaturas: acompanhamento em tabela (edição) e kanban, usando só os status que já existem."""

import pandas as pd
import streamlit as st

from vagas import db
from vagas import relatorios as r
from vagas.painel import logica, ui
from vagas.painel.acoes import ROTULO_STATUS, dialogo_detalhes, mudar_andamento, mudar_status
from vagas.painel.comum import CANDIDATURA, carregar_vagas, historico, limpar_cache, quando


# --------------------------------------------------------------------------- dados
def preparar(cands: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta dias sem retorno e próxima ação recomendada."""
    c = cands.copy()
    c["dias_sem_retorno"] = c.apply(
        lambda x: x["dias_desde"] if x["status"] == "candidatei" else None, axis=1)
    acoes = c.apply(lambda x: logica.proxima_acao(x["status"], x["dias_desde"]), axis=1)
    c["proxima_acao"] = [a[0] for a in acoes]
    c["tom_acao"] = [a[1] for a in acoes]
    return c


# --------------------------------------------------------------------------- tabela editável
def versao_tabela(nome: str) -> int:
    """Cada tabela editável usa uma chave com versão: depois de salvar, a versão sobe e a
    tabela é recriada a partir do banco (sem edições pendentes reaplicadas por engano)."""
    return st.session_state.setdefault(f"versao-{nome}", 0)


def salvou_tabela(nome: str, mensagem: str) -> None:
    st.session_state[f"versao-{nome}"] += 1
    limpar_cache()
    st.toast(mensagem, icon="💾")
    st.rerun()


def tabela_candidaturas(cands: pd.DataFrame, chave: str = "cand") -> None:
    """Tabela editável: Andamento e Observação salvam na hora. Usada aqui e nos Relatórios."""
    rotulo = {s: ROTULO_STATUS[s] for s in CANDIDATURA}
    status_de = {v: k for k, v in rotulo.items()}
    c = preparar(cands)
    tabela = pd.DataFrame({
        "id": c["id"], "empresa": c["empresa"].fillna("—"), "titulo": c["titulo"],
        "andamento": c["status"].map(rotulo), "proxima_acao": c["proxima_acao"],
        "candidatou_em": c["candidatou_em"], "ultima_mov": c["status_em"],
        "dias_sem_retorno": c["dias_sem_retorno"], "nota": c["nota"].fillna(""), "url": c["url"],
    }).reset_index(drop=True)
    editado = st.data_editor(
        tabela, key=f"{chave}-{versao_tabela(chave)}", hide_index=True, width="stretch",
        column_order=["empresa", "titulo", "andamento", "proxima_acao", "candidatou_em", "ultima_mov",
                      "dias_sem_retorno", "nota", "url"],
        disabled=["empresa", "titulo", "proxima_acao", "candidatou_em", "ultima_mov", "dias_sem_retorno", "url"],
        column_config={
            "empresa": st.column_config.TextColumn("Empresa", width=150),
            "titulo": st.column_config.TextColumn("Cargo", width=260),
            "andamento": st.column_config.SelectboxColumn("Status", options=list(rotulo.values()), required=True,
                                                          help="Mude quando a empresa responder", width=120),
            "proxima_acao": st.column_config.TextColumn("Próxima ação", width=240),
            "candidatou_em": st.column_config.DatetimeColumn("Candidatura", format="DD/MM/YYYY"),
            "ultima_mov": st.column_config.DatetimeColumn("Última movimentação", format="DD/MM/YYYY"),
            "dias_sem_retorno": st.column_config.NumberColumn("Dias sem retorno", format="%d"),
            "nota": st.column_config.TextColumn("Observação", width="large"),
            "url": st.column_config.LinkColumn("Vaga", display_text="abrir ↗", width="small"),
        },
    )
    mudou = False
    for antes, depois in zip(tabela.itertuples(), editado.itertuples()):
        if depois.andamento != antes.andamento:
            db.definir_status(antes.id, status_de[depois.andamento])
            mudou = True
        if (depois.nota or "") != antes.nota:
            db.definir_nota(antes.id, depois.nota or "")
            mudou = True
    if mudou:
        salvou_tabela(chave, "Candidaturas atualizadas")


# --------------------------------------------------------------------------- kanban
def _kanban(c: pd.DataFrame) -> None:
    colunas = st.columns(len(CANDIDATURA), gap="small")
    for col, status in zip(colunas, CANDIDATURA):
        rotulo, tom, ic = ui.STATUS_UI[status]
        grupo = c[c["status"] == status]
        with col:
            st.html(f'<div class="rv-kan-cab">{ui.badge(rotulo, tom, ic)}'
                    f'<span class="rv-meta">{len(grupo)}</span></div>')
            if grupo.empty:
                st.html('<div class="rv-vazio" style="padding:16px 8px"><div class="rv-vazio-txt">Nenhuma</div></div>')
            for _, v in grupo.iterrows():
                with st.container(border=True):
                    st.html(
                        f'<div class="rv-kan"><div class="rv-linha-tit">{ui.esc(v.get("empresa") or "Empresa não identificada")}</div>'
                        f'<div class="rv-linha-sub" style="white-space:normal">{ui.esc(v["titulo"])}</div>'
                        f'<div class="rv-metas" style="margin-top:6px">'
                        f'{ui.meta("calendar", "Candidatura " + quando(v["candidatou_em"]))}</div>'
                        + (f'<div class="rv-badges">{ui.badge(v["proxima_acao"], v["tom_acao"], "arrow-right")}</div>'
                           if v["proxima_acao"] else "") + "</div>"
                    )
                    chave = f"kan-{v['id']}"
                    st.selectbox("Mover para", CANDIDATURA, index=CANDIDATURA.index(status), key=chave,
                                 format_func=ROTULO_STATUS.get, label_visibility="collapsed",
                                 on_change=mudar_andamento, args=(v["id"], chave))
                    if st.button("Detalhes", key=f"kan-d-{v['id']}", type="tertiary", icon=":material/visibility:"):
                        dialogo_detalhes(v.to_dict())


# --------------------------------------------------------------------------- página
def pagina() -> None:
    ui.cabecalho("Candidaturas", "Acompanhe cada processo e saiba qual é o próximo passo.", "send")
    df = carregar_vagas()
    hist = historico()
    cands = r.minhas_candidaturas(df, hist) if not df.empty else pd.DataFrame()

    if cands.empty:
        ui.vazio("Nenhuma candidatura registrada",
                 "Na página <b>Vagas</b>, use o botão de enviar (✈) para registrar uma candidatura. "
                 "Ela aparece aqui com o próximo passo recomendado.", "send")
    else:
        s = r.resumo_candidaturas(df, hist)
        c = preparar(cands)
        sem_retorno = int((c["dias_sem_retorno"].fillna(0) >= r.DIAS_PARA_COBRAR).sum())
        ui.kpis([
            {"rotulo": "Candidaturas", "valor": s["candidaturas"], "icone": "send", "tom": "primario"},
            {"rotulo": "Taxa de resposta", "valor": "—" if s["taxa_resposta"] is None else f"{s['taxa_resposta']:.0%}",
             "icone": "message-square", "tom": "info", "ajuda": "Candidaturas com retorno (entrevista, proposta ou recusa)."},
            {"rotulo": "Entrevistas", "valor": s["entrevistas"], "icone": "message-square", "tom": "info"},
            {"rotulo": "Propostas", "valor": s["propostas"], "icone": "award", "tom": "sucesso"},
            {"rotulo": "Sem retorno há 7+ dias", "valor": sem_retorno, "icone": "hourglass",
             "tom": "atencao" if sem_retorno else "sucesso",
             "detalhe": "hora de cobrar" if sem_retorno else "nenhuma atrasada"},
        ])
        if s["candidaturas"] and not s["entrevistas"] and not s["recusados"]:
            st.info("Quando uma empresa responder, mude o **Status** da candidatura (entrevista, proposta ou "
                    "recusado). É isso que calcula a taxa de resposta e o funil.", icon=":material/lightbulb:")

        modo = st.segmented_control("Visualização", ["Tabela", "Kanban"], default="Tabela", key="cand-modo",
                                    label_visibility="collapsed")
        with st.container(border=True):
            if modo == "Kanban":
                ui.secao("Quadro de candidaturas", "kanban", "Mude a etapa pelo seletor de cada cartão.")
                _kanban(c)
            else:
                ui.secao("Minhas candidaturas", "clipboard-list",
                         "Edite <b>Status</b> e <b>Observação</b> direto na tabela. Salva na hora.")
                tabela_candidaturas(cands)

    inter = r.interessadas_pendentes(df, hist) if not df.empty else pd.DataFrame()
    with st.container(border=True):
        ui.secao("Interessei, mas ainda não me candidatei", "star",
                 "Vagas marcadas com interesse esperando sua candidatura.")
        if inter.empty:
            ui.vazio("Nenhuma vaga parada", "Marque vagas com a estrela na página Vagas para separá-las aqui.", "star")
        for _, v in inter.iterrows():
            rotulo, tom = logica.classificar_nota(v["compatibilidade"])
            c1, c2, c3 = st.columns([1, 6, 2.4], vertical_alignment="center")
            c1.html(ui.nota_bloco(v["compatibilidade"], rotulo, tom, compacto=True))
            c2.html(f'<div class="rv-linha-tit"><a href="{ui.url_segura(v["url"])}" target="_blank" '
                    f'rel="noopener noreferrer">{ui.esc(v["titulo"])}</a></div>'
                    f'<div class="rv-linha-sub">{ui.esc(v.get("empresa") or "Empresa não identificada")} · '
                    f'marcada {quando(v["marcada_em"])}</div>')
            with c3, st.container(horizontal=True, gap="small"):
                st.button("Candidatei", key=f"int-c-{v['id']}", icon=":material/send:", type="primary",
                          on_click=mudar_status, args=(v["id"], "candidatei"))
                if st.button("", key=f"int-d-{v['id']}", icon=":material/visibility:", help="Detalhes"):
                    dialogo_detalhes(v.to_dict())
