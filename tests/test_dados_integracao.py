"""Etapa 4: testes de integração do banco da trilha de Engenharia de Dados.

SEGURANÇA: nada aqui escreve no banco real. A sessão de testes
  1. pega o backup mais recente de dados/backups (fora do Git);
  2. cria um banco NOVO e descartável (`vagas_teste_dados_<8 hex>`), recusando se o nome já existir
     ou for reservado (o banco real, `vagas_conferencia` do script de regressão, bancos do sistema);
  3. restaura o backup nele e aplica sql/schema_dados.sql só ali;
  4. no fim, remove somente o banco que ela mesma criou.
Cada teste roda numa transação que sofre rollback. Sem Docker, Postgres ou backup, os testes são pulados.
Todos os dados são sintéticos.
"""

import hashlib
import json
import re
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import dict_row

from tests.test_dados_nota import DESC_A, PERFIL
from vagas import db as laravel_db
from vagas.config import RAIZ, config
from vagas.tratamento.normalizar import montar_vaga
from vagas.trilhas.dados import db as dados_db
from vagas.trilhas.dados.normalizar import e_alvo, montar_vaga_dados
from vagas.trilhas.dados.nota import calcular

CONTAINER = "vagas-laravel-db"
PREFIXO = "vagas_teste_dados_"
RESERVADOS = {config.db_nome, "vagas_conferencia", "postgres", "template0", "template1"}
PADRAO_NOME = re.compile(rf"^{PREFIXO}[0-9a-f]{{8}}$")
VOLATEIS = {"ultima_coleta", "calculado_em"}
TABELAS_LARAVEL = ["silver.vagas", "silver.vaga_status", "silver.vaga_status_historico", "silver.vaga_pontuacao",
                   "silver.execucoes", "gold.vagas", "gold.vagas_alvo"]
OBJETOS_DADOS = {"silver.dados_vagas", "silver.dados_vaga_status", "silver.dados_vaga_status_historico",
                 "silver.dados_vaga_pontuacao", "silver.dados_execucoes", "gold.dados_vagas", "gold.dados_vagas_alvo"}


# --------------------------------------------------------------------------- banco descartável
def _conninfo(dbname: str) -> str:
    return (f"host={config.db_host} port={config.db_porta} dbname={dbname} "
            f"user={config.db_usuario} password={config.db_senha}")


def _checar_nome(nome: str) -> None:
    assert PADRAO_NOME.match(nome) and nome not in RESERVADOS, f"nome de banco não permitido: {nome}"


def criar_banco_descartavel(backup: Path) -> str:
    """Cria um banco novo e restaura o backup nele. Recusa se o nome já existir. Só toca no banco criado."""
    nome = PREFIXO + uuid.uuid4().hex[:8]
    _checar_nome(nome)
    with psycopg.connect(_conninfo("postgres"), autocommit=True) as admin:
        if admin.execute("select 1 from pg_database where datname = %s", (nome,)).fetchone():
            raise RuntimeError(f"o banco {nome} já existe: recusado")
        admin.execute(f'create database "{nome}"')
    try:
        with backup.open("rb") as f:
            r = subprocess.run(["docker", "exec", "-i", CONTAINER, "pg_restore", "-U", config.db_usuario, "-d", nome,
                                "--no-owner"], stdin=f, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(f"pg_restore falhou: {r.stderr.decode(errors='replace')[:400]}")
    except BaseException:
        remover_banco(nome)
        raise
    return nome


def remover_banco(nome: str) -> None:
    _checar_nome(nome)          # só remove banco com o nosso prefixo
    with psycopg.connect(_conninfo("postgres"), autocommit=True) as admin:
        admin.execute(f'drop database if exists "{nome}" with (force)')


def conectar_descartavel(nome: str):
    _checar_nome(nome)
    return psycopg.connect(_conninfo(nome), row_factory=dict_row)


# --------------------------------------------------------------------------- impressões do banco
def hashes_laravel(conn) -> dict:
    saida = {}
    for tabela in TABELAS_LARAVEL:
        linhas = [{k: v for k, v in l.items() if k not in VOLATEIS}
                  for l in conn.execute(f"select * from {tabela}").fetchall()]
        saida[tabela] = (len(linhas), hashlib.sha256(json.dumps(sorted(map(str, linhas))).encode()).hexdigest()[:16])
    return saida


def hashes_dados(conn) -> dict:
    saida = {}
    for tabela in sorted(OBJETOS_DADOS):
        linhas = [{k: v for k, v in l.items() if k not in VOLATEIS}
                  for l in conn.execute(f"select * from {tabela}").fetchall()]
        saida[tabela] = (len(linhas), hashlib.sha256(json.dumps(sorted(map(str, linhas))).encode()).hexdigest()[:16])
    return saida


def catalogo(conn, dados: bool) -> dict:
    """Estrutura (colunas, índices, constraints, definição das views) dos objetos dados_* (ou dos demais)."""
    op = "like" if dados else "not like"
    padrao = "dados\\_%"
    return {
        "colunas": conn.execute(
            f"select table_schema, table_name, column_name, data_type, is_nullable, column_default "
            f"from information_schema.columns where table_schema in ('silver', 'gold') and table_name {op} %s "
            f"order by 1, 2, ordinal_position", (padrao,)).fetchall(),
        "indices": conn.execute(
            f"select schemaname, tablename, indexname, indexdef from pg_indexes "
            f"where schemaname in ('silver', 'gold') and tablename {op} %s order by 1, 2, 3", (padrao,)).fetchall(),
        "constraints": conn.execute(
            f"select n.nspname, c.relname, k.conname, pg_get_constraintdef(k.oid) as def from pg_constraint k "
            f"join pg_class c on c.oid = k.conrelid join pg_namespace n on n.oid = c.relnamespace "
            f"where n.nspname in ('silver', 'gold') and c.relname {op} %s order by 1, 2, 3", (padrao,)).fetchall(),
        "views": conn.execute(
            f"select schemaname, viewname, definition from pg_views where schemaname in ('silver', 'gold') "
            f"and viewname {op} %s order by 1, 2", (padrao,)).fetchall(),
    }


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def banco():
    backups = sorted((config.pasta_dados / "backups").glob("*.dump"))
    if not backups:
        pytest.skip("sem backup em dados/backups")
    if subprocess.run(["docker", "exec", CONTAINER, "true"], capture_output=True).returncode != 0:
        pytest.skip("contêiner do Postgres indisponível")
    try:
        nome = criar_banco_descartavel(backups[-1])
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    try:
        with conectar_descartavel(nome) as conn:
            assert conn.execute("select current_database() as b").fetchone()["b"] == nome != config.db_nome
            antes = {"hashes": hashes_laravel(conn), "catalogo": catalogo(conn, dados=False)}
            assert conn.execute("select count(*) as n from information_schema.tables where table_name like 'dados\\_%'"
                                ).fetchone()["n"] == 0, "a cópia restaurada já tinha objetos dados_*"
            dados_db.criar_esquema(conn)
            conn.commit()
        yield {"nome": nome, "laravel_antes": antes}
    finally:
        remover_banco(nome)


@pytest.fixture
def conn(banco, monkeypatch):
    """Conexão ao banco descartável; tudo que o teste fizer sofre rollback."""
    c = conectar_descartavel(banco["nome"])
    assert c.execute("select current_database() as b").fetchone()["b"] == banco["nome"]

    def sem_banco_real():
        raise AssertionError("o módulo da trilha de dados tentou abrir conexão com o banco REAL")

    monkeypatch.setattr(dados_db, "conectar", sem_banco_real)
    monkeypatch.setattr(laravel_db, "conectar", sem_banco_real)
    yield c
    c.rollback()
    c.close()


# --------------------------------------------------------------------------- dados sintéticos
def nova_vaga(id_externo="1", titulo="[Remoto] Engenheiro de Dados Júnior", fonte="github", descricao=DESC_A.format(aws="AWS"),
              empresa="Acme", **kw):
    v = montar_vaga_dados(fonte=fonte, id_externo=id_externo, titulo=titulo, url=f"https://exemplo.test/{id_externo}",
                          empresa=empresa, descricao=descricao, publicada_em="2026-11-20T10:00:00+00:00", **kw)
    assert v is not None
    return v


def contar(conn, tabela, where="true", params=()):
    return conn.execute(f"select count(*) as n from {tabela} where {where}", params).fetchone()["n"]


# =========================================================================== esquema
def test_schema_cria_os_objetos_novos(conn):
    existentes = {r["o"] for r in conn.execute(
        "select table_schema || '.' || table_name as o from information_schema.tables "
        "where table_name like 'dados\\_%'").fetchall()}
    assert existentes == OBJETOS_DADOS


def test_schema_e_idempotente(conn):
    antes = catalogo(conn, dados=True)
    dados_db.criar_esquema(conn)
    dados_db.criar_esquema(conn)
    assert catalogo(conn, dados=True) == antes


def test_schema_nao_toca_nos_objetos_laravel(conn, banco):
    assert catalogo(conn, dados=False) == banco["laravel_antes"]["catalogo"]
    assert hashes_laravel(conn) == banco["laravel_antes"]["hashes"]     # mesmos dados do backup, depois do schema
    dados_db.criar_esquema(conn)
    assert hashes_laravel(conn) == banco["laravel_antes"]["hashes"]


def test_estatico_so_objetos_dados_no_sql_e_no_modulo():
    sql = re.sub(r"--[^\n]*", "", (RAIZ / "sql" / "schema_dados.sql").read_text(encoding="utf-8")).lower()
    codigo = (RAIZ / "vagas" / "trilhas" / "dados" / "db.py").read_text(encoding="utf-8").lower()
    proibidos = re.compile(r"\b(silver\.(vagas|vaga_status|vaga_status_historico|vaga_pontuacao|execucoes)|gold\.(vagas|vagas_alvo))\b")
    assert not proibidos.search(sql) and not proibidos.search(codigo)
    assert not re.search(r"drop\s+schema|truncate|drop\s+table", sql + codigo)
    for alvo in re.findall(r"(?:create|alter|drop)\s+(?:table|view|index)\s+(?:if\s+(?:not\s+)?exists\s+)?([\w.\"]+)", sql):
        assert "dados_" in alvo, alvo
    for alvo in re.findall(r"(?:insert\s+into|(?<!do\s)update|delete\s+from)\s+(?!set\b)([\w.]+)", codigo):
        assert alvo.startswith("silver.dados_"), alvo
    assert "references silver.dados_vagas" in sql and "references silver.vagas" not in sql   # só FKs entre dados_*


# =========================================================================== vagas
def test_inserir_vaga_e_ler_de_volta(conn):
    v = nova_vaga()
    assert dados_db.salvar_vagas(conn, [v]) == 1
    r = conn.execute("select * from silver.dados_vagas where id = %s", (v["id"],)).fetchone()
    assert (r["fonte"], r["id_externo"], r["categoria_cargo"], r["nivel"], r["modelo_trabalho"]) == (
        "github", "1", "engenharia_dados", "junior", "remoto")
    assert r["tecnologias"] == v["tecnologias"] and r["conceitos"] == v["conceitos"]
    assert r["req_obrigatorios"] == v["req_obrigatorios"] and r["req_desejaveis"] == ["Spark", "dbt", "Docker"]
    assert r["citados_em_atividades"] == [] and r["so_titulo"] is False and r["chave_dedupe"] == v["chave_dedupe"]


def test_upsert_e_idempotente_e_nao_duplica(conn):
    v = nova_vaga()
    assert dados_db.salvar_vagas(conn, [v]) == 1
    primeira = conn.execute("select primeira_coleta from silver.dados_vagas").fetchone()["primeira_coleta"]
    assert dados_db.salvar_vagas(conn, [v]) == 0 and dados_db.salvar_vagas(conn, [v, v]) == 0
    assert contar(conn, "silver.dados_vagas") == 1
    assert conn.execute("select primeira_coleta from silver.dados_vagas").fetchone()["primeira_coleta"] == primeira
    v2 = {**v, "titulo": "[Remoto] Engenheiro de Dados Júnior (atualizado)", "nivel": "trainee"}
    assert dados_db.salvar_vagas(conn, [v2]) == 0
    r = conn.execute("select titulo, nivel from silver.dados_vagas").fetchone()
    assert r["titulo"].endswith("(atualizado)") and r["nivel"] == "trainee" and contar(conn, "silver.dados_vagas") == 1


def test_unicidade_por_fonte_e_id_externo(conn):
    dados_db.salvar_vagas(conn, [nova_vaga()])
    with pytest.raises(errors.UniqueViolation), conn.transaction():
        conn.execute("insert into silver.dados_vagas (id, fonte, id_externo, titulo, url, categoria_cargo, chave_dedupe) "
                     "values ('outro-id', 'github', '1', 't', 'u', 'dev_etl', 'k')")


def test_vaga_de_email_mantem_a_data_de_publicacao_mais_antiga(conn):
    v = {**nova_vaga(fonte="linkedin"), "so_titulo": True}
    dados_db.salvar_vagas(conn, [{**v, "publicada_em": "2026-11-22T08:00:00+00:00"}])
    dados_db.salvar_vagas(conn, [{**v, "publicada_em": "2026-11-20T08:00:00+00:00"}])
    dados_db.salvar_vagas(conn, [{**v, "publicada_em": "2026-11-24T08:00:00+00:00"}])
    assert str(conn.execute("select publicada_em from silver.dados_vagas").fetchone()["publicada_em"]).startswith("2026-11-20")


def test_upsert_nao_mexe_em_status_nem_avaliacao(conn):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    dados_db.salvar_avaliacoes(conn, [(v["id"], calcular(v, PERFIL))])
    dados_db.definir_status(v["id"], "candidatei", conn=conn)
    dados_db.salvar_vagas(conn, [{**v, "descricao": v["descricao"] + "\nmais texto"}])
    assert contar(conn, "silver.dados_vaga_status", "status = 'candidatei'") == 1
    assert contar(conn, "silver.dados_vaga_pontuacao") == 1 and contar(conn, "silver.dados_vaga_status_historico") == 1


def test_deduplicacao_logica_no_gold(conn):
    github = nova_vaga("10", fonte="github", descricao="Requisitos:\n- SQL")
    adzuna = nova_vaga("20", fonte="adzuna", descricao=DESC_A.format(aws="AWS"))          # mesma vaga, texto maior
    assert github["chave_dedupe"] == adzuna["chave_dedupe"]
    dados_db.salvar_vagas(conn, [github, adzuna])
    assert contar(conn, "silver.dados_vagas") == 2           # as duas cópias ficam na silver
    gold = conn.execute("select id from gold.dados_vagas").fetchall()
    assert [g["id"] for g in gold] == [adzuna["id"]]          # o gold mostra uma só: a de descrição mais longa


def test_deduplicacao_prefere_cargo_alvo_a_relacionada(conn):
    alvo = nova_vaga("1", descricao="Requisitos:\n- SQL")
    relacionada = {**nova_vaga("2", descricao=DESC_A.format(aws="AWS") * 3), "categoria_cargo": "relacionada"}
    dados_db.salvar_vagas(conn, [alvo, relacionada])
    assert [g["id"] for g in conn.execute("select id from gold.dados_vagas").fetchall()] == [alvo["id"]]


# =========================================================================== avaliação
DESC_ALERTAS = ("Estágio. Exige estar cursando graduação em Computação.\nRequisitos:\n- Python e SQL\n- 3 anos de experiência\n"
                "- Inglês avançado\nDesejável:\n- Power BI\n")


def test_persistencia_da_nota_das_parcelas_da_confianca_e_dos_alertas(conn):
    v = nova_vaga("5", titulo="Estágio em Engenharia de Dados", descricao=DESC_ALERTAS, localizacao="Santiago, Chile")
    av = calcular(v, PERFIL)
    assert len(av.alertas) == 4
    dados_db.salvar_vagas(conn, [v])
    dados_db.salvar_avaliacoes(conn, [(v["id"], av)])
    r = conn.execute("select * from silver.dados_vaga_pontuacao where vaga_id = %s", (v["id"],)).fetchone()
    assert r["compatibilidade"] == av.nota and r["faixa"] == av.faixa
    assert r["parcelas"] == [asdict(p) for p in av.parcelas] and len(r["parcelas"]) == 7
    assert r["motivos"] == av.motivos and r["alertas"] == av.alertas
    assert (r["confianca_pontos"], r["confianca_nivel"], r["confianca_motivos"]) == (
        av.confianca.pontos, av.confianca.nivel, av.confianca.motivos)
    assert r["elegibilidade"] == "alerta" and r["formacao_exigida"] == av.parcela("formacao").detalhe


def test_reavaliar_atualiza_sem_duplicar(conn):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    dados_db.salvar_avaliacoes(conn, [(v["id"], calcular(v, PERFIL))])
    melhor = calcular({**v, "modelo_trabalho": "presencial"}, PERFIL)
    dados_db.salvar_avaliacoes(conn, [(v["id"], melhor)])
    dados_db.salvar_avaliacoes(conn, [(v["id"], melhor)])
    assert contar(conn, "silver.dados_vaga_pontuacao") == 1
    assert conn.execute("select compatibilidade from silver.dados_vaga_pontuacao").fetchone()["compatibilidade"] == melhor.nota


# =========================================================================== status e histórico
def test_criacao_e_alteracao_de_status_com_historico(conn):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    for status in ("interessa", "candidatei", "entrevista", None):
        dados_db.definir_status(v["id"], status, conn=conn)
    assert [h["status"] for h in dados_db.carregar_historico(conn)] == ["interessa", "candidatei", "entrevista", "nova"]
    assert contar(conn, "silver.dados_vaga_status") == 0            # None = volta a ser "nova"
    assert conn.execute("select status from gold.dados_vagas").fetchone()["status"] == "nova"


def test_descartar_com_motivo_corrigir_motivo_e_nota(conn):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    dados_db.definir_status(v["id"], "descartada", "Empresa não me interessa", "  vaga no México  ", conn=conn)
    r = conn.execute("select * from silver.dados_vaga_status").fetchone()
    assert (r["status"], r["motivo_descarte"], r["detalhe_descarte"]) == ("descartada", "Empresa não me interessa", "vaga no México")
    dados_db.definir_motivo(v["id"], "Exige inglês avançado", "", conn=conn)
    dados_db.definir_nota(v["id"], "falei com a recrutadora", conn=conn)
    r = conn.execute("select * from silver.dados_vaga_status").fetchone()
    assert (r["motivo_descarte"], r["detalhe_descarte"], r["nota"]) == ("Exige inglês avançado", None, "falei com a recrutadora")
    dados_db.definir_status(v["id"], "candidatei", "motivo ignorado", conn=conn)
    r = conn.execute("select * from silver.dados_vaga_status").fetchone()
    assert (r["status"], r["motivo_descarte"], r["nota"]) == ("candidatei", None, "falei com a recrutadora")   # nota mantida
    assert conn.execute("select motivo from silver.dados_vaga_status_historico order by id").fetchall()[0]["motivo"] == "Empresa não me interessa"


def test_status_invalido_e_vaga_inexistente_nao_gravam_nada(conn):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    with pytest.raises(ValueError):
        dados_db.definir_status(v["id"], "contratado", conn=conn)
    with pytest.raises(errors.ForeignKeyViolation):
        dados_db.definir_status("github:nao-existe", "interessa", conn=conn)
    conn.rollback()
    assert contar(conn, "silver.dados_vaga_status") == 0 and contar(conn, "silver.dados_vaga_status_historico") == 0


def test_historico_e_a_mudanca_de_status_sao_atomicos(conn):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    conn.execute("alter table silver.dados_vaga_status_historico add constraint falha_de_teste check (status <> 'proposta')")
    with pytest.raises(errors.CheckViolation):
        dados_db.definir_status(v["id"], "proposta", conn=conn)
    assert contar(conn, "silver.dados_vaga_status") == 0 and contar(conn, "silver.dados_vaga_status_historico") == 0


# =========================================================================== integridade
def test_integridade_referencial_e_cascata(conn):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    with pytest.raises(errors.ForeignKeyViolation), conn.transaction():
        conn.execute("insert into silver.dados_vaga_pontuacao (vaga_id, compatibilidade, faixa, confianca_pontos, "
                     "confianca_nivel, elegibilidade) values ('github:nao-existe', 50, 'baixa', 1, 'baixa', 'ok')")
    dados_db.salvar_avaliacoes(conn, [(v["id"], calcular(v, PERFIL))])
    dados_db.definir_status(v["id"], "interessa", conn=conn)
    conn.execute("delete from silver.dados_vagas where id = %s", (v["id"],))
    assert contar(conn, "silver.dados_vaga_status") == contar(conn, "silver.dados_vaga_status_historico") == 0
    assert contar(conn, "silver.dados_vaga_pontuacao") == 0


@pytest.mark.parametrize("sql", [
    "update silver.dados_vagas set categoria_cargo = 'php'",
    "update silver.dados_vagas set nivel = 'diretor'",
    "update silver.dados_vagas set modelo_trabalho = 'lua'",
    "update silver.dados_vaga_pontuacao set compatibilidade = 101",
    "update silver.dados_vaga_pontuacao set elegibilidade = 'talvez'",
    "update silver.dados_vaga_pontuacao set confianca_pontos = 8",
    "update silver.dados_vaga_status set status = 'contratado'",
])
def test_restricoes_de_dominio(conn, sql):
    v = nova_vaga()
    dados_db.salvar_vagas(conn, [v])
    dados_db.salvar_avaliacoes(conn, [(v["id"], calcular(v, PERFIL))])
    dados_db.definir_status(v["id"], "interessa", conn=conn)
    with pytest.raises(errors.CheckViolation), conn.transaction():
        conn.execute(sql)


# =========================================================================== gold
def test_gold_junta_vaga_avaliacao_e_status(conn):
    v = nova_vaga()
    av = calcular(v, PERFIL)
    dados_db.salvar_vagas(conn, [v])
    assert dados_db.carregar_gold(conn)[0]["status"] == "nova" and dados_db.carregar_gold(conn)[0]["compatibilidade"] is None
    dados_db.salvar_avaliacoes(conn, [(v["id"], av)])
    dados_db.definir_status(v["id"], "candidatei", conn=conn)
    g = dados_db.carregar_gold(conn)[0]
    assert (g["id"], g["status"], g["compatibilidade"], g["faixa"], g["alvo"]) == (v["id"], "candidatei", av.nota, "alta", True)
    assert g["status_em"] is not None and g["motivos"] == av.motivos and g["confianca_nivel"] == "alta"
    assert g["categoria_cargo"] == "engenharia_dados" and g["req_desejaveis"] == ["Spark", "dbt", "Docker"]
    assert [x["id"] for x in dados_db.carregar_gold(conn, so_alvo=True)] == [v["id"]]


@pytest.mark.parametrize("categoria", ["engenharia_dados", "analytics_engineer", "dev_etl", "relacionada"])
@pytest.mark.parametrize("nivel", [None, "estagio", "trainee", "junior", "pleno", "senior"])
def test_coluna_alvo_do_gold_bate_com_a_regra_em_python(conn, categoria, nivel):
    v = {**nova_vaga(), "categoria_cargo": categoria, "nivel": nivel}
    dados_db.salvar_vagas(conn, [v])
    assert conn.execute("select alvo from gold.dados_vagas").fetchone()["alvo"] is e_alvo(categoria, nivel)


def test_gold_alvo_exclui_descartadas_e_nao_alvo(conn):
    boa = nova_vaga("1", titulo="[Remoto] Engenheiro de Dados Júnior")
    descartada = nova_vaga("2", titulo="[Remoto] Analytics Engineer Jr")
    pleno = nova_vaga("3", titulo="[Remoto] Engenheiro de Dados Pleno")
    relacionada = {**nova_vaga("4", titulo="Desenvolvedor Python Júnior"), "categoria_cargo": "relacionada"}
    dados_db.salvar_vagas(conn, [boa, descartada, pleno, relacionada])
    dados_db.definir_status(descartada["id"], "descartada", "Outro", conn=conn)
    assert {g["id"] for g in dados_db.carregar_gold(conn)} == {boa["id"], descartada["id"], pleno["id"], relacionada["id"]}
    assert [g["id"] for g in dados_db.carregar_gold(conn, so_alvo=True)] == [boa["id"]]


def test_gold_tem_as_colunas_do_contrato_do_gold_laravel(conn):
    colunas = {c["column_name"] for c in conn.execute(
        "select column_name from information_schema.columns where table_schema = 'gold' and table_name = 'dados_vagas'").fetchall()}
    laravel = {c["column_name"] for c in conn.execute(
        "select column_name from information_schema.columns where table_schema = 'gold' and table_name = 'vagas'").fetchall()}
    comuns_esperadas = {"status", "nota", "compatibilidade", "motivos", "status_em", "alvo", "motivo_descarte", "detalhe_descarte",
                        "publicada_em", "primeira_coleta", "titulo", "empresa", "tecnologias", "nivel", "modelo_trabalho"}
    assert comuns_esperadas <= colunas and comuns_esperadas <= laravel


def test_execucoes(conn):
    exec_id = dados_db.registrar_inicio(conn, "adzuna")
    dados_db.registrar_fim(conn, exec_id, coletadas=10, novas=3, arquivo="a.json")
    exec2 = dados_db.registrar_inicio(conn, "gmail")
    dados_db.registrar_fim(conn, exec2, erro="ignorada: sem token")
    r = {e["fonte"]: e for e in dados_db.carregar_execucoes(conn)}
    assert (r["adzuna"]["qtd_coletada"], r["adzuna"]["qtd_nova"], r["adzuna"]["erro"]) == (10, 3, None)
    assert r["gmail"]["erro"] == "ignorada: sem token" and r["gmail"]["finalizada_em"] is not None
    assert contar(conn, "silver.execucoes", "fonte = 'adzuna' and arquivo_bronze = 'a.json'") == 0   # tabela Laravel intocada


# =========================================================================== isolamento entre as trilhas
def fluxo_completo_da_trilha_de_dados(conn):
    vagas = [nova_vaga("1"), nova_vaga("2", fonte="adzuna", titulo="Analytics Engineer Jr", descricao="Requisitos:\n- SQL"),
             nova_vaga("3", titulo="Estágio em Engenharia de Dados", descricao=DESC_ALERTAS)]
    exec_id = dados_db.registrar_inicio(conn, "github")
    dados_db.salvar_vagas(conn, vagas)
    dados_db.salvar_vagas(conn, vagas)
    dados_db.registrar_fim(conn, exec_id, coletadas=3, novas=3)
    dados_db.salvar_avaliacoes(conn, [(v["id"], calcular(v, PERFIL)) for v in vagas])
    dados_db.definir_status(vagas[0]["id"], "candidatei", conn=conn)
    dados_db.definir_status(vagas[1]["id"], "descartada", "Outro", "x", conn=conn)
    dados_db.definir_nota(vagas[0]["id"], "obs", conn=conn)
    dados_db.carregar_gold(conn)
    return vagas


def test_nenhuma_operacao_da_trilha_de_dados_altera_as_tabelas_laravel(conn, banco):
    antes = hashes_laravel(conn)
    fluxo_completo_da_trilha_de_dados(conn)
    assert hashes_laravel(conn) == antes == banco["laravel_antes"]["hashes"]
    assert catalogo(conn, dados=False) == banco["laravel_antes"]["catalogo"]


def test_status_de_uma_trilha_nao_altera_a_outra(conn, monkeypatch):
    # O módulo Laravel REAL (vagas.db) é usado, mas apontado para a conexão do banco descartável.
    @contextmanager
    def conectar_descartavel_():
        yield conn

    monkeypatch.setattr(laravel_db, "conectar", conectar_descartavel_)
    laravel = montar_vaga(fonte="teste", id_externo="L1", titulo="Desenvolvedor Laravel Júnior", url="u", empresa="Acme",
                          descricao="Laravel e PHP")
    laravel_db.salvar_vagas(conn, [laravel])
    vagas_dados = fluxo_completo_da_trilha_de_dados(conn)

    # 1) status Laravel não altera nada de dados_*
    dados_antes = hashes_dados(conn)
    laravel_db.definir_status(laravel["id"], "interessa")
    laravel_db.definir_status(laravel["id"], "candidatei")
    laravel_db.definir_nota(laravel["id"], "obs laravel")
    assert hashes_dados(conn) == dados_antes
    assert conn.execute("select status from silver.vaga_status where vaga_id = %s", (laravel["id"],)).fetchone()["status"] == "candidatei"

    # 2) status de dados não altera nada das tabelas Laravel
    laravel_antes = hashes_laravel(conn)
    dados_db.definir_status(vagas_dados[0]["id"], "entrevista", conn=conn)
    dados_db.definir_status(vagas_dados[1]["id"], None, conn=conn)
    assert hashes_laravel(conn) == laravel_antes
    assert contar(conn, "silver.vaga_status_historico", "vaga_id = %s", (laravel["id"],)) == 2


def test_a_mesma_vaga_pode_existir_nas_duas_trilhas_com_status_independentes(conn, monkeypatch):
    @contextmanager
    def conectar_descartavel_():
        yield conn

    monkeypatch.setattr(laravel_db, "conectar", conectar_descartavel_)
    laravel = montar_vaga(fonte="github", id_externo="X", titulo="Engenheiro de Dados PHP", url="u", empresa="Acme",
                          descricao="Laravel")
    laravel_db.salvar_vagas(conn, [laravel])
    dados = nova_vaga("X", titulo="Engenheiro de Dados PHP")
    dados_db.salvar_vagas(conn, [dados])
    laravel_db.definir_status(laravel["id"], "descartada", "Outro")
    dados_db.definir_status(dados["id"], "interessa", conn=conn)
    assert conn.execute("select status from silver.vaga_status").fetchall()[-1]["status"] == "descartada"
    assert conn.execute("select status from gold.dados_vagas").fetchone()["status"] == "interessa"


# =========================================================================== fluxo completo
def test_fluxo_completo_inserir_avaliar_e_registrar_candidatura(conn):
    v = nova_vaga()
    assert dados_db.salvar_vagas(conn, [v]) == 1
    av = calcular(v, PERFIL)
    dados_db.salvar_avaliacoes(conn, [(v["id"], av)])
    dados_db.definir_status(v["id"], "interessa", conn=conn)
    dados_db.definir_status(v["id"], "candidatei", conn=conn)
    g = dados_db.carregar_gold(conn, so_alvo=True)[0]
    assert (g["status"], g["compatibilidade"], g["alvo"], g["elegibilidade"]) == ("candidatei", 88, True, "nao_se_aplica")
    assert [h["status"] for h in dados_db.carregar_historico(conn)] == ["interessa", "candidatei"]
