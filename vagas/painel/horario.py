"""Quando a vaga entrou no radar (primeira coleta), no fuso do projeto. Usado pelos cards das duas trilhas.

Só lê `primeira_coleta`: nunca `publicada_em` (quando a vaga foi publicada) nem `ultima_coleta` (reatualizações).
"""

import pandas as pd

from vagas.relatorios import FUSO

SEM_HORARIO = "Adicionada ao radar: horário indisponível"


def adicionada_ao_radar(ts) -> str:
    """'Adicionada ao radar: 25/11/2026 às 20:34' (horário de São Paulo); sem registro, indica que não há, sem inventar data."""
    if ts is None or pd.isna(ts):
        return SEM_HORARIO
    ts = pd.Timestamp(ts)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    ts = ts.tz_convert(FUSO)
    return f"Adicionada ao radar: {ts:%d/%m/%Y} às {ts:%H:%M}"
