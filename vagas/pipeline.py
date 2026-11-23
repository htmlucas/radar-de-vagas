"""Roda a coleta completa: fontes -> bronze (arquivos) -> silver (Postgres).

Uso:  python -m vagas.pipeline
Cada fonte roda isolada: se uma falhar, as outras continuam, e o erro
fica registrado em silver.execucoes (o painel mostra).
"""

import logging
import sys

from vagas import db
from vagas.coleta import adzuna, github
from vagas.coleta.base import FonteIgnorada
from vagas.curriculo.base import CurriculoNaoEncontrado
from vagas.curriculo.base import carregar as carregar_curriculo
from vagas.pontuacao import nota

COLETORES = {
    github.FONTE: github.coletar,
    adzuna.FONTE: adzuna.coletar,
}

log = logging.getLogger("pipeline")


def rodar() -> dict:
    db.criar_esquema()
    resumo = {}
    with db.conectar() as conn:
        for fonte, coletar in COLETORES.items():
            execucao = db.registrar_inicio(conn, fonte)
            conn.commit()
            try:
                vagas, arquivos = coletar()
                novas = db.salvar_vagas(conn, vagas)
                db.registrar_fim(conn, execucao, coletadas=len(vagas), novas=novas, arquivo=";".join(arquivos))
                resumo[fonte] = f"{len(vagas)} coletadas, {novas} novas"
            except FonteIgnorada as e:
                conn.rollback()
                db.registrar_fim(conn, execucao, erro=f"ignorada: {e}")
                resumo[fonte] = f"ignorada ({e})"
            except Exception as e:  # uma fonte com problema não derruba as outras
                conn.rollback()
                log.exception("falha na fonte %s", fonte)
                db.registrar_fim(conn, execucao, erro=f"{type(e).__name__}: {e}")
                resumo[fonte] = f"ERRO: {e}"
            conn.commit()

        resumo["pontuacao"] = pontuar_tudo(conn)
        conn.commit()
        alvo = conn.execute("select count(*) as n from gold.vagas_alvo").fetchone()["n"]
    resumo["vagas_alvo"] = alvo
    return resumo


def pontuar_tudo(conn) -> str:
    """Recalcula a nota de todas as vagas (é barato e mantém tudo coerente
    quando você muda o perfil no currículo base)."""
    try:
        perfil = carregar_curriculo().get("pontuacao", {})
    except CurriculoNaoEncontrado as e:
        return f"ignorada ({e})"
    vagas = conn.execute(
        "select id, titulo, descricao, localizacao, nivel, modelo_trabalho, tecnologias from silver.vagas"
    ).fetchall()
    db.salvar_pontuacoes(conn, [(v["id"], *nota.calcular(v, perfil)) for v in vagas])
    return f"{len(vagas)} vagas pontuadas"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for chave, valor in rodar().items():
        print(f"{chave:>12}: {valor}")
    sys.exit(0)
