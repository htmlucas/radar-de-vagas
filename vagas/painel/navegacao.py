"""Registro das páginas, para uma página conseguir levar o usuário a outra (st.switch_page)."""

import streamlit as st

PAGINAS: dict[str, st.Page] = {}


def ir_para(nome: str) -> None:
    """Troca de página. Chamar no corpo da página (não dentro de callback de widget)."""
    if nome in PAGINAS:
        st.switch_page(PAGINAS[nome])


def abrir_sugestoes(vaga_id: str) -> None:
    st.session_state["vaga_sugestao"] = vaga_id
    ir_para("sugestoes")
