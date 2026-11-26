"""Navegação do painel: seletor de trilha, Laravel como padrão, URLs antigas preservadas e prefixo `dados-` nas novas.

Roda o app.py REAL no AppTest, com as páginas trocadas por marcadores e o banco bloqueado.
"""

from pathlib import Path

import pandas as pd
import psycopg
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from vagas.painel import comum, comum_dados, navegacao
from vagas.painel.navegacao import TRILHA_PADRAO, TRILHAS, chave_visao_geral, trilha_da_url
from vagas.painel.paginas import candidaturas, configuracoes, relatorios, sugestoes, vagas, visao_geral
from vagas.painel.paginas.dados import candidaturas as d_candidaturas
from vagas.painel.paginas.dados import configuracoes as d_configuracoes
from vagas.painel.paginas.dados import relatorios as d_relatorios
from vagas.painel.paginas.dados import sugestoes as d_sugestoes
from vagas.painel.paginas.dados import vagas as d_vagas
from vagas.painel.paginas.dados import visao_geral as d_visao_geral

APP = str(Path(__file__).resolve().parents[1] / "vagas" / "painel" / "app.py")
LARAVEL = {"visao_geral": "", "vagas": "vagas", "candidaturas": "candidaturas", "sugestoes": "sugestoes",
           "relatorios": "relatorios", "configuracoes": "configuracoes"}      # a Visão geral é a página padrão (raiz)
DADOS = {"dados_visao_geral": "dados-visao-geral", "dados_vagas": "dados-vagas", "dados_candidaturas": "dados-candidaturas",
         "dados_sugestoes": "dados-sugestoes", "dados_relatorios": "dados-relatorios", "dados_configuracoes": "dados-configuracoes"}
MODULOS = {"laravel-visao": visao_geral, "laravel-vagas": vagas, "laravel-cand": candidaturas, "laravel-sug": sugestoes,
           "laravel-rel": relatorios, "laravel-cfg": configuracoes, "dados-visao": d_visao_geral, "dados-vagas": d_vagas,
           "dados-cand": d_candidaturas, "dados-sug": d_sugestoes, "dados-rel": d_relatorios, "dados-cfg": d_configuracoes}


def marcador(nome):
    def pagina():
        st.write(f"PAGINA:{nome}")
    return pagina


@pytest.fixture(autouse=True)
def app_sem_banco(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("a navegação tentou abrir o banco de dados")
    monkeypatch.setattr(psycopg, "connect", proibido)
    monkeypatch.setattr(comum, "banco_disponivel", lambda: (True, None))
    monkeypatch.setattr(comum, "ultimas_execucoes", lambda: pd.DataFrame())
    monkeypatch.setattr(comum_dados, "ultimas_execucoes", lambda: pd.DataFrame())
    monkeypatch.setattr(comum_dados, "inicializada", lambda: False)
    for nome, modulo in MODULOS.items():
        monkeypatch.setattr(modulo, "pagina", marcador(nome))


def abrir() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def tela(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown if str(m.value).startswith("PAGINA:")]


def links(at: AppTest) -> list[str]:
    return [(l.proto.label, l.proto.page) for l in at.sidebar.get("page_link")]


def seletor(at: AppTest):
    return at.get("segmented_control")[0]


# =========================================================================== padrão e URLs
def test_laravel_e_a_trilha_padrao_e_abre_a_visao_geral_dela():
    at = abrir()
    assert not at.exception and TRILHA_PADRAO == "laravel"
    assert tela(at) == ["PAGINA:laravel-visao"]
    assert at.session_state["trilha"] == "laravel"


def test_seletor_de_trilha_no_topo_da_barra_lateral_com_as_duas_trilhas():
    at = abrir()
    assert [e.type for e in at.sidebar][:2] == ["sidebar", "button_group"]      # o seletor é o primeiro item, antes do menu
    sel = seletor(at)
    assert sel.key == "trilha" and sel.value == "laravel" and sel.options == ["PHP / Laravel", "Engenharia de Dados"]
    assert list(TRILHAS) == ["laravel", "dados"] and list(TRILHAS.values()) == ["PHP / Laravel", "Engenharia de Dados"]


def test_urls_antigas_laravel_permanecem_identicas_e_as_novas_tem_prefixo_dados():
    abrir()
    urls = {k: v.url_path for k, v in navegacao.PAGINAS.items()}
    assert {k: urls[k] for k in LARAVEL} == LARAVEL
    assert {k: urls[k] for k in DADOS} == DADOS
    assert len(urls) == 12 and len(set(urls.values())) == 12     # nenhuma URL repetida
    assert all(u.startswith("dados-") for k, u in urls.items() if k.startswith("dados_"))
    assert not any(u.startswith("dados-") for k, u in urls.items() if not k.startswith("dados_"))


def test_as_seis_paginas_da_trilha_de_dados_estao_registradas():
    abrir()
    assert sorted(k for k in navegacao.PAGINAS if k.startswith("dados_")) == sorted(DADOS)
    assert {navegacao.PAGINAS[k].title for k in DADOS} == {"Visão geral", "Vagas", "Candidaturas", "Relatórios",
                                                           "Sugestões de currículo", "Configurações"}


def test_trilha_da_url_e_chave_da_visao_geral():
    assert [trilha_da_url(u) for u in ("", "vagas", "visao-geral", None, "dados-vagas", "dados-visao-geral")] == \
        ["laravel", "laravel", "laravel", "laravel", "dados", "dados"]
    assert chave_visao_geral("laravel") == "visao_geral" and chave_visao_geral("dados") == "dados_visao_geral"


# =========================================================================== menu e troca de trilha
def test_menu_laravel_mostra_so_as_paginas_laravel():
    at = abrir()
    assert [r for r, _ in links(at)] == ["Visão geral", "Vagas", "Candidaturas", "Sugestões de currículo", "Relatórios", "Configurações"]
    assert [p for _, p in links(at)] == list(LARAVEL.values())
    assert not any("dados" in p for _, p in links(at))


def test_trocar_para_engenharia_de_dados_abre_a_visao_geral_dela_e_mostra_so_o_menu_dela():
    at = abrir()
    seletor(at).set_value("dados").run()
    assert not at.exception, [e.value for e in at.exception]
    assert tela(at) == ["PAGINA:dados-visao"]
    assert at.session_state["trilha"] == "dados"
    assert [p for _, p in links(at)] == list(DADOS.values())
    assert [c.value for c in at.sidebar.caption] == ["BUSCA", "ANÁLISE", "SISTEMA"]


def test_voltar_para_laravel_abre_a_visao_geral_laravel():
    at = abrir()
    seletor(at).set_value("dados").run()
    seletor(at).set_value("laravel").run()
    assert tela(at) == ["PAGINA:laravel-visao"] and at.session_state["trilha"] == "laravel"
    assert [p for _, p in links(at)] == list(LARAVEL.values())


def test_so_abre_a_visao_geral_da_outra_trilha_quando_o_usuario_troca():
    at = abrir()
    seletor(at).set_value("laravel").run()                              # clicar na que já está ativa não navega
    assert tela(at) == ["PAGINA:laravel-visao"]


# =========================================================================== isolamento entre as trilhas
def test_abrir_a_trilha_laravel_nao_consulta_nada_da_trilha_de_dados(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("a trilha Laravel consultou a trilha de dados")
    monkeypatch.setattr(comum_dados, "ultimas_execucoes", proibido)
    monkeypatch.setattr(comum_dados, "inicializada", proibido)
    monkeypatch.setattr(comum_dados, "carregar_vagas", proibido)
    at = abrir()
    assert not at.exception and tela(at) == ["PAGINA:laravel-visao"]


def test_abrir_a_trilha_de_dados_nao_consulta_nada_da_trilha_laravel(monkeypatch):
    at = abrir()

    def proibido(*a, **k):
        raise AssertionError("a trilha de dados consultou a trilha Laravel")
    monkeypatch.setattr(comum, "ultimas_execucoes", proibido)
    monkeypatch.setattr(comum, "carregar_vagas", proibido)
    seletor(at).set_value("dados").run()
    assert not at.exception, [e.value for e in at.exception]
    assert tela(at) == ["PAGINA:dados-visao"]


def test_rodape_mostra_a_situacao_da_trilha_ativa(monkeypatch):
    at = abrir()
    assert "Nenhuma coleta ainda" in " ".join(h.proto.body for h in at.sidebar.get("html"))        # Laravel: sem coletas
    seletor(at).set_value("dados").run()
    assert "Trilha ainda não inicializada" in " ".join(h.proto.body for h in at.sidebar.get("html"))
    monkeypatch.setattr(comum_dados, "inicializada", lambda: True)
    seletor(at).set_value("dados").run()
    assert "Nenhuma coleta ainda" in " ".join(h.proto.body for h in at.sidebar.get("html"))


def test_banco_indisponivel_continua_mostrando_a_tela_amigavel(monkeypatch):
    monkeypatch.setattr(comum, "banco_disponivel", lambda: (False, "connection refused"))
    at = abrir()
    assert not at.exception and tela(at) == []
    assert any("Banco de dados indisponível" in h.proto.body for h in at.get("html")) and not at.get("segmented_control")


def test_o_codigo_da_navegacao_laravel_ficou_igual():
    """As seis páginas Laravel continuam registradas com os mesmos títulos, ícones e URLs de antes."""
    abrir()
    assert {k: (navegacao.PAGINAS[k].title, navegacao.PAGINAS[k].url_path) for k in LARAVEL} == {
        "visao_geral": ("Visão geral", ""), "vagas": ("Vagas", "vagas"), "candidaturas": ("Candidaturas", "candidaturas"),
        "sugestoes": ("Sugestões de currículo", "sugestoes"), "relatorios": ("Relatórios", "relatorios"),
        "configuracoes": ("Configurações", "configuracoes")}
