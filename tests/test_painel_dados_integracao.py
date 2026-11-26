"""Painel da trilha de dados contra um banco DESCARTÁVEL (restaurado de backup; nunca o real).

O pipeline grava vagas simuladas (sem rede) e as páginas leem de verdade de gold.dados_vagas. Cobre também:
banco sem as tabelas dados_* (mensagem amigável, nada criado) e o isolamento total das tabelas Laravel.
"""

from contextlib import contextmanager

import pytest
from streamlit.testing.v1 import AppTest

from tests.dados_painel_simulado import BASE, DADOS
from tests.dados_simulados import RedeSimulada
from tests.test_dados_integracao import banco, conn, contar, hashes_dados, hashes_laravel  # noqa: F401 (fixtures)
from tests.test_dados_nota import PERFIL
from tests.test_painel_dados_paginas import PAGINAS, _executar, html, kpis
from vagas.painel import acoes_dados as ad
from vagas.painel import comum_dados as cd
from vagas.painel.paginas.dados import visao_geral
from vagas.trilhas.dados import coleta as coleta_mod
from vagas.trilhas.dados import db as dados_db
from vagas.trilhas.dados import pipeline
from vagas.trilhas.dados.curriculo import combinar


@pytest.fixture
def painel(conn, monkeypatch, tmp_path):
    """Banco descartável com a trilha preenchida pelo pipeline e o painel apontado para ele."""
    @contextmanager
    def conectar():
        with conn.transaction():          # como uma conexão por uso: um erro desfaz só aquele uso, não o teste inteiro
            yield conn
    monkeypatch.setattr(dados_db, "conectar", conectar)
    monkeypatch.setattr(cd, "curriculo_combinado", lambda: combinar(BASE, DADOS))
    monkeypatch.setattr(cd, "agendamento", lambda: None)
    RedeSimulada(monkeypatch, tmp_path)
    pipeline.rodar(conn=conn, perfil=PERFIL, formacao=[])
    cd.limpar_cache()
    yield conn
    cd.limpar_cache()


def rodar(nome: str, **sessao) -> AppTest:
    at = AppTest.from_function(_executar, args=(nome,), default_timeout=90)
    for k, v in sessao.items():
        at.session_state[k] = v
    return at.run()


# =========================================================================== as seis páginas lendo o banco de verdade
@pytest.mark.parametrize("nome", PAGINAS)
def test_cada_pagina_abre_sem_erro_lendo_gold_dados_vagas(painel, nome):
    at = rodar(nome)
    assert not at.exception, [e.value for e in at.exception]
    assert "ainda não foi inicializada" not in html(at)


def test_visao_geral_bate_com_o_que_o_pipeline_gravou(painel):
    df = cd.carregar_vagas()
    n = visao_geral.indicadores(df)
    k = kpis(rodar("visao_geral"))
    assert n["coletadas"] == 9 and n["alvo"] == 6
    assert (k["Vagas coletadas"], k["Vagas-alvo"], k["Remotas compatíveis"]) == ("9", "6", str(n["remotas"]))
    remotas = cd.remotas_compativeis(df)
    assert 0 < len(remotas) <= n["alvo"] and set(remotas["modelo_trabalho"]) == {"remoto"}
    assert not (set(remotas["id"]) & set(df[~df["alvo"]]["id"]))        # relacionadas, pleno e sênior nunca entram


def test_gold_trouxe_as_colunas_que_o_painel_usa_e_o_pipeline_gravou_tudo(painel):
    df = cd.carregar_vagas()
    for coluna in ("compatibilidade", "faixa", "parcelas", "motivos", "alertas", "confianca_nivel", "elegibilidade", "categoria_cargo",
                   "req_obrigatorios", "req_desejaveis", "citados_em_atividades", "fontes", "alvo", "status"):
        assert coluna in df.columns, coluna
    v = df[df["id"] == "github:backend-br/vagas#101"].iloc[0]
    assert v["categoria_cargo"] == "engenharia_dados" and v["nivel"] == "junior" and v["modelo_trabalho"] == "remoto"
    assert len(v["parcelas"]) == 7 and v["req_obrigatorios"] and v["status"] == "nova" and v["fontes"] == ["github"]
    assert df["compatibilidade"].notna().all() and set(df["confianca_nivel"]) <= {"alta", "media", "baixa"}


def test_vagas_mostra_as_remotas_alvo_do_banco(painel):
    at = rodar("vagas")
    esperado = cd.remotas_compativeis(cd.carregar_vagas())
    assert esperado["titulo"].nunique() >= 1
    from tests.test_painel_dados_paginas import titulos
    assert sorted(titulos(at)) == sorted(esperado["titulo"])


# =========================================================================== candidaturas e histórico no banco
VAGA = "github:backend-br/vagas#101"
OUTRA = "adzuna:1"


def test_fluxo_de_candidatura_grava_so_nas_tabelas_dados(painel):
    laravel_antes = hashes_laravel(painel)
    ad.mudar_status(VAGA, "interessa")
    ad.mudar_status(VAGA, "candidatei")
    dados_db.definir_nota(VAGA, "falei com a recrutadora")
    ad.mudar_status(OUTRA, "descartada", "Exige inglês avançado", "pede fluência")
    cd.limpar_cache()
    df = cd.carregar_vagas().set_index("id")
    assert (df.loc[VAGA, "status"], df.loc[VAGA, "nota"]) == ("candidatei", "falei com a recrutadora")
    assert (df.loc[OUTRA, "status"], df.loc[OUTRA, "motivo_descarte"], df.loc[OUTRA, "detalhe_descarte"]) == (
        "descartada", "Exige inglês avançado", "pede fluência")
    hist = cd.historico()
    assert list(hist[hist["vaga_id"] == VAGA]["status"]) == ["interessa", "candidatei"]
    assert hashes_laravel(painel) == laravel_antes                                  # nada da trilha Laravel mudou


def test_paginas_refletem_candidaturas_e_descartes(painel):
    ad.mudar_status(VAGA, "candidatei")
    ad.mudar_status(OUTRA, "descartada", "Exige inglês avançado", None)
    cd.limpar_cache()
    k = kpis(rodar("candidaturas"))
    assert k["Candidaturas"] == "1" and k["Entrevistas"] == "0"
    assert kpis(rodar("visao_geral"))["Candidaturas em andamento"] == "1"
    rel = rodar("relatorios")
    assert not rel.exception and "Funil de candidaturas" in html(rel)
    assert "Exige inglês avançado" in " ".join(str(d.value.to_dict()) for d in rel.dataframe)
    assert OUTRA not in set(cd.alvo_ativas(cd.carregar_vagas())["id"])                 # descartada sai dos números do alvo


def test_restaurar_descartada_volta_a_ser_nova_e_o_historico_guarda_tudo(painel):
    ad.mudar_status(OUTRA, "descartada", "Outro", None)
    ad.mudar_status(OUTRA, None)
    cd.limpar_cache()
    assert cd.carregar_vagas().set_index("id").loc[OUTRA, "status"] == "nova"
    h = cd.historico()
    assert list(h[h["vaga_id"] == OUTRA]["status"]) == ["descartada", "nova"]


def test_sugestoes_para_vaga_do_banco(painel):
    at = rodar("sugestoes", vaga_sugestao_dados=VAGA)
    assert not at.exception
    codigos = " ".join(c.value for c in at.get("code"))
    assert "pós-graduação em andamento" in codigos and "Engenheiro de Dados" not in codigos.split("\n")[0]


def test_configuracoes_mostra_as_execucoes_gravadas(painel):
    at = rodar("configuracoes")
    assert not at.exception
    corpo = html(at)
    assert "Última coleta" in corpo and "na trilha" in corpo and "Nunca executada" not in corpo
    assert len(at.dataframe) == 1 and set(at.dataframe[0].value["fonte"]) == {"github", "adzuna", "gmail"}
    assert len(at.button) == 0


def test_paginas_nao_gravam_nada_so_de_serem_abertas(painel):
    antes = hashes_dados(painel)
    for nome in PAGINAS:
        assert not rodar(nome).exception
    assert hashes_dados(painel) == antes


# =========================================================================== isolamento das tabelas Laravel
def test_abrir_todas_as_paginas_nao_altera_nenhuma_tabela_laravel(painel, banco):
    for nome in PAGINAS:
        rodar(nome)
    assert hashes_laravel(painel) == banco["laravel_antes"]["hashes"]


# =========================================================================== banco sem as tabelas dados_*
SEM_SCHEMA = ("drop view if exists gold.dados_vagas_alvo; drop view if exists gold.dados_vagas; "
              "drop table if exists silver.dados_vaga_pontuacao, silver.dados_vaga_status_historico, silver.dados_vaga_status, "
              "silver.dados_vagas, silver.dados_execucoes")


@pytest.fixture
def banco_sem_schema(conn, monkeypatch):
    """O banco da cópia, como o real hoje: sem nenhum objeto dados_* (o DDL sofre rollback no fim do teste)."""
    conn.execute(SEM_SCHEMA)

    @contextmanager
    def conectar():
        with conn.transaction():          # como uma conexão por uso: um erro desfaz só aquele uso, não o teste inteiro
            yield conn

    def nao_pode(*a, **k):
        raise AssertionError("o painel tentou criar schema ou coletar")
    monkeypatch.setattr(dados_db, "conectar", conectar)
    monkeypatch.setattr(dados_db, "criar_esquema", nao_pode)
    monkeypatch.setattr(pipeline, "rodar", nao_pode)
    for nome in coleta_mod.COLETORES:
        monkeypatch.setitem(coleta_mod.COLETORES, nome, nao_pode)
    cd.limpar_cache()
    yield conn
    cd.limpar_cache()


def objetos_dados(conn) -> int:
    return conn.execute("select count(*) as n from information_schema.tables where table_name like 'dados\\_%'").fetchone()["n"]


@pytest.mark.parametrize("nome", ["visao_geral", "vagas", "candidaturas", "relatorios", "sugestoes"])
def test_sem_schema_a_pagina_explica_como_inicializar_e_nao_cria_nada(banco_sem_schema, nome):
    assert objetos_dados(banco_sem_schema) == 0 and cd.inicializada() is False
    at = rodar(nome)
    assert not at.exception, [e.value for e in at.exception]
    corpo = html(at)
    assert "A trilha de Engenharia de Dados ainda não foi inicializada" in corpo and "python -m vagas.trilhas.dados.pipeline" in corpo
    assert objetos_dados(banco_sem_schema) == 0                                   # nada foi criado


def test_sem_schema_configuracoes_continua_util_e_somente_leitura(banco_sem_schema, banco):
    at = rodar("configuracoes")
    assert not at.exception
    assert any("ainda não foi inicializada" in i.value for i in at.info) and "Termos de busca" in html(at)
    assert len(at.button) == 0 and objetos_dados(banco_sem_schema) == 0


def test_sem_schema_os_carregadores_devolvem_vazio_e_a_laravel_segue_igual(banco_sem_schema, banco):
    assert cd.carregar_vagas().empty and cd.execucoes().empty and cd.historico().empty and cd.ultimas_execucoes().empty
    assert hashes_laravel(banco_sem_schema) == banco["laravel_antes"]["hashes"]
