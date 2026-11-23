"""Ações sobre vagas (status, andamento, observação, descarte) e as janelas de detalhes/descarte.
Toda ação grava no banco pelas funções existentes de vagas/db.py e dá um retorno visual (toast)."""

import pandas as pd
import streamlit as st

from vagas import db
from vagas.painel import logica, ui
from vagas.painel.comum import CANDIDATURA, MOTIVOS_DESCARTE, historico, limpar_cache, quando
from vagas.painel.navegacao import abrir_sugestoes
from vagas.pontuacao import nota as regra_nota

ROTULO_STATUS = {s: r for s, (r, _, _) in ui.STATUS_UI.items()}
MENSAGENS = {
    None: ("Vaga voltou para nova", "↩️"),
    "interessa": ("Marcada com interesse", "⭐"),
    "candidatei": ("Candidatura registrada. Boa sorte!", "📨"),
    "entrevista": ("Andamento: entrevista", "🗣️"),
    "proposta": ("Andamento: proposta", "🎉"),
    "recusado": ("Andamento: recusado", "📝"),
    "descartada": ("Vaga descartada", "🗑️"),
}


def mudar_status(vaga_id: str, status: str | None, motivo: str | None = None, detalhe: str | None = None) -> None:
    db.definir_status(vaga_id, status, motivo, detalhe)
    limpar_cache()
    texto, emoji = MENSAGENS.get(status, ("Status atualizado", "✔️"))
    st.toast(texto, icon=emoji)


def mudar_andamento(vaga_id: str, chave: str) -> None:
    mudar_status(vaga_id, st.session_state[chave])


def salvar_nota(vaga_id: str, chave: str) -> None:
    db.definir_nota(vaga_id, st.session_state[chave] or "")
    limpar_cache()
    st.toast("Observação salva", icon="💾")


# --------------------------------------------------------------------------- descarte
@st.dialog("Por que descartar esta vaga?")
def dialogo_descartar(vaga_id: str, titulo: str, empresa: str | None) -> None:
    st.caption(f"**{titulo}** · {empresa or 'Empresa não identificada'}")
    motivo, detalhe = _campos_descarte(f"dd-{vaga_id}")
    st.caption("Fica registrado em Relatórios → Descartadas, onde dá para restaurar a vaga.")
    ok, cancelar = st.columns(2)
    if ok.button("Descartar", icon=":material/delete:", type="primary", width="stretch", disabled=motivo is None):
        mudar_status(vaga_id, "descartada", motivo, detalhe)
        st.rerun()
    if cancelar.button("Cancelar", width="stretch"):
        st.rerun()


def _campos_descarte(prefixo: str):
    motivo = st.radio("Motivo", MOTIVOS_DESCARTE, index=None, key=f"{prefixo}-mot")
    detalhe = st.text_input("Detalhe (opcional)", key=f"{prefixo}-det",
                            placeholder="Ex.: pede 6 anos de experiência; presencial em Curitiba")
    return motivo, detalhe


# --------------------------------------------------------------------------- detalhes
@st.dialog("Detalhes da vaga", width="large")
def dialogo_detalhes(vaga: dict) -> None:
    rotulo, tom = logica.classificar_nota(vaga.get("compatibilidade"))
    modal, ic_modal = ui.MODALIDADE_UI.get(vaga.get("modelo_trabalho"), ui.MODALIDADE_UI[None])
    c1, c2 = st.columns([1, 6], vertical_alignment="center")
    with c1:
        st.html(ui.nota_bloco(vaga.get("compatibilidade"), rotulo, tom))
    with c2:
        st.html(
            f'<div class="rv-vaga-tit">{ui.esc(vaga["titulo"])}</div>'
            f'<div class="rv-vaga-emp">{ui.icone("building-2", 15, "#4b5563")}{ui.esc(vaga.get("empresa") or "Empresa não identificada")}'
            f'{" · " + ui.esc(vaga["localizacao"]) if vaga.get("localizacao") else ""}</div>'
            f'<div class="rv-badges">{ui.badge_status(vaga["status"])}{ui.badge(modal, "neutro", ic_modal)}'
            f'{ui.badge(ui.NIVEL_UI.get(vaga.get("nivel"), "Nível não informado"), "neutro", "award")}</div>'
        )

    a1, a2 = st.columns(2)
    a1.link_button("Abrir vaga original", vaga["url"], icon=":material/open_in_new:", width="stretch")
    if a2.button("Sugestões de currículo", icon=":material/auto_awesome:", width="stretch", key="det-sug"):
        abrir_sugestoes(vaga["id"])

    abas = st.tabs(["Por que essa nota", "Descrição", "Status e histórico", "Fontes"])
    with abas[0]:
        _explicar_nota(vaga)
    with abas[1]:
        if vaga.get("so_titulo"):
            st.info("Esta vaga veio de um alerta por e-mail, que traz só título, empresa e local. "
                    "A descrição completa está no link da vaga original.", icon=":material/mail:")
        elif vaga.get("fonte") == "adzuna":
            st.caption("A Adzuna envia só um trecho da descrição; o texto completo está no link da vaga.")
        if vaga.get("descricao"):
            st.markdown(vaga["descricao"])
        else:
            st.caption("Sem descrição.")
    with abas[2]:
        _status_e_historico(vaga)
    with abas[3]:
        fontes = vaga.get("fontes") or [vaga.get("fonte")]
        st.html('<div class="rv-badges">' + "".join(
            ui.badge(ui.FONTE_UI.get(f, (f, "globe"))[0], "primario", ui.FONTE_UI.get(f, (f, "globe"))[1])
            for f in fontes) + "</div>")
        st.caption("Quando a mesma vaga aparece em mais de uma fonte, o radar mostra uma só e guarda todas as origens.")
        st.html(ui.meta("calendar", f"Publicada {quando(vaga.get('publicada_em'))}") + "&nbsp;&nbsp;" +
                ui.meta("radar", f"No radar desde {quando(vaga.get('primeira_coleta'))}"))


def _explicar_nota(vaga: dict) -> None:
    positivos, atencao = logica.separar_motivos(vaga.get("motivos"))
    p, a = st.columns(2)
    with p:
        st.markdown("**Pontos positivos**")
        st.html(ui.lista_itens(positivos, "check", "sucesso") if positivos else
                '<p class="rv-secao-desc">Nenhum ponto positivo identificado.</p>')
    with a:
        st.markdown("**Pontos de atenção**")
        st.html(ui.lista_itens(atencao, "triangle-alert", "atencao") if atencao else
                '<p class="rv-secao-desc">Nenhum ponto de atenção.</p>')
    if vaga.get("tecnologias"):
        st.markdown("**Tecnologias identificadas**")
        st.html(ui.chips(vaga["tecnologias"], maximo=30))
    with st.expander("Como a nota é calculada"):
        st.markdown(
            f"A nota vai de 0 a 100 e soma quatro critérios:\n\n"
            f"- **Stack ({regra_nota.PESO_STACK} pts):** tecnologias da vaga que você domina valem inteiro, as que "
            f"conhece valem metade. Com menos de {regra_nota.MIN_TECHS_CONFIAVEL} tecnologias identificadas, "
            f"esse critério fica limitado a 75%.\n"
            f"- **Nível ({regra_nota.PESO_NIVEL} pts):** pleno é o ideal para sua experiência.\n"
            f"- **Modalidade e local ({regra_nota.PESO_MODELO} pts):** remoto, ou híbrido/presencial em cidade viável.\n"
            f"- **Tipo de cargo ({regra_nota.PESO_CARGO} pts):** desenvolvimento pontua mais; cargos de outra área "
            f"(DevOps, suporte) têm a nota multiplicada por {regra_nota.FATOR_CARGO_OUTRO}.\n\n"
            "Faixas na tela: **Alta** a partir de 75, **Média** de 60 a 74, **Baixa** abaixo de 60."
        )


def _status_e_historico(vaga: dict) -> None:
    vid = vaga["id"]
    with st.form(f"form-status-{vid}", border=False):
        opcoes = list(ROTULO_STATUS)
        novo = st.selectbox("Status", opcoes, index=opcoes.index(vaga["status"]), format_func=ROTULO_STATUS.get)
        st.caption("Se escolher **Descartada**, informe o motivo:")
        motivo, detalhe = _campos_descarte(f"df-{vid}")
        salvar = st.form_submit_button("Salvar status", icon=":material/check:", type="primary")
    if salvar and novo != vaga["status"]:
        if novo == "descartada" and motivo is None:
            st.error("Escolha um motivo para descartar.")
        else:
            mudar_status(vid, None if novo == "nova" else novo, motivo, detalhe)
            st.rerun()

    if vaga["status"] != "nova":
        chave = f"det-obs-{vid}"
        st.text_input("Observação", value=vaga.get("nota") or "", key=chave,
                      placeholder="Ex.: falei com a recrutadora em 25/11", on_change=salvar_nota, args=(vid, chave))
    if vaga["status"] == "descartada":
        st.caption(f"Motivo do descarte: **{vaga.get('motivo_descarte') or 'sem motivo registrado'}**"
                   + (f" — {vaga['detalhe_descarte']}" if vaga.get("detalhe_descarte") else ""))

    h = logica.historico_da_vaga(historico(), vid)
    st.markdown("**Histórico**")
    if h.empty:
        st.caption("Nenhuma mudança de status registrada ainda.")
    else:
        linhas = "".join(
            f'<li><span class="rv-li-ic rv-tom-{ui.STATUS_UI.get(r.status, ui.STATUS_UI["nova"])[1]}">'
            f'{ui.icone(ui.STATUS_UI.get(r.status, ui.STATUS_UI["nova"])[2], 13, ui.cor_do_tom(ui.STATUS_UI.get(r.status, ui.STATUS_UI["nova"])[1]))}</span>'
            f'<span><b>{ui.esc(ROTULO_STATUS.get(r.status, r.status))}</b> · {quando(r.em)}'
            f'{" · " + ui.esc(r.motivo) if isinstance(getattr(r, "motivo", None), str) else ""}</span></li>'
            for r in h.itertuples())
        st.html(f'<ul class="rv-lista">{linhas}</ul>')


def acoes_rapidas(v: dict, prefixo: str) -> None:
    """Botões de ação de um card: interesse, candidatei, descartar, detalhes e sugestões."""
    vid, status = v["id"], v["status"]
    # Fileira horizontal: continua lado a lado no celular (colunas empilhariam)
    with st.container(horizontal=True, gap="small"):
        st.button("", icon=":material/star:", key=f"{prefixo}-i-{vid}", help="Marcar interesse", width="stretch",
                  on_click=mudar_status, args=(vid, "interessa"), disabled=status == "interessa")
        st.button("", icon=":material/send:", key=f"{prefixo}-c-{vid}", help="Registrar candidatura",
                  width="stretch", on_click=mudar_status, args=(vid, "candidatei"), disabled=status in CANDIDATURA)
        if status in ("nova", "interessa"):
            if st.button("", icon=":material/delete:", key=f"{prefixo}-d-{vid}", help="Descartar (pede o motivo)",
                         width="stretch"):
                dialogo_descartar(vid, v["titulo"], v.get("empresa"))
        else:
            st.button("", icon=":material/undo:", key=f"{prefixo}-n-{vid}", help="Voltar para nova", width="stretch",
                      on_click=mudar_status, args=(vid, None))
    if st.button("Ver detalhes", icon=":material/visibility:", key=f"{prefixo}-v-{vid}", width="stretch"):
        dialogo_detalhes(v)
    if st.button("Sugestões", icon=":material/auto_awesome:", key=f"{prefixo}-s-{vid}", width="stretch",
                 type="tertiary"):
        abrir_sugestoes(vid)


def dias_desde(ts) -> int | None:
    if ts is None or pd.isna(ts):
        return None
    return int((pd.Timestamp.now(tz=logica.FUSO) - ts).days)
