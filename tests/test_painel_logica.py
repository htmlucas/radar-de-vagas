import pandas as pd

from vagas.painel import logica as L

AGORA = pd.Timestamp("2026-11-24 12:00", tz=L.FUSO)


def test_classificar_nota():
    assert L.classificar_nota(86) == ("Alta", "sucesso")
    assert L.classificar_nota(75) == ("Alta", "sucesso")
    assert L.classificar_nota(60) == ("Média", "atencao")
    assert L.classificar_nota(40) == ("Baixa", "erro")
    assert L.classificar_nota(None)[0] == "Sem nota"


def test_separar_motivos_da_nota():
    pos, aten = L.separar_motivos([
        "✅ Você domina: Laravel, MySQL", "➕ Você conhece: Vue", "🏠 Remoto",
        "⚠️ Vaga sênior", "❔ Nível não informado", "🚗 Híbrido fora da sua região",
    ])
    assert pos == ["Você domina: Laravel, MySQL", "Você conhece: Vue", "Remoto"]
    assert aten == ["Vaga sênior", "Nível não informado", "Híbrido fora da sua região"]
    assert L.separar_motivos(None) == ([], [])


def test_proxima_acao():
    assert L.proxima_acao("candidatei", 9) == ("Cobrar retorno do recrutador", "atencao")
    assert L.proxima_acao("candidatei", 5)[0] == "Aguardar retorno (2 dias para cobrar)"
    assert L.proxima_acao("candidatei", 6)[0] == "Aguardar retorno (1 dia para cobrar)"
    assert L.proxima_acao("proposta", 1)[1] == "sucesso"
    assert L.proxima_acao("nova", None) == ("", "neutro")


def _df():
    base = {"alvo": True, "publicada_em": AGORA - pd.Timedelta(days=2), "primeira_coleta": AGORA,
            "status": "nova", "modelo_trabalho": "remoto", "nivel": "pleno", "empresa": "Acme",
            "descricao": "", "tecnologias": ["Laravel", "PHP"], "fontes": ["adzuna"], "compatibilidade": 80}
    linhas = [
        base | {"id": "a", "titulo": "Dev Laravel"},
        base | {"id": "b", "titulo": "Dev PHP", "modelo_trabalho": None, "fontes": ["linkedin", "adzuna"]},
        base | {"id": "c", "titulo": "Dev Java", "alvo": False, "tecnologias": ["Java"], "compatibilidade": 40},
        base | {"id": "d", "titulo": "Dev React", "modelo_trabalho": "presencial", "status": "descartada",
                "tecnologias": ["React", "Laravel"], "empresa": "Beta", "compatibilidade": 90},
        base | {"id": "e", "titulo": "Antiga", "publicada_em": AGORA - pd.Timedelta(days=200)},
    ]
    return pd.DataFrame(linhas)


def test_filtros_combinados():
    df = _df()
    f = L.Filtros(modalidades=["remoto", L.SEM_MODALIDADE], status=["nova"])
    assert list(L.filtrar_vagas(df, f, AGORA)["id"]) == ["a", "b"]  # c fora do perfil, d descartada, e antiga
    f = L.Filtros(so_perfil=False, dias=None, tecnologias=["React"])
    assert list(L.filtrar_vagas(df, f, AGORA)["id"]) == ["d"]
    f = L.Filtros(fontes=["linkedin"])
    assert list(L.filtrar_vagas(df, f, AGORA)["id"]) == ["b"]
    f = L.Filtros(so_perfil=False, busca="java")
    assert list(L.filtrar_vagas(df, f, AGORA)["id"]) == ["c"]
    f = L.Filtros(busca="laravel")  # busca também nas tecnologias
    assert set(L.filtrar_vagas(df, f, AGORA)["id"]) == {"a", "b", "d"}


def test_filtro_por_dia_em_que_entrou_no_radar():
    df = _df()
    df.loc[df["id"] == "b", "primeira_coleta"] = AGORA - pd.Timedelta(days=1)
    hoje, ontem = AGORA.date(), (AGORA - pd.Timedelta(days=1)).date()
    f = L.Filtros(dias=None, dia=hoje)
    assert set(L.filtrar_vagas(df, f, AGORA)["id"]) == {"a", "d", "e"}
    f = L.Filtros(dias=None, dia=ontem)
    assert list(L.filtrar_vagas(df, f, AGORA)["id"]) == ["b"]


def test_dias_com_vagas_e_dia_padrao():
    df = _df()
    df.loc[df["id"] == "b", "primeira_coleta"] = AGORA - pd.Timedelta(days=1)
    hoje, ontem = AGORA.date(), (AGORA - pd.Timedelta(days=1)).date()
    assert L.dias_com_vagas(df) == [(hoje, 4), (ontem, 1)]
    assert L.dia_padrao(df, hoje) == hoje
    # Amanhã, antes da coleta: mostra o último dia em que houve vagas
    amanha = (AGORA + pd.Timedelta(days=1)).date()
    assert L.dia_padrao(df, amanha) == hoje
    assert L.dia_padrao(df.iloc[0:0], hoje) == hoje


def test_ordenar_e_contar_filtros():
    df = _df()
    assert list(L.ordenar(df, "compatibilidade")["id"])[0] == "d"
    assert list(L.ordenar(df, "empresa")["empresa"])[-1] == "Beta"
    padrao = L.Filtros()
    assert L.filtros_ativos(padrao, padrao) == 0
    assert L.filtros_ativos(L.Filtros(busca="x", fontes=["adzuna"]), padrao) == 2
