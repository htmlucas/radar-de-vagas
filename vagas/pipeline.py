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

        alvo = conn.execute("select count(*) as n from gold.vagas_alvo").fetchone()["n"]
    resumo["vagas_alvo"] = alvo
    return resumo


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for chave, valor in rodar().items():
        print(f"{chave:>12}: {valor}")
    sys.exit(0)
