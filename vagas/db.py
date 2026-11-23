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
                -- Vagas de e-mail (sem data de publicação real): mantém a mais antiga já vista,
                -- para a data não "andar" a cada alerta repetido.
                publicada_em = case when excluded.so_titulo
                                    then least(silver.vagas.publicada_em, excluded.publicada_em)
                                    else excluded.publicada_em end,
                so_titulo = excluded.so_titulo,
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


def definir_status(vaga_id: str, status: str | None, motivo: str | None = None,
                   detalhe: str | None = None) -> None:
    """Muda o status (None = volta para 'nova') e registra a mudança no histórico.
    A observação (nota) da vaga é mantida. Motivo/detalhe só valem para 'descartada'
    (em qualquer outro status eles são limpos)."""
    if status != "descartada":
        motivo = detalhe = None
    detalhe = (detalhe or "").strip() or None
    with conectar() as conn:
        if status is None:
            conn.execute("delete from silver.vaga_status where vaga_id = %s", (vaga_id,))
        else:
            conn.execute(
                """
                insert into silver.vaga_status (vaga_id, status, motivo_descarte, detalhe_descarte)
                values (%s, %s, %s, %s)
                on conflict (vaga_id) do update
                   set status = excluded.status, motivo_descarte = excluded.motivo_descarte,
                       detalhe_descarte = excluded.detalhe_descarte, atualizado_em = now()
                """,
                (vaga_id, status, motivo, detalhe),
            )
        conn.execute(
            "insert into silver.vaga_status_historico (vaga_id, status, motivo) values (%s, %s, %s)",
            (vaga_id, status or "nova", motivo),
        )


def definir_motivo(vaga_id: str, motivo: str | None, detalhe: str | None) -> None:
    """Corrige o motivo/detalhe de uma vaga já descartada, sem mudar status nem data."""
    with conectar() as conn:
        conn.execute(
            "update silver.vaga_status set motivo_descarte = %s, detalhe_descarte = %s "
            "where vaga_id = %s and status = 'descartada'",
            (motivo, (detalhe or "").strip() or None, vaga_id),
        )


def definir_nota(vaga_id: str, nota: str) -> None:
    """Observação livre sobre a vaga (ex.: 'falei com a recrutadora em 25/11')."""
    with conectar() as conn:
        conn.execute("update silver.vaga_status set nota = %s where vaga_id = %s", (nota.strip() or None, vaga_id))


def carregar_historico() -> list[dict]:
    with conectar() as conn:
        return conn.execute("select vaga_id, status, em from silver.vaga_status_historico order by em").fetchall()


def carregar_execucoes() -> list[dict]:
    with conectar() as conn:
        return conn.execute(
            "select fonte, iniciada_em, finalizada_em, qtd_coletada, qtd_nova, erro "
            "from silver.execucoes order by iniciada_em desc limit 200"
        ).fetchall()
