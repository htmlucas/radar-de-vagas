"""Radar de Vagas — painel. Rodar com:  streamlit run vagas/painel/app.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from vagas.painel import ui  # noqa: E402
from vagas.painel.comum import ha_quanto, perfil_publico, situacao_execucao, ultimas_execucoes  # noqa: E402
from vagas.painel.navegacao import PAGINAS  # noqa: E402
from vagas.painel.paginas import (  # noqa: E402
    candidaturas, configuracoes, relatorios, sugestoes, vagas, visao_geral,
)

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Radar de Vagas", page_icon=str(ASSETS / "icone.svg"), layout="wide",
                   initial_sidebar_state="auto")  # aberta em tela larga, recolhida no celular
ui.aplicar_estilo()
st.logo(str(ASSETS / "logo.svg"), size="large", icon_image=str(ASSETS / "icone.svg"))

PAGINAS.update({
    "visao_geral": st.Page(visao_geral.pagina, title="Visão geral", icon=":material/space_dashboard:",
                           url_path="visao-geral", default=True),
    "vagas": st.Page(vagas.pagina, title="Vagas", icon=":material/work:", url_path="vagas"),
    "candidaturas": st.Page(candidaturas.pagina, title="Candidaturas", icon=":material/send:",
                            url_path="candidaturas"),
    "sugestoes": st.Page(sugestoes.pagina, title="Sugestões de currículo", icon=":material/auto_awesome:",
                         url_path="sugestoes"),
    "relatorios": st.Page(relatorios.pagina, title="Relatórios", icon=":material/bar_chart:",
                          url_path="relatorios"),
    "configuracoes": st.Page(configuracoes.pagina, title="Configurações", icon=":material/settings:",
                             url_path="configuracoes"),
})

navegacao = st.navigation({
    "Busca": [PAGINAS["visao_geral"], PAGINAS["vagas"], PAGINAS["candidaturas"], PAGINAS["sugestoes"]],
    "Análise": [PAGINAS["relatorios"]],
    "Sistema": [PAGINAS["configuracoes"]],
})


def rodape_sidebar() -> None:
    perfil = perfil_publico()
    iniciais = "".join(p[0] for p in perfil["nome"].split()[:2]).upper() or "R"
    execs = ultimas_execucoes()
    if execs.empty:
        ponto, texto = "#9ca3af", "Nenhuma coleta ainda"
    else:
        situacoes = [situacao_execucao(e) for e in execs.to_dict("records")]
        problema = any(tom == "erro" for _, tom in situacoes)
        ultima = pd.to_datetime(execs["iniciada_em"], utc=True).max()
        ponto = "#dc2626" if problema else "#16a34a"
        texto = f"Última coleta {ha_quanto(ultima)}" + (" · com erro" if problema else "")
    with st.sidebar:
        st.html(
            f'<div class="rv-usuario"><div class="rv-avatar">{ui.esc(iniciais)}</div><div>'
            f'<div class="rv-usuario-nome">{ui.esc(perfil["nome"])}</div>'
            f'<div class="rv-usuario-sub">{ui.esc(perfil["titulo"])}</div></div></div>'
            f'<div class="rv-coleta"><span class="rv-ponto" style="background:{ponto}"></span>{ui.esc(texto)}</div>'
        )


rodape_sidebar()
navegacao.run()
