"""Etapa 5: pipeline da trilha de Engenharia de Dados.

Parte 1 (sem banco): deduplicação, avaliação, modo --testar e linha de comando.
Parte 2 (banco DESCARTÁVEL, restaurado de backup; nunca o real): gravação, idempotência, falha isolada e execuções.
Rede simulada e dados sintéticos em todo o arquivo.
"""

import copy

import psycopg
import pytest

from tests.dados_simulados import RedeSimulada, issues_github
from tests.test_dados_integracao import banco, conn, contar, hashes_dados, hashes_laravel, nova_vaga  # noqa: F401 (fixtures)
from tests.test_dados_nota import PERFIL
from vagas.coleta.base import FonteIgnorada
from vagas.trilhas.dados import coleta as coleta_mod
from vagas.trilhas.dados import db as dados_db
from vagas.trilhas.dados import pipeline
from vagas.trilhas.dados.coleta import Coleta

FORMACAO = []


@pytest.fixture
def sem_banco(monkeypatch):
    """Qualquer tentativa de abrir o banco (ou de criar o schema) quebra o teste."""
    def proibido(*a, **k):
        raise AssertionError("o modo de teste/unidade tentou usar o banco de dados")
    monkeypatch.setattr(psycopg, "connect", proibido)
    monkeypatch.setattr(dados_db, "conectar", proibido)
    monkeypatch.setattr(dados_db, "criar_esquema", proibido)


def coleta_de(fonte, *vagas, brutas=None, falhas=()):
    return Coleta(fonte, list(vagas), [f"bronze/{fonte}.json"], len(vagas) if brutas is None else brutas, list(falhas))


# =========================================================================== deduplicação e avaliação
def test_deduplicar_por_id_fica_com_a_descricao_mais_longa_e_conta_repeticoes_logicas():
    a = nova_vaga("1", fonte="github", descricao="Requisitos:\n- SQL")
    a_maior = {**a, "descricao": a["descricao"] + "\nmais detalhes"}
    b = nova_vaga("2", fonte="adzuna")                                       # outra fonte, mesma vaga (mesma chave_dedupe)
    unicas, repetidas = pipeline.deduplicar([a, a_maior, a, b])
    assert [v["id"] for v in unicas] == [a["id"], b["id"]] and unicas[0]["descricao"].endswith("mais detalhes")
    assert repetidas == 1 and pipeline.deduplicar([]) == ([], 0)


def test_avaliar_isola_a_vaga_que_falha():
    boa, ruim = nova_vaga("1"), {**nova_vaga("2"), "categoria_cargo": None}      # sem categoria: calcular() recusa
    avaliacoes, falhas = pipeline.avaliar([boa, ruim], PERFIL, FORMACAO)
    assert [i for i, _ in avaliacoes] == [boa["id"]] and len(falhas) == 1 and "github:2" in falhas[0]


def test_processar_dedup_avalia_e_descarta_o_que_nao_pode_ser_avaliado():
    ok, ruim = nova_vaga("1"), {**nova_vaga("2", titulo="[Remoto] Analytics Engineer Jr"), "nivel": "diretor"}
    p = pipeline.processar(coleta_de("github", ok, ok, ruim, brutas=9, falhas=["x: KeyError"]), PERFIL, FORMACAO)
    assert [v["id"] for v in p.vagas] == [ok["id"]] and [i for i, _ in p.avaliacoes] == [ok["id"]]
    assert p.brutas == 9 and len(p.falhas) == 2 and p.arquivos == ["bronze/github.json"]
    assert pipeline._erro_parcial(p).startswith("parcial: 2 item(ns)")
    assert pipeline._erro_parcial(pipeline.processar(coleta_de("github", ok), PERFIL, FORMACAO)) is None


# =========================================================================== modo --testar (sem banco)
def test_testar_resume_por_fonte_categorias_niveis_alvos_e_faixas(monkeypatch, tmp_path, sem_banco):
    RedeSimulada(monkeypatch, tmp_path)
    rel = pipeline.testar(perfil=PERFIL, formacao=FORMACAO)
    gh, az, gm = (rel["fontes"][f] for f in ("github", "adzuna", "gmail"))
    assert (gh["status"], gh["brutas"], gh["na_trilha"], gh["alvos"]) == ("ok", 6, 4, 2)
    assert dict(gh["categorias"]) == {"engenharia_dados": 3, "relacionada": 1}
    assert dict(gh["niveis"]) == {"junior": 2, "nao_informado": 1, "senior": 1}   # 107 é júnior (relacionada)
    assert (az["na_trilha"], az["alvos"]) == (2, 2) and dict(az["niveis"]) == {"junior": 1, "estagio": 1}
    assert (gm["na_trilha"], gm["alvos"]) == (3, 2) and dict(gm["categorias"]) == {"engenharia_dados": 2, "analytics_engineer": 1}
    t = rel["total"]
    assert (t["na_trilha"], t["alvos"]) == (9, 6) and sum(t["faixas"].values()) == 9
    assert [v["alvo"] for v in rel["vagas"]] == [True] * 6 + [False] * 3             # alvos primeiro, depois por nota
    notas_alvo = [v["nota"] for v in rel["vagas"] if v["alvo"]]
    assert notas_alvo == sorted(notas_alvo, reverse=True)
    so_titulo = [v for v in rel["vagas"] if v["so_titulo"]]
    assert len(so_titulo) == 3 and all(v["confianca"] == "baixa" for v in so_titulo)


def test_testar_nao_usa_o_banco_mas_pode_gravar_o_bronze(monkeypatch, tmp_path, sem_banco):
    rede = RedeSimulada(monkeypatch, tmp_path)
    pipeline.testar(perfil=PERFIL, formacao=FORMACAO)            # a fixture sem_banco quebraria qualquer acesso
    assert sorted(f for f, _ in rede.bronze) == ["dados_adzuna", "dados_github", "dados_gmail"]


def test_testar_mostra_fonte_ignorada_e_fonte_com_erro_sem_parar(monkeypatch, tmp_path, sem_banco):
    def quebra():
        raise ConnectionError("sem rede")

    def ignora():
        raise FonteIgnorada("sem chave")
    rel = pipeline.testar({"adzuna": ignora, "gmail": quebra, "github": lambda: coleta_de("github", nova_vaga("1"))},
                          PERFIL, FORMACAO)
    assert rel["fontes"]["adzuna"]["status"] == "ignorada" and "sem chave" in rel["fontes"]["adzuna"]["erro"]
    assert rel["fontes"]["gmail"]["status"] == "erro" and "ConnectionError: sem rede" in rel["fontes"]["gmail"]["erro"]
    assert rel["fontes"]["github"]["na_trilha"] == 1 and rel["total"]["na_trilha"] == 1


def test_testar_com_respostas_vazias(monkeypatch, tmp_path, sem_banco):
    RedeSimulada(monkeypatch, tmp_path, github={"backend-br/vagas": []}, adzuna=lambda t, p: [], emails=[])
    rel = pipeline.testar(perfil=PERFIL, formacao=FORMACAO)
    assert rel["total"]["na_trilha"] == 0 and rel["vagas"] == [] and all(f["status"] == "ok" for f in rel["fontes"].values())
    assert "TOTAL: 0 na trilha" in pipeline.relatorio_texto(rel)


def test_testar_marca_item_com_falha_de_normalizacao_como_parcial(monkeypatch, tmp_path, sem_banco):
    RedeSimulada(monkeypatch, tmp_path, github={"backend-br/vagas": [{"number": 1, "html_url": "u"}, *issues_github()]})
    rel = pipeline.testar(perfil=PERFIL, formacao=FORMACAO)
    assert rel["fontes"]["github"]["status"] == "parcial" and len(rel["fontes"]["github"]["falhas"]) == 1


def test_relatorio_texto_ajuda_a_achar_falsos_positivos(monkeypatch, tmp_path, sem_banco):
    RedeSimulada(monkeypatch, tmp_path)
    texto = pipeline.relatorio_texto(pipeline.testar(perfil=PERFIL, formacao=FORMACAO), limite=5)
    assert "nada foi gravado no banco" in texto and "[github] ok" in texto and "[gmail] ok" in texto
    assert "relacionada" in texto and "[só título]" in texto and "ALVO" in texto and "e mais 4" in texto
    assert "Engenheiro de Dados Júnior - Empresa Exemplo" in texto


def test_linha_de_comando_testar_nao_cria_schema_nem_abre_o_banco(monkeypatch, tmp_path, sem_banco, capsys):
    RedeSimulada(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "carregar_perfil", lambda: (PERFIL, FORMACAO))
    assert pipeline.main(["--testar", "--limite", "3"]) == 0
    saida = capsys.readouterr().out
    assert "MODO DE TESTE" in saida and "TOTAL: 9 na trilha, 6 alvo" in saida


# =========================================================================== gravação em banco descartável
def rede_e_perfil(monkeypatch, tmp_path, **kw):
    return RedeSimulada(monkeypatch, tmp_path, **kw)


def rodar(conn, **kw):
    return pipeline.rodar(conn=conn, perfil=kw.pop("perfil", PERFIL), formacao=FORMACAO, **kw)


def test_rodar_grava_vagas_avaliacoes_e_execucoes(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path)
    laravel_antes = hashes_laravel(conn)
    resumo = rodar(conn)
    assert {f: resumo[f]["status"] for f in ("github", "adzuna", "gmail")} == {"github": "ok", "adzuna": "ok", "gmail": "ok"}
    assert (resumo["github"]["na_trilha"], resumo["adzuna"]["na_trilha"], resumo["gmail"]["na_trilha"]) == (4, 2, 3)
    assert (resumo["github"]["novas"], resumo["adzuna"]["novas"], resumo["gmail"]["novas"]) == (4, 2, 3)
    assert contar(conn, "silver.dados_vagas") == 9 == contar(conn, "silver.dados_vaga_pontuacao")
    assert resumo["vagas_alvo"] == contar(conn, "gold.dados_vagas_alvo") > 0
    execs = {e["fonte"]: e for e in dados_db.carregar_execucoes(conn)}
    assert set(execs) == {"github", "adzuna", "gmail"} and all(e["erro"] is None and e["finalizada_em"] for e in execs.values())
    assert (execs["github"]["qtd_coletada"], execs["github"]["qtd_nova"]) == (4, 4)
    assert conn.execute("select arquivo_bronze from silver.dados_execucoes where fonte = 'gmail'").fetchone()["arquivo_bronze"].endswith("simulado.json")
    assert hashes_laravel(conn) == laravel_antes                                  # nada da trilha Laravel mudou


def test_rodar_persiste_o_que_o_modo_testar_mostra(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path)
    previsto = pipeline.testar(perfil=PERFIL, formacao=FORMACAO)
    rodar(conn)
    gravado = {g["id"]: g for g in dados_db.carregar_gold(conn)}
    for v in previsto["vagas"]:
        assert gravado[v["id"]]["compatibilidade"] == v["nota"] and gravado[v["id"]]["alvo"] is v["alvo"]
        assert gravado[v["id"]]["categoria_cargo"] == v["categoria"]


def test_rodar_e_idempotente(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path)
    rodar(conn)
    antes = hashes_dados(conn)
    segundo = rodar(conn)
    assert [segundo[f]["novas"] for f in ("github", "adzuna", "gmail")] == [0, 0, 0]
    assert contar(conn, "silver.dados_vagas") == 9 and contar(conn, "silver.dados_execucoes") == 6
    depois = hashes_dados(conn)
    assert {t: h for t, h in depois.items() if t != "silver.dados_execucoes"} == {t: h for t, h in antes.items() if t != "silver.dados_execucoes"}


def test_rodar_preserva_status_e_historico_e_recalcula_a_nota(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path)
    rodar(conn)
    vaga_id = "github:backend-br/vagas#101"
    dados_db.definir_status(vaga_id, "candidatei", conn=conn)
    nota_antes = conn.execute("select compatibilidade from silver.dados_vaga_pontuacao where vaga_id = %s", (vaga_id,)).fetchone()["compatibilidade"]
    perfil_melhor = copy.deepcopy(PERFIL)
    perfil_melhor["tecnologias"]["Airflow"] = {"nivel": "profissional"}
    perfil_melhor["tecnologias"]["dbt"] = {"nivel": "profissional"}
    rodar(conn, perfil=perfil_melhor)
    nota_depois = conn.execute("select compatibilidade from silver.dados_vaga_pontuacao where vaga_id = %s", (vaga_id,)).fetchone()["compatibilidade"]
    assert nota_depois > nota_antes and contar(conn, "silver.dados_vaga_pontuacao") == 9
    assert conn.execute("select status from silver.dados_vaga_status where vaga_id = %s", (vaga_id,)).fetchone()["status"] == "candidatei"
    assert [h["status"] for h in dados_db.carregar_historico(conn)] == ["candidatei"]


def test_falha_de_uma_fonte_nao_impede_as_outras(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path, emails=FonteIgnorada("Gmail não autorizado"))

    def adzuna_quebrada():
        raise RuntimeError("API fora do ar")
    resumo = rodar(conn, coletores={"adzuna": adzuna_quebrada, "github": coleta_mod.coletar_github, "gmail": coleta_mod.coletar_gmail})
    assert resumo["adzuna"]["status"] == "erro" and resumo["adzuna"]["erro"] == "RuntimeError: API fora do ar"
    assert resumo["gmail"]["status"] == "ignorada" and resumo["gmail"]["erro"] == "ignorada: Gmail não autorizado"
    assert resumo["github"]["status"] == "ok" and contar(conn, "silver.dados_vagas") == 4      # o GitHub foi gravado
    erros = {e["fonte"]: e["erro"] for e in dados_db.carregar_execucoes(conn)}
    assert erros == {"adzuna": "RuntimeError: API fora do ar", "gmail": "ignorada: Gmail não autorizado", "github": None}


def test_falha_na_gravacao_desfaz_so_aquela_fonte(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path)
    sem_url = {**nova_vaga("900", fonte="adzuna"), "url": None}                      # a nota calcula, mas o banco recusa (url NOT NULL)
    resumo = rodar(conn, coletores={"adzuna": lambda: coleta_de("adzuna", nova_vaga("1", fonte="adzuna"), sem_url),
                                    "github": coleta_mod.coletar_github})
    assert resumo["adzuna"]["status"] == "erro" and "NotNullViolation" in resumo["adzuna"]["erro"]
    assert resumo["github"]["status"] == "ok"
    assert contar(conn, "silver.dados_vagas", "fonte = 'adzuna'") == 0 and contar(conn, "silver.dados_vagas", "fonte = 'github'") == 4
    assert contar(conn, "silver.dados_vaga_pontuacao") == 4                          # nenhuma avaliação órfã da fonte que falhou


def test_falha_parcial_de_normalizacao_fica_registrada_sem_perder_o_resto(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path, github={"backend-br/vagas": [{"number": 1, "html_url": "u"}, *issues_github()]})
    resumo = rodar(conn)
    assert resumo["github"]["status"] == "parcial" and resumo["github"]["na_trilha"] == 4 and resumo["github"]["falhas"] == 1
    erro = conn.execute("select erro from silver.dados_execucoes where fonte = 'github'").fetchone()["erro"]
    assert erro.startswith("parcial: 1 item(ns)") and contar(conn, "silver.dados_vagas", "fonte = 'github'") == 4


def test_respostas_vazias_gravam_so_a_execucao(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path, github={"backend-br/vagas": []}, adzuna=lambda t, p: [], emails=[])
    resumo = rodar(conn)
    assert all(resumo[f]["status"] == "ok" and resumo[f]["na_trilha"] == 0 for f in ("github", "adzuna", "gmail"))
    assert contar(conn, "silver.dados_vagas") == 0 and contar(conn, "silver.dados_execucoes") == 3 and resumo["vagas_alvo"] == 0


def test_vaga_fora_do_alvo_e_gravada_mas_nao_aparece_no_alvo(conn, monkeypatch, tmp_path):
    rede_e_perfil(monkeypatch, tmp_path)
    rodar(conn)
    gold = {g["id"]: g for g in dados_db.carregar_gold(conn)}
    assert gold["github:backend-br/vagas#103"]["alvo"] is False and gold["github:backend-br/vagas#107"]["alvo"] is False
    assert gold["linkedin:6000000002"]["alvo"] is False                              # pleno
    alvo = {g["id"] for g in dados_db.carregar_gold(conn, so_alvo=True)}
    assert "github:backend-br/vagas#101" in alvo and "github:backend-br/vagas#103" not in alvo
    assert not any(i.startswith("github:backend-br/vagas#104") or i.endswith("#105") for i in gold)   # backend e cientista nem entram


def test_rodar_sem_conexao_usa_o_vagas_db_conectar_e_nunca_o_banco_real_nos_testes(monkeypatch, tmp_path):
    """Sem `conn`, o pipeline abre a conexão pelo vagas.db.conectar. Aqui isso é interceptado: nunca chega no banco real."""
    RedeSimulada(monkeypatch, tmp_path)
    tentativas = []

    def interceptado():
        tentativas.append(1)
        raise ConnectionError("interceptado pelo teste")
    monkeypatch.setattr(dados_db, "conectar", interceptado)
    with pytest.raises(ConnectionError):
        pipeline.rodar(perfil=PERFIL, formacao=FORMACAO)
    assert tentativas == [1]
