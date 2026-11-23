from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from vagas.config import RAIZ, config


@contextmanager
def conectar():
    with psycopg.connect(config.conninfo, row_factory=dict_row) as conn:
        yield conn


def criar_esquema() -> None:
    sql = (RAIZ / "sql" / "schema.sql").read_text(encoding="utf-8")
    with conectar() as conn:
        conn.execute(sql)


def registrar_inicio(conn, fonte: str) -> int:
    return conn.execute(
        "insert into silver.execucoes (fonte) values (%s) returning id", (fonte,)
    ).fetchone()["id"]


def registrar_fim(conn, execucao_id: int, *, coletadas=None, novas=None, arquivo=None, erro=None) -> None:
    conn.execute(
        """
        update silver.execucoes
           set finalizada_em = now(), qtd_coletada = %s, qtd_nova = %s,
               arquivo_bronze = %s, erro = %s
         where id = %s
        """,
        (coletadas, novas, arquivo, erro, execucao_id),
    )


def salvar_vagas(conn, vagas: list[dict]) -> int:
    """Upsert na silver. Devolve quantas vagas eram novas."""
    novas = 0
    for v in vagas:
        linha = conn.execute(
            """
            insert into silver.vagas (
                id, fonte, id_externo, titulo, empresa, descricao, url, localizacao,
                modelo_trabalho, nivel, tecnologias, cita_laravel, chave_dedupe, publicada_em, so_titulo
            ) values (
                %(id)s, %(fonte)s, %(id_externo)s, %(titulo)s, %(empresa)s, %(descricao)s,
                %(url)s, %(localizacao)s, %(modelo_trabalho)s, %(nivel)s, %(tecnologias)s,
                %(cita_laravel)s, %(chave_dedupe)s, %(publicada_em)s, %(so_titulo)s
            )
            on conflict (id) do update set
                titulo = excluded.titulo, empresa = excluded.empresa,
                descricao = excluded.descricao, url = excluded.url,
                localizacao = excluded.localizacao, modelo_trabalho = excluded.modelo_trabalho,
                nivel = excluded.nivel, tecnologias = excluded.tecnologias,
                cita_laravel = excluded.cita_laravel, chave_dedupe = excluded.chave_dedupe,
                publicada_em = excluded.publicada_em, so_titulo = excluded.so_titulo,
                ultima_coleta = now()
            returning (xmax = 0) as inserida
            """,
            v,
        ).fetchone()
        novas += int(linha["inserida"])
    return novas


def salvar_pontuacoes(conn, pontuacoes: list[tuple[str, int, list[str]]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into silver.vaga_pontuacao (vaga_id, compatibilidade, motivos) values (%s, %s, %s)
            on conflict (vaga_id) do update
               set compatibilidade = excluded.compatibilidade, motivos = excluded.motivos,
                   calculado_em = now()
            """,
            pontuacoes,
        )


def definir_status(vaga_id: str, status: str | None, nota: str | None = None) -> None:
    with conectar() as conn:
        if status is None:
            conn.execute("delete from silver.vaga_status where vaga_id = %s", (vaga_id,))
            return
        conn.execute(
            """
            insert into silver.vaga_status (vaga_id, status, nota) values (%s, %s, %s)
            on conflict (vaga_id) do update
               set status = excluded.status, nota = excluded.nota, atualizado_em = now()
            """,
            (vaga_id, status, nota),
        )
