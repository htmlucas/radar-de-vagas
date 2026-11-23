"""Sugestões de currículo: orientação por vaga, sempre fundamentada no currículo base e na vaga.
(As regras ficam em vagas/curriculo/sugestoes.py; aqui é só a apresentação.)"""

import pandas as pd
import streamlit as st

from vagas.curriculo import sugestoes
from vagas.painel import logica, ui
from vagas.painel.comum import CANDIDATURA, carregar_base, carregar_vagas

PRIORIDADE = {"interessa": 0, **{s: 1 for s in CANDIDATURA}, "nova": 2}


def _opcoes(df: pd.DataFrame) -> pd.DataFrame:
    """Vagas que fazem sentido adaptar: do seu perfil ou que você marcou (sem descartadas)."""
    f = df[(df["alvo"] | (df["status"] != "nova")) & (df["status"] != "descartada")].copy()
    f["prio"] = f["status"].map(PRIORIDADE).fillna(3)
    return f.sort_values(["prio", "compatibilidade"], ascending=[True, False])


def _copiavel(texto: str) -> None:
    """Bloco com botão de copiar (canto superior direito)."""
    st.code(texto, language=None, wrap_lines=True)


def _coluna_vaga(v: dict, analise: dict) -> None:
    rotulo, tom = logica.classificar_nota(v.get("compatibilidade"))
    modal, ic = ui.MODALIDADE_UI.get(v.get("modelo_trabalho"), ui.MODALIDADE_UI[None])
    with st.container(border=True):
        c1, c2 = st.columns([1, 3.2], vertical_alignment="center")
        c1.html(ui.nota_bloco(v.get("compatibilidade"), rotulo, tom))
        c2.html(f'<div class="rv-vaga-tit">{ui.esc(v["titulo"])}</div>'
                f'<div class="rv-vaga-emp">{ui.icone("building-2", 15, "#4b5563")}{ui.esc(v.get("empresa") or "Empresa não identificada")}</div>'
                f'<div class="rv-badges">{ui.badge_status(v["status"])}{ui.badge(modal, "neutro", ic)}</div>')
        st.link_button("Abrir vaga original", v["url"], icon=":material/open_in_new:", width="stretch")

        total = len(analise["comprovadas"]) + len(analise["lacunas"])
        ui.secao("Requisitos identificados", "list-checks")
        if total:
            st.progress(len(analise["comprovadas"]) / total,
                        text=f"Você comprova {len(analise['comprovadas'])} de {total} tecnologias pedidas")
        if analise["comprovadas"]:
            st.html('<div class="rv-secao-desc">No seu currículo</div><div class="rv-badges">'
                    + "".join(ui.badge(t, "sucesso", "check") for t in analise["comprovadas"]) + "</div>")
        if analise["lacunas"]:
            st.html('<div class="rv-secao-desc" style="margin-top:8px">Não aparece no seu currículo</div><div class="rv-badges">'
                    + "".join(ui.badge(t, "atencao", "circle-alert") for t in analise["lacunas"]) + "</div>")
        if analise["temas_comuns"]:
            st.html('<div class="rv-secao-desc" style="margin-top:8px">Temas em comum</div><div class="rv-badges">'
                    + "".join(ui.badge(t, "primario") for t in analise["temas_comuns"]) + "</div>")
        if not total and not analise["temas_comuns"]:
            st.caption("Poucas informações na vaga. Cole a descrição completa abaixo.")

    with st.container(border=True):
        ui.secao("Descrição completa", "file-text",
                 "Opcional, mas deixa tudo mais preciso (vagas da Adzuna e de e-mail vêm resumidas).")
        st.text_area("Descrição completa da vaga", key=f"desc-{v['id']}", height=140, label_visibility="collapsed",
                     placeholder="Abra a vaga original, copie a descrição e cole aqui. Depois tecle Ctrl+Enter.")
        if not analise["usou_descricao_completa"]:
            st.caption("Sem a descrição completa, as sugestões usam só o que o radar coletou.")


def _coluna_sugestoes(v: dict, analise: dict, base: dict, descricao: str) -> None:
    abas = st.tabs(["Resumo", "Experiência", "Projetos", "Tecnologias", "Requisitos ausentes", "Texto para IA"])
    with abas[0]:
        ui.secao("Título profissional", "award")
        _copiavel(analise["titulo"])
        ui.secao("Resumo profissional sugerido", "file-text", "Montado só com o que seu currículo comprova.")
        _copiavel(analise["resumo"])
    with abas[1]:
        experiencias = [e for e in sorted(analise["experiencias"], key=lambda e: -e["relevancia"]) if e["destaque"]]
        if not experiencias:
            ui.vazio("Nada se destacou", "Nenhuma atividade do currículo bate com esta vaga. Mantenha a ordem atual.",
                     "briefcase-business")
        else:
            st.caption("Coloque estas atividades no topo de cada experiência (a mais relevante primeiro).")
        for e in experiencias:
            ui.secao(f"{e['cargo']} — {e['empresa']}", "briefcase-business")
            for atividade, motivos in e["destaque"]:
                _copiavel(atividade)
                st.caption("Por quê: " + ", ".join(motivos))
    with abas[2]:
        projetos_base = {p["nome"]: p for p in base.get("projetos", [])}
        if not analise["projetos"]:
            ui.vazio("Nenhum projeto relevante", "Nenhum projeto do currículo cita o que esta vaga pede.", "code-xml")
        for p in analise["projetos"]:
            ui.secao(p["nome"], "code-xml", "Relevante por: " + ", ".join(p["motivos"]))
            descricao_base = (projetos_base.get(p["nome"]) or {}).get("descricao")
            if descricao_base:
                _copiavel(" ".join(descricao_base.split()))
    with abas[3]:
        ui.secao("Use os mesmos termos da vaga", "zap",
                 "Tecnologias que a vaga pede e o seu currículo comprova. Escreva do mesmo jeito que a vaga.")
        if analise["comprovadas"]:
            _copiavel(", ".join(analise["comprovadas"]))
        else:
            st.caption("Nenhuma tecnologia identificada em comum.")
        if analise["temas_comuns"]:
            ui.secao("Temas para mencionar", "lightbulb")
            _copiavel(", ".join(analise["temas_comuns"]))
    with abas[4]:
        if analise["lacunas"]:
            st.html(ui.lista_itens(analise["lacunas"], "circle-alert", "atencao"))
            st.info("Se você tem alguma experiência com esses itens, inclua no currículo base: a nota e as sugestões "
                    "passam a considerar. Se não tem, não invente: prepare-se para falar sobre o tema na entrevista.",
                    icon=":material/lightbulb:")
        else:
            ui.vazio("Nenhuma lacuna identificada", "Tudo o que a vaga pede aparece no seu currículo.", "circle-check")
    with abas[5]:
        st.caption("Opcional: cole num assistente de IA que você já usa para uma reescrita completa. "
                   "Seus dados de contato não vão no texto.")
        _copiavel(sugestoes.prompt_para_chat(v, base, descricao))
        st.download_button("Baixar todas as sugestões (.txt)", sugestoes.formatar(analise),
                           file_name=f"sugestoes - {v.get('empresa') or 'vaga'}.txt", mime="text/plain",
                           icon=":material/download:", key=f"sug-txt-{v['id']}")


def pagina() -> None:
    ui.cabecalho("Sugestões de currículo",
                 "Orientação para adaptar seu currículo a cada vaga, sem inventar nada.", "wand-sparkles")
    base = carregar_base()
    if base is None:
        ui.vazio("Currículo base não encontrado",
                 "Crie <code>curriculo/base/curriculo.yaml</code> a partir de <code>curriculo/exemplo.yaml</code>.",
                 "file-text")
        return
    df = carregar_vagas()
    opcoes = _opcoes(df) if not df.empty else pd.DataFrame()
    if opcoes.empty:
        ui.vazio("Nenhuma vaga para adaptar", "Quando houver vagas no seu perfil, escolha uma aqui.", "inbox")
        return

    ids = list(opcoes["id"])
    escolhida = st.session_state.get("vaga_sugestao")
    rotulos = {r.id: f"{int(r.compatibilidade) if pd.notna(r.compatibilidade) else '—'} · {r.titulo} — "
                     f"{r.empresa or 'Empresa não identificada'}" for r in opcoes.itertuples()}
    vid = st.selectbox("Vaga", ids, index=ids.index(escolhida) if escolhida in ids else 0,
                       format_func=rotulos.get, help="Vagas com interesse e candidaturas aparecem primeiro.")
    st.session_state["vaga_sugestao"] = vid
    v = opcoes[opcoes["id"] == vid].iloc[0].to_dict()

    descricao = st.session_state.get(f"desc-{vid}", "")
    analise = sugestoes.analisar(v, base, descricao)
    esquerda, direita = st.columns([1, 1.55], gap="medium")
    with esquerda:
        _coluna_vaga(v, analise)
    with direita, st.container(border=True):
        _coluna_sugestoes(v, analise, base, descricao)
