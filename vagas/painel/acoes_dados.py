"""Ações sobre vagas da trilha de Engenharia de Dados: status, descarte, observação, histórico e janela de detalhes.

Grava SOMENTE pelas funções de vagas/trilhas/dados/db.py (tabelas dados_*). Nada da trilha Laravel é tocado.
"""

import pandas as pd
import streamlit as st

from vagas.painel import comum_dados as cd
from vagas.painel import logica, ui
from vagas.painel.navegacao import abrir_sugestoes_dados
from vagas.trilhas.dados import db as dados_db

ROTULO_STATUS = {s: r for s, (r, _, _) in ui.STATUS_UI.items()}
MENSAGENS = {
    None: ("Vaga voltou para nova", "↩️"), "interessa": ("Marcada com interesse", "⭐"),
    "candidatei": ("Candidatura registrada. Boa sorte!", "📨"), "entrevista": ("Andamento: entrevista", "🗣️"),
    "proposta": ("Andamento: proposta", "🎉"), "recusado": ("Andamento: recusado", "📝"),
    "descartada": ("Vaga descartada", "🗑️"),
}
ROTULO_PARCELA = {"area": "Área do cargo", "senioridade": "Senioridade", "fundamentos": "Fundamentos (Python e SQL)",
                  "ecossistema": "Ecossistema de dados", "conceitos": "Conceitos transferíveis", "formacao": "Formação",
                  "modalidade": "Modalidade"}


# --------------------------------------------------------------------------- selos
def badge_confianca(nivel) -> str:
    return ui.badge(f"Confiança {cd.CONFIANCA.get(nivel, '—').lower()}", cd.TOM_CONFIANCA.get(nivel, "neutro"), "circle-check",
                    "Quantidade e qualidade da informação da vaga. Independe da nota.")


def badge_elegibilidade(elegibilidade) -> str:
    if elegibilidade != "alerta":
        return ""
    return ui.badge("Elegibilidade: alerta", "atencao", "triangle-alert", "Confira a exigência de formação antes de se candidatar.")


def badge_categoria(categoria) -> str:
    tom = "neutro" if categoria == "relacionada" else "primario"
    return ui.badge(cd.CATEGORIAS.get(categoria, categoria or "—"), tom, "database")


def rotulo_nivel(nivel) -> str:
    return cd.NIVEIS.get(nivel, "Nível não informado")


# --------------------------------------------------------------------------- gravação
def mudar_status(vaga_id: str, status: str | None, motivo: str | None = None, detalhe: str | None = None) -> None:
    dados_db.definir_status(vaga_id, status, motivo, detalhe)
    cd.limpar_cache()
    texto, emoji = MENSAGENS.get(status, ("Status atualizado", "✔️"))
    st.toast(texto, icon=emoji)


def mudar_andamento(vaga_id: str, chave: str) -> None:
    mudar_status(vaga_id, st.session_state[chave])


def salvar_nota(vaga_id: str, chave: str) -> None:
    dados_db.definir_nota(vaga_id, st.session_state[chave] or "")
    cd.limpar_cache()
    st.toast("Observação salva", icon="💾")


# --------------------------------------------------------------------------- descarte
def campos_descarte(prefixo: str):
    motivo = st.radio("Motivo", cd.MOTIVOS_DESCARTE, index=None, key=f"{prefixo}-mot")
    detalhe = st.text_input("Detalhe (opcional)", key=f"{prefixo}-det",
                            placeholder="Ex.: pede 3 anos de experiência; vaga no México")
    return motivo, detalhe


@st.dialog("Por que descartar esta vaga?")
def dialogo_descartar(vaga_id: str, titulo: str, empresa: str | None) -> None:
    st.caption(f"**{titulo}** · {empresa or 'Empresa não identificada'}")
    motivo, detalhe = campos_descarte(f"dd-{vaga_id}")
    st.caption("Fica registrado em Relatórios → Descartadas, onde dá para restaurar a vaga.")
    ok, cancelar = st.columns(2)
    if ok.button("Descartar", icon=":material/delete:", type="primary", width="stretch", disabled=motivo is None):
        mudar_status(vaga_id, "descartada", motivo, detalhe)
        st.rerun()
    if cancelar.button("Cancelar", width="stretch"):
        st.rerun()


# --------------------------------------------------------------------------- status e histórico (formulário reutilizável)
def status_e_historico(vaga: dict, prefixo: str = "df") -> None:
    vid = vaga["id"]
    with st.form(f"{prefixo}-form-status-{vid}", border=False):
        novo = st.selectbox("Status", cd.STATUS, index=cd.STATUS.index(vaga["status"]), format_func=ROTULO_STATUS.get,
                            key=f"{prefixo}-status-{vid}")
        st.caption("Se escolher **Descartada**, informe o motivo:")
        motivo, detalhe = campos_descarte(f"{prefixo}-{vid}")
        salvar = st.form_submit_button("Salvar status", icon=":material/check:", type="primary")
    if salvar and novo != vaga["status"]:
        if novo == "descartada" and motivo is None:
            st.error("Escolha um motivo para descartar.")
        else:
            mudar_status(vid, None if novo == "nova" else novo, motivo, detalhe)
            st.rerun()

    if vaga["status"] != "nova":
        chave = f"{prefixo}-obs-{vid}"
        st.text_input("Observação", value=vaga.get("nota") or "", key=chave,
                      placeholder="Ex.: falei com a recrutadora em 25/11", on_change=salvar_nota, args=(vid, chave))
    if vaga["status"] == "descartada":
        st.caption(f"Motivo do descarte: **{vaga.get('motivo_descarte') or 'sem motivo registrado'}**"
                   + (f" — {vaga['detalhe_descarte']}" if vaga.get("detalhe_descarte") else ""))

    h = logica.historico_da_vaga(cd.historico(), vid)
    st.markdown("**Histórico**")
    if h.empty:
        st.caption("Nenhuma mudança de status registrada ainda.")
        return
    linhas = ""
    for r in h.itertuples():
        _, tom, ic = ui.STATUS_UI.get(r.status, ui.STATUS_UI["nova"])
        motivo_h = f" · {ui.esc(r.motivo)}" if isinstance(getattr(r, "motivo", None), str) else ""
        linhas += (f'<li><span class="rv-li-ic rv-tom-{tom}">{ui.icone(ic, 13, ui.cor_do_tom(tom))}</span>'
                   f'<span><b>{ui.esc(ROTULO_STATUS.get(r.status, r.status))}</b> · {cd.quando(r.em)}{motivo_h}</span></li>')
    st.html(f'<ul class="rv-lista">{linhas}</ul>')


# --------------------------------------------------------------------------- detalhes
def _aba_nota(vaga: dict) -> None:
    c1, c2, c3 = st.columns(3)
    c1.html(badge_confianca(vaga.get("confianca_nivel")))
    c2.html(ui.badge(cd.ELEGIBILIDADE.get(vaga.get("elegibilidade"), "—"), cd.TOM_ELEGIBILIDADE.get(vaga.get("elegibilidade"), "neutro"),
                     "graduation-cap"))
    c3.html(ui.badge(f"{vaga.get('confianca_pontos', 0) if pd.notna(vaga.get('confianca_pontos')) else 0}/7 sinais de confiança",
                     "neutro", "list-checks"))
    parcelas = vaga.get("parcelas") or []
    if parcelas:
        tabela = pd.DataFrame([{"Critério": ROTULO_PARCELA.get(p["nome"], p["nome"]), "Pontos": round(p["pontos"], 2),
                                "Máximo": p["maximo"], "Detalhe": p.get("detalhe") or ""} for p in parcelas])
        st.dataframe(tabela, hide_index=True, width="stretch")
    else:
        st.caption("Esta vaga ainda não foi avaliada.")
    positivos, atencao = logica.separar_motivos(vaga.get("motivos"))
    # "Em estudo" não é experiência: sai dos pontos positivos e vai para as lacunas, dizendo isso.
    estudo = [m for m in positivos if m.startswith("Em estudo")]
    positivos = [m for m in positivos if m not in estudo]
    atencao = atencao + [f"{m} (sem experiência prática)" for m in estudo]
    p, a = st.columns(2)
    with p:
        st.markdown("**Pontos positivos**")
        st.html(ui.lista_itens(positivos, "check", "sucesso") if positivos else
                '<p class="rv-secao-desc">Nenhum ponto positivo identificado.</p>')
    with a:
        st.markdown("**Lacunas e pontos de atenção**")
        st.html(ui.lista_itens(atencao, "triangle-alert", "atencao") if atencao else
                '<p class="rv-secao-desc">Nenhuma lacuna identificada.</p>')
    if vaga.get("alertas"):
        st.markdown("**Alertas** (não alteram a nota)")
        st.html(ui.lista_itens(vaga["alertas"], "triangle-alert", "atencao"))
    if vaga.get("confianca_motivos"):
        st.markdown("**O que reduz a confiança**")
        st.html(ui.lista_itens(vaga["confianca_motivos"], "circle-alert", "neutro"))
    if vaga.get("formacao_exigida"):
        st.caption(f"Formação: {vaga['formacao_exigida']}")


def _aba_requisitos(vaga: dict) -> None:
    st.caption("Tecnologia **mencionada** não é requisito. Só vale como requisito o que está sob cabeçalhos de "
               "requisitos, desejáveis ou stack.")
    for titulo, chave, tom in (("Requisitos obrigatórios", "req_obrigatorios", "sucesso"),
                               ("Requisitos desejáveis", "req_desejaveis", "info"),
                               ("Citadas apenas nas atividades (não são requisitos)", "citados_em_atividades", "neutro"),
                               ("Tecnologias mencionadas na vaga", "tecnologias", "neutro")):
        itens = vaga.get(chave) or []
        st.markdown(f"**{titulo}**")
        if itens:
            st.html('<div class="rv-badges">' + "".join(ui.badge(i, tom) for i in itens) + "</div>")
        else:
            st.caption("Nenhuma.")
    if vaga.get("conceitos"):
        st.markdown("**Conceitos citados**")
        st.html(ui.chips(vaga["conceitos"], maximo=30))


@st.dialog("Detalhes da vaga", width="large")
def dialogo_detalhes(vaga: dict) -> None:
    rotulo, tom = logica.classificar_nota(vaga.get("compatibilidade"))
    modal, ic_modal = ui.MODALIDADE_UI.get(vaga.get("modelo_trabalho"), ui.MODALIDADE_UI[None])
    c1, c2 = st.columns([1, 6], vertical_alignment="center")
    c1.html(ui.nota_bloco(vaga.get("compatibilidade"), rotulo, tom))
    c2.html(
        f'<div class="rv-vaga-tit">{ui.esc(vaga["titulo"])}</div>'
        f'<div class="rv-vaga-emp">{ui.icone("building-2", 15, "#4b5563")}{ui.esc(vaga.get("empresa") or "Empresa não identificada")}'
        f'{" · " + ui.esc(vaga["localizacao"]) if vaga.get("localizacao") else ""}</div>'
        f'<div class="rv-badges">{ui.badge_status(vaga["status"])}{ui.badge(modal, "neutro", ic_modal)}'
        f'{ui.badge(rotulo_nivel(vaga.get("nivel")), "neutro", "award")}{badge_categoria(vaga.get("categoria_cargo"))}</div>')
    a1, a2 = st.columns(2)
    a1.link_button("Abrir vaga original", vaga["url"], icon=":material/open_in_new:", width="stretch")
    if a2.button("Sugestões de currículo", icon=":material/auto_awesome:", width="stretch", key="dd-det-sug"):
        abrir_sugestoes_dados(vaga["id"])
    abas = st.tabs(["Nota e alertas", "Requisitos", "Descrição", "Status e histórico", "Fontes"])
    with abas[0]:
        _aba_nota(vaga)
    with abas[1]:
        _aba_requisitos(vaga)
    with abas[2]:
        if vaga.get("so_titulo"):
            st.info("Veio de um alerta por e-mail, que traz só título, empresa e local. A descrição completa está no link "
                    "da vaga original.", icon=":material/mail:")
        elif vaga.get("fonte") == "adzuna":
            st.caption("A Adzuna envia só um trecho da descrição; o texto completo está no link da vaga.")
        if vaga.get("descricao"):
            st.markdown(vaga["descricao"])
        else:
            st.caption("Sem descrição.")
    with abas[3]:
        status_e_historico(vaga)
    with abas[4]:
        fontes = vaga.get("fontes") or [vaga.get("fonte")]
        st.html('<div class="rv-badges">' + "".join(
            ui.badge(ui.FONTE_UI.get(f, (f, "globe"))[0], "primario", ui.FONTE_UI.get(f, (f, "globe"))[1]) for f in fontes) + "</div>")
        st.html(ui.meta("calendar", f"Publicada {cd.quando(vaga.get('publicada_em'))}") + "&nbsp;&nbsp;" +
                ui.meta("radar", f"No radar desde {cd.quando(vaga.get('primeira_coleta'))}"))


def acoes_rapidas(v: dict, prefixo: str) -> None:
    """Botões de ação de um card: interesse, candidatei, descartar/voltar, detalhes e sugestões."""
    vid, status = v["id"], v["status"]
    with st.container(horizontal=True, gap="small"):
        st.button("", icon=":material/star:", key=f"{prefixo}-i-{vid}", help="Marcar interesse", width="stretch",
                  on_click=mudar_status, args=(vid, "interessa"), disabled=status == "interessa")
        st.button("", icon=":material/send:", key=f"{prefixo}-c-{vid}", help="Registrar candidatura", width="stretch",
                  on_click=mudar_status, args=(vid, "candidatei"), disabled=status in cd.CANDIDATURA)
        if status in ("nova", "interessa"):
            if st.button("", icon=":material/delete:", key=f"{prefixo}-d-{vid}", help="Descartar (pede o motivo)", width="stretch"):
                dialogo_descartar(vid, v["titulo"], v.get("empresa"))
        else:
            st.button("", icon=":material/undo:", key=f"{prefixo}-n-{vid}", help="Voltar para nova", width="stretch",
                      on_click=mudar_status, args=(vid, None))
    if st.button("Ver detalhes", icon=":material/visibility:", key=f"{prefixo}-v-{vid}", width="stretch"):
        dialogo_detalhes(v)
    if st.button("Sugestões", icon=":material/auto_awesome:", key=f"{prefixo}-s-{vid}", width="stretch", type="tertiary"):
        abrir_sugestoes_dados(vid)
