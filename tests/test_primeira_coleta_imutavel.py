"""A data/hora em que a vaga entrou no radar (`primeira_coleta`) não muda nas coletas seguintes, nas duas trilhas.

Banco DESCARTÁVEL restaurado de backup (nunca o real). O `now()` do Postgres é fixo dentro da transação do teste, por isso a
primeira_coleta é recuada para uma data antiga antes de coletar de novo.
"""

from tests.test_dados_integracao import banco, conn  # noqa: F401 (fixtures)
from tests.test_dados_nota import PERFIL
from tests.test_painel_dados_integracao import painel  # noqa: F401 (fixture)
from vagas import db as laravel_db
from vagas.painel import comum_dados as cd
from vagas.trilhas.dados import pipeline


def _vaga_laravel(**extra):
    v = {"id": "github:imut#1", "fonte": "github", "id_externo": "imut#1", "titulo": "Dev Laravel", "empresa": "X", "descricao": "d",
         "url": "https://exemplo.test/1", "localizacao": None, "modelo_trabalho": "remoto", "nivel": "junior", "tecnologias": ["Laravel"],
         "cita_laravel": True, "chave_dedupe": "x|dev laravel", "publicada_em": "2026-11-01T10:00:00+00:00", "so_titulo": False}
    v.update(extra)
    return v


def test_laravel_upsert_mantem_a_primeira_coleta(conn):
    laravel_db.salvar_vagas(conn, [_vaga_laravel()])
    conn.execute("update silver.vagas set primeira_coleta = '2026-01-02 03:04:05+00' where id = 'github:imut#1'")
    antes = conn.execute("select primeira_coleta, ultima_coleta from silver.vagas where id = 'github:imut#1'").fetchone()
    assert laravel_db.salvar_vagas(conn, [_vaga_laravel(titulo="Dev Laravel (atualizada)")]) == 0       # não é inserção nova
    depois = conn.execute("select titulo, primeira_coleta, ultima_coleta from silver.vagas where id = 'github:imut#1'").fetchone()
    assert depois["titulo"].endswith("(atualizada)")
    assert depois["primeira_coleta"] == antes["primeira_coleta"]                                     # horário original intacto
    assert depois["ultima_coleta"] > depois["primeira_coleta"] and depois["ultima_coleta"] != antes["primeira_coleta"]


def test_dados_recoleta_mantem_a_primeira_coleta_e_ultima_coleta_so_avanca(painel):
    conn = painel
    conn.execute("update silver.dados_vagas set primeira_coleta = '2026-01-02 03:04:05+00', ultima_coleta = '2026-01-02 03:04:05+00'")
    n = conn.execute("select count(*) as n from silver.dados_vagas").fetchone()["n"]
    pipeline.rodar(conn=conn, perfil=PERFIL, formacao=[])
    linhas_ = conn.execute("select primeira_coleta, ultima_coleta from silver.dados_vagas").fetchall()
    assert len(linhas_) == n > 0                                                                      # nada duplicado
    assert {str(l["primeira_coleta"]) for l in linhas_} == {"2026-01-02 03:04:05+00:00"}              # nunca substituída
    assert all(l["ultima_coleta"] > l["primeira_coleta"] for l in linhas_)                           # só a última coleta andou
    cd.limpar_cache()
    gold = cd.carregar_vagas()
    assert set(gold["primeira_coleta"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S")) == {"2026-01-02 03:04:05"}
