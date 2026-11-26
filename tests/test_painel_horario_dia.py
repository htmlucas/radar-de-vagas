"""Vagas por dia de entrada no radar e horário de entrada nos cards das duas trilhas (PHP/Laravel e Engenharia de Dados).

O horário vem sempre de `primeira_coleta` (nunca de `publicada_em` nem de `ultima_coleta`), no fuso de São Paulo.
Páginas rodam no AppTest com dados sintéticos e SEM banco (a imutabilidade, em banco descartável, está em test_primeira_coleta_imutavel.py).
"""

from datetime import date

import pandas as pd
import psycopg
import pytest
from streamlit.testing.v1 import AppTest

from tests.dados_painel_simulado import linha
from tests.test_painel_dados_paginas import html, titulos
from vagas.painel import comum, comum_dados as cd, logica
from vagas.painel.horario import SEM_HORARIO, adicionada_ao_radar
from vagas.painel.paginas import vagas as pagina_laravel
from vagas.painel.paginas.dados import vagas as pagina_dados
from vagas.trilhas.dados import db as dados_db

DIA_25, DIA_24 = date(2026, 11, 25), date(2026, 11, 24)


def linhas() -> list[dict]:
    """Quatro vagas: A (25/11 20:34 em SP), B (UTC já é dia 25, mas em SP ainda é 24/11 23:10), C (24/11) e D (sem horário)."""
    dados = [("A", "Vaga Alfa", "2026-11-25T23:34:00+00:00", 90), ("B", "Vaga Beta", "2026-11-25T02:10:00+00:00", 80),
             ("C", "Vaga Gama", "2026-11-24T14:00:00+00:00", 70), ("D", "Vaga Delta", None, 60)]
    saida = []
    for k, titulo, entrada, nota in dados:
        v = linha(f"github:{k}", titulo, empresa=f"Empresa {k}", nota=nota, publicada="2026-10-01T09:00:00+00:00",
                  tecnologias=("Python", "SQL"))
        v["primeira_coleta"], v["ultima_coleta"] = entrada, "2026-11-25T23:59:00+00:00"
        v["cita_laravel"] = True
        saida.append(v)
    return saida


def df() -> pd.DataFrame:
    return cd.preparar_vagas_dados(linhas())


def _dados():
    importlib = __import__("importlib")
    importlib.import_module("vagas.painel.paginas.dados.vagas").pagina()


def _laravel():
    importlib = __import__("importlib")
    importlib.import_module("vagas.painel.paginas.vagas").pagina()


@pytest.fixture(autouse=True)
def cenario(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("a página tentou abrir o banco de dados")
    monkeypatch.setattr(psycopg, "connect", proibido)
    monkeypatch.setattr(dados_db, "conectar", proibido)
    monkeypatch.setattr(cd, "inicializada", lambda: True)
    monkeypatch.setattr(cd, "carregar_vagas", df)
    monkeypatch.setattr(pagina_laravel, "carregar_vagas", df)
    monkeypatch.setattr(pagina_laravel, "carregar_base", lambda: None)
    monkeypatch.setattr(comum, "carregar_vagas", df)


def estado_dados(**m) -> dict:
    e = {k: (list(v) if isinstance(v, list) else v) for k, v in pagina_dados.PADRAO.items()}
    e.update(dv_modal=[], dv_todas=True, dv_status=[], dv_dia=DIA_25)
    e.update(m)
    return e


def estado_laravel(**m) -> dict:
    e = {"f_busca": "", "f_perfil": False, "f_modal": [], "f_nivel": [], "f_tec": [], "f_fontes": [], "f_status": [],
         "f_modo": "dia", "f_dia": DIA_25, "f_dias": 90, "f_ordem": "compatibilidade"}
    e.update(m)
    return e


def rodar(funcao, estado: dict) -> AppTest:
    at = AppTest.from_function(funcao, default_timeout=60)
    for k, v in estado.items():
        at.session_state[k] = v
    return at.run()


def dados(**m) -> AppTest:
    return rodar(_dados, estado_dados(**m))


def laravel(**m) -> AppTest:
    return rodar(_laravel, estado_laravel(**m))


def pilulas(at: AppTest) -> list[str]:
    return [b.proto.options[i].content if hasattr(b.proto.options[i], "content") else str(b.proto.options[i])
            for b in at.get("button_group") if b.proto.label == "Encontradas no dia" for i in range(len(b.proto.options))]


# =========================================================================== 1. agrupamento diário igual ao Laravel
@pytest.mark.parametrize("dia, esperado", [(DIA_25, ["Vaga Alfa"]), (DIA_24, ["Vaga Beta", "Vaga Gama"])])
def test_cada_dia_mostra_as_mesmas_vagas_nas_duas_trilhas(dia, esperado):
    d, lv = dados(dv_dia=dia), laravel(f_dia=dia)
    assert not d.exception and not lv.exception, [e.value for e in d.exception + lv.exception]
    assert sorted(titulos(d)) == sorted(titulos(lv)) == esperado


def test_os_dias_oferecidos_e_a_contagem_sao_os_mesmos_nas_duas_trilhas():
    d, lv = dados(), laravel()
    assert pilulas(d) == pilulas(lv) and len(pilulas(d)) == 2
    assert [p.split(" · ")[1] for p in pilulas(d)] == ["1", "2"]                       # 25/11 tem 1 vaga; 24/11 tem 2
    for at in (d, lv):
        assert "Vagas encontradas em 25/11/2026" in html(at)


def test_logica_de_dia_e_a_mesma_funcao_para_as_duas_trilhas():
    base = df()
    assert logica.dias_com_vagas(base) == [(DIA_25, 1), (DIA_24, 2)]
    assert logica.dia_padrao(base, hoje=date(2026, 11, 26)) == DIA_25
    assert list(pagina_dados.filtrar(base, estado_dados(dv_dia=DIA_24))["id"].sort_values()) == ["github:B", "github:C"]


def test_por_periodo_na_trilha_de_dados_ignora_o_dia_e_usa_a_publicacao():
    at = dados(dv_modo="periodo", dv_dias=None)
    assert sorted(titulos(at)) == ["Vaga Alfa", "Vaga Beta", "Vaga Delta", "Vaga Gama"]


# =========================================================================== 2/6. horário nos cards e fuso
def test_card_das_duas_trilhas_mostra_data_e_hora_de_sao_paulo():
    for at in (dados(), laravel()):
        assert "Adicionada ao radar: 25/11/2026 às 20:34" in html(at)                     # 23:34 UTC = 20:34 em SP


def test_conversao_de_fuso_pode_mudar_o_dia():
    assert adicionada_ao_radar(pd.Timestamp("2026-11-25T02:10:00+00:00")) == "Adicionada ao radar: 24/11/2026 às 23:10"
    for at in (dados(dv_dia=DIA_24), laravel(f_dia=DIA_24)):
        assert "Adicionada ao radar: 24/11/2026 às 23:10" in html(at) and "Adicionada ao radar: 24/11/2026 às 11:00" in html(at)


def test_horario_naive_e_tratado_como_utc():
    assert adicionada_ao_radar(pd.Timestamp("2026-11-25 23:34:00")) == "Adicionada ao radar: 25/11/2026 às 20:34"


# =========================================================================== 4/5. só primeira_coleta; sem horário não inventa
def test_card_nao_usa_publicada_em_nem_ultima_coleta():
    for at in (dados(), laravel()):
        corpo = html(at)
        assert "01/10/2026" not in corpo.split("Adicionada ao radar")[1].split("</span>")[0]      # publicada_em
        assert "23:59" not in corpo and "20:59" not in corpo                                       # ultima_coleta


def test_vaga_sem_horario_nao_recebe_data_inventada():
    assert adicionada_ao_radar(None) == adicionada_ao_radar(pd.NaT) == SEM_HORARIO
    assert "horário indisponível" in SEM_HORARIO
    for at in (dados(dv_modo="periodo", dv_dias=None), laravel(f_modo="periodo", f_dias=None)):
        corpo = html(at)
        assert corpo.count("horário indisponível") == 1 and corpo.count("Adicionada ao radar: ") == 4
        assert pagina_dados.filtrar(df(), estado_dados(dv_dia=DIA_25)).query("id == 'github:D'").empty   # D não cai em nenhum dia


# =========================================================================== 7. filtros dentro do dia
def test_filtros_continuam_valendo_dentro_do_dia_nas_duas_trilhas():
    for at in (dados(dv_dia=DIA_24, dv_busca="gama"), laravel(f_dia=DIA_24, f_busca="gama")):
        assert titulos(at) == ["Vaga Gama"]
    for at in (dados(dv_dia=DIA_24, dv_status=["interessa"]), laravel(f_dia=DIA_24, f_status=["interessa"])):
        assert titulos(at) == []                                                                # nenhuma vaga do dia com esse status
    assert titulos(dados(dv_dia=DIA_24, dv_fontes=["github"])) == titulos(laravel(f_dia=DIA_24, f_fontes=["github"]))
    assert titulos(dados(dv_dia=DIA_24, dv_ordem="empresa")) == ["Vaga Beta", "Vaga Gama"]


def test_ordenacao_atual_dentro_do_dia_nao_mudou():
    assert titulos(dados(dv_dia=DIA_24)) == titulos(laravel(f_dia=DIA_24)) == ["Vaga Beta", "Vaga Gama"]    # maior compatibilidade
    assert titulos(dados(dv_dia=DIA_24, dv_ordem="radar")) == ["Vaga Beta", "Vaga Gama"]                  # B entrou depois que C


def test_dia_vazio_na_trilha_de_dados_explica_o_que_fazer():
    corpo = html(dados(dv_dia=date(2026, 11, 20)))
    assert "Nenhuma vaga com esses filtros" in corpo and "Escolha outro dia" in corpo
