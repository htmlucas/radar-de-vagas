"""Radar de Vagas — painel. Rodar com:  streamlit run vagas/painel/app.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from vagas.painel import ui  # noqa: E402
from vagas.painel import comum_dados  # noqa: E402
from vagas.painel.comum import (  # noqa: E402
    banco_disponivel, ha_quanto, perfil_publico, situacao_execucao, ultimas_execucoes,
)
from vagas.painel.navegacao import (  # noqa: E402
    PAGINAS, TRILHA_PADRAO, TRILHAS, chave_visao_geral, ir_para, trilha_da_url,
)
from vagas.painel.paginas import (  # noqa: E402
    candidaturas, configuracoes, relatorios, sugestoes, vagas, visao_geral,
)
from vagas.painel.paginas.dados import (  # noqa: E402
    candidaturas as d_candidaturas, configuracoes as d_configuracoes, relatorios as d_relatorios,
    sugestoes as d_sugestoes, vagas as d_vagas, visao_geral as d_visao_geral,
)

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Radar de Vagas", page_icon=str(ASSETS / "icone.svg"), layout="wide",
                   initial_sidebar_state="auto")  # aberta em tela larga, recolhida no celular
ui.aplicar_estilo()
st.logo(str(ASSETS / "logo.svg"), size="large", icon_image=str(ASSETS / "icone.svg"))


@st.fragment(run_every=5)
def _aguardar_banco() -> None:
    """Confere o banco a cada 5 s e recarrega o painel sozinho assim que ele voltar."""
    if banco_disponivel()[0]:
        st.rerun()
    st.caption("Verificando o banco a cada 5 segundos...")


def pagina_sem_banco(erro: str) -> None:
    ui.cabecalho("Banco de dados indisponível",
                 "O painel está no ar, mas não consegue falar com o banco.", "database")
    with st.container(border=True):
        st.markdown(
            "Isso costuma acontecer quando o **Docker Desktop** está fechado ou ainda iniciando.\n\n"
            "1. Abra o Docker Desktop e espere o container **vagas-laravel-db** ficar em *Running*.\n"
            "2. Pronto: este painel confere sozinho e volta ao normal quando o banco responder. "
            "Não precisa recarregar a página."
        )
        _aguardar_banco()
        st.button("Tentar agora", icon=":material/refresh:", type="primary")
        with st.expander("Detalhes técnicos"):
            st.code(erro, language=None, wrap_lines=True)


_banco_ok, _banco_erro = banco_disponivel()
if not _banco_ok:
    pagina_sem_banco(_banco_erro or "sem detalhes")
    st.stop()

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
    # Trilha de Engenharia de Dados: URLs com o prefixo "dados-" (as da Laravel não mudam)
    "dados_visao_geral": st.Page(d_visao_geral.pagina, title="Visão geral", icon=":material/space_dashboard:",
                                 url_path="dados-visao-geral"),
    "dados_vagas": st.Page(d_vagas.pagina, title="Vagas", icon=":material/work:", url_path="dados-vagas"),
    "dados_candidaturas": st.Page(d_candidaturas.pagina, title="Candidaturas", icon=":material/send:",
                                  url_path="dados-candidaturas"),
    "dados_sugestoes": st.Page(d_sugestoes.pagina, title="Sugestões de currículo", icon=":material/auto_awesome:",
                               url_path="dados-sugestoes"),
    "dados_relatorios": st.Page(d_relatorios.pagina, title="Relatórios", icon=":material/bar_chart:",
                                url_path="dados-relatorios"),
    "dados_configuracoes": st.Page(d_configuracoes.pagina, title="Configurações", icon=":material/settings:",
                                   url_path="dados-configuracoes"),
})

# Cada trilha mostra só as suas páginas. A navegação do Streamlit fica oculta (só registra as rotas);
# o menu é desenhado abaixo, com o seletor de trilha no topo da barra lateral.
MENUS = {
    "laravel": {"Busca": ["visao_geral", "vagas", "candidaturas", "sugestoes"], "Análise": ["relatorios"],
                "Sistema": ["configuracoes"]},
    "dados": {"Busca": ["dados_visao_geral", "dados_vagas", "dados_candidaturas", "dados_sugestoes"],
              "Análise": ["dados_relatorios"], "Sistema": ["dados_configuracoes"]},
}

navegacao = st.navigation(list(PAGINAS.values()), position="hidden")
trilha_atual = trilha_da_url(navegacao.url_path)


def _pediu_troca_de_trilha() -> None:
    st.session_state["_trilha_pedida"] = st.session_state["trilha"]


def seletor_e_menu(trilha: str) -> None:
    """Seletor de trilha (topo da barra lateral) e o menu só da trilha ativa."""
    # A página manda: abrir /dados-vagas direto já mostra a trilha de dados.
    st.session_state["trilha"] = trilha
    with st.sidebar:
        st.segmented_control("Trilha", list(TRILHAS), key="trilha", format_func=TRILHAS.get, required=True,
                             label_visibility="collapsed", on_change=_pediu_troca_de_trilha,
                             help="Cada trilha tem suas próprias vagas, candidaturas e relatórios.")
    pedida = st.session_state.pop("_trilha_pedida", None)
    if pedida and pedida != trilha:
        ir_para(chave_visao_geral(pedida))       # trocar de trilha abre a Visão geral dela
    with st.sidebar:
        for secao, chaves in MENUS[trilha].items():
            st.caption(secao.upper())
            for chave in chaves:
                st.page_link(PAGINAS[chave])


def rodape_sidebar(trilha: str = TRILHA_PADRAO) -> None:
    perfil = perfil_publico()
    iniciais = "".join(p[0] for p in perfil["nome"].split()[:2]).upper() or "R"
    execs = ultimas_execucoes() if trilha == TRILHA_PADRAO else comum_dados.ultimas_execucoes()
    if trilha != TRILHA_PADRAO and not comum_dados.inicializada():
        ponto, texto = "#9ca3af", "Trilha ainda não inicializada"
    elif execs.empty:
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


seletor_e_menu(trilha_atual)
rodape_sidebar(trilha_atual)
navegacao.run()
