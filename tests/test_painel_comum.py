import pandas as pd

from vagas.painel.comum import FUSO, quando

AGORA = pd.Timestamp("2026-11-23 18:00", tz=FUSO)


def test_quando_mostra_data_e_tempo_relativo():
    assert quando(pd.Timestamp("2026-11-23 08:00", tz=FUSO), AGORA) == "23/11 (hoje)"
    assert quando(pd.Timestamp("2026-11-22 23:00", tz=FUSO), AGORA) == "22/11 (ontem)"
    assert quando(pd.Timestamp("2026-11-15 10:00", tz=FUSO), AGORA) == "15/11 (há 8 dias)"


def test_quando_mostra_o_ano_so_se_for_outro():
    assert quando(pd.Timestamp("2025-12-30 10:00", tz=FUSO), AGORA).startswith("30/12/2025")


def test_quando_sem_data():
    assert quando(pd.NaT, AGORA) == "sem data"
    assert quando(None, AGORA) == "sem data"
