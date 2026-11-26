"""Registro das páginas, para uma página conseguir levar o usuário a outra (st.switch_page)."""

import streamlit as st

PAGINAS: dict[str, st.Page] = {}

# --- Trilhas (seletor no topo da barra lateral). PHP/Laravel é a padrão e mantém as URLs de sempre;
# as páginas de Engenharia de Dados usam o prefixo "dados-" na URL e "dados_" na chave de PAGINAS.
TRILHAS = {"laravel": "PHP / Laravel", "dados": "Engenharia de Dados"}
TRILHA_PADRAO = "laravel"
PREFIXO_URL_DADOS = "dados-"
PREFIXO_CHAVE_DADOS = "dados_"


def trilha_da_url(url_path: str | None) -> str:
    """A página pertence à trilha de dados se a URL começa com 'dados-'; senão é a Laravel (a padrão)."""
    return "dados" if (url_path or "").startswith(PREFIXO_URL_DADOS) else TRILHA_PADRAO


def chave_visao_geral(trilha: str) -> str:
    return f"{PREFIXO_CHAVE_DADOS}visao_geral" if trilha == "dados" else "visao_geral"


def ir_para(nome: str) -> None:
    """Troca de página. Chamar no corpo da página (não dentro de callback de widget)."""
    if nome in PAGINAS:
        st.switch_page(PAGINAS[nome])


def abrir_sugestoes(vaga_id: str) -> None:
    st.session_state["vaga_sugestao"] = vaga_id
    ir_para("sugestoes")


def abrir_sugestoes_dados(vaga_id: str) -> None:
    st.session_state["vaga_sugestao_dados"] = vaga_id
    ir_para("dados_sugestoes")
