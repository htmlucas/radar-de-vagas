import pandas as pd

from vagas import relatorios as r

AGORA = pd.Timestamp("2026-11-24 12:00", tz=r.FUSO)


def ts(dia: str):
    return pd.Timestamp(f"2026-11-{dia} 10:00", tz=r.FUSO)


def vaga(id, **kw):
    base = {"id": id, "fonte": "adzuna", "titulo": f"Vaga {id}", "empresa": "Acme", "nivel": "pleno",
            "modelo_trabalho": "remoto", "localizacao": None, "tecnologias": ["Laravel", "PHP"],
            "compatibilidade": 80, "status": "nova", "status_em": pd.NaT, "alvo": True,
            "publicada_em": ts("20"), "primeira_coleta": ts("20"), "nota": None}
    return base | kw


DF = pd.DataFrame([
    vaga("a", status="entrevista", status_em=ts("22")),
    vaga("b", status="candidatei", status_em=ts("10"), empresa="Beta"),
    vaga("c", status="candidatei", status_em=ts("21")),
    vaga("d", status="interessa", status_em=ts("19"), compatibilidade=90),
    vaga("e", status="recusado", status_em=ts("23")),
    vaga("f", compatibilidade=95, publicada_em=ts("23")),
    vaga("g", compatibilidade=40, alvo=False, fonte="glassdoor", tecnologias=["Java"]),
])
HIST = pd.DataFrame([
    {"vaga_id": "a", "status": "candidatei", "em": ts("15")},
    {"vaga_id": "a", "status": "entrevista", "em": ts("22")},
    {"vaga_id": "b", "status": "candidatei", "em": ts("10")},
    {"vaga_id": "c", "status": "candidatei", "em": ts("21")},
    {"vaga_id": "d", "status": "interessa", "em": ts("19")},
    {"vaga_id": "e", "status": "candidatei", "em": ts("12")},
    {"vaga_id": "e", "status": "recusado", "em": ts("23")},
])


def test_resumo_e_taxas():
    s = r.resumo_candidaturas(DF, HIST)
    assert s["candidaturas"] == 4          # a, b, c, e
    assert s["entrevistas"] == 1           # a
    assert s["recusados"] == 1             # e
    assert s["taxa_resposta"] == 0.5       # a e e responderam
    assert s["interessa"] == 1


def test_funil_conta_quem_passou_pela_etapa():
    f = r.funil(DF, HIST).set_index("etapa")["vagas"]
    assert list(f.index) == ["Interessei", "Me candidatei", "Entrevista", "Proposta"]
    assert f["Me candidatei"] == 4
    assert f["Entrevista"] == 1
    assert f["Interessei"] == 5  # quem se candidatou também "passou" por interesse


def test_aguardando_retorno_sugere_cobrar_depois_de_7_dias():
    a = r.aguardando_retorno(DF, HIST, AGORA).set_index("id")
    assert list(a.index) == ["b", "c"]  # mais antiga primeiro
    assert a.loc["b", "dias_sem_retorno"] == 14 and a.loc["b", "acao"].startswith("📞")
    assert a.loc["c", "acao"].startswith("⏳")


def test_tempo_ate_candidatar_e_esquecidas():
    assert r.tempo_ate_candidatar(DF, HIST) is not None
    esq = r.esquecidas(DF.assign(publicada_em=pd.Timestamp.now(tz=r.FUSO)))
    assert list(esq["id"]) == ["f"]  # nova, nota 95; a 'g' tem nota baixa


def test_tecnologias_e_situacao_no_perfil():
    t = r.tecnologias(DF, {"dominio": ["Laravel", "PHP"], "conhecimento": []}).set_index("tecnologia")
    assert t.loc["Laravel", "situacao"] == "Você domina"
    assert t.loc["Java", "situacao"] == "Não está no seu perfil"
    assert t.loc["Laravel", "vagas"] == 6


def test_filtro_por_alvo_e_periodo():
    f = r.filtrar(DF, dias=None, so_alvo=True, fontes=[], modelos=[])
    assert "g" not in set(f["id"])
    assert len(r.filtrar(DF, dias=None, so_alvo=False, fontes=["glassdoor"], modelos=[])) == 1


def test_por_fonte_e_empresas():
    pf = r.por_fonte(DF).set_index("fonte")
    assert pf.loc["adzuna", "no_alvo"] == 6 and pf.loc["glassdoor", "no_alvo"] == 0
    emp = r.empresas(DF).set_index("empresa")
    assert emp.loc["Acme", "sua_situacao"] == "entrevista"  # etapa mais avançada na empresa


def test_minhas_candidaturas_usa_a_primeira_data_de_candidatura():
    c = r.minhas_candidaturas(DF, HIST, AGORA).set_index("id")
    assert set(c.index) == {"a", "b", "c", "e"}  # interessa e nova ficam de fora
    assert c.loc["a", "status"] == "entrevista"
    assert c.loc["a", "candidatou_em"] == ts("15")  # não a data da entrevista
    assert c.loc["b", "dias_desde"] == 14


def test_descartadas_e_motivos():
    df = pd.DataFrame([
        vaga("x", status="descartada", status_em=ts("20"), motivo_descarte="Nível acima do meu (sênior/especialista)"),
        vaga("y", status="descartada", status_em=ts("21"), motivo_descarte="Nível acima do meu (sênior/especialista)"),
        vaga("z", status="descartada", status_em=ts("22")),  # descartada antes de existir o motivo
        vaga("w"),
    ])
    d = r.descartadas(df)
    assert list(d["id"]) == ["z", "y", "x"]  # mais recente primeiro
    m = r.motivos_descarte(d).set_index("motivo")["vagas"]
    assert m["Nível acima do meu (sênior/especialista)"] == 2 and m[r.SEM_MOTIVO] == 1


def test_faixas_de_nota_incluem_100():
    f = r.faixas_de_nota(pd.DataFrame({"compatibilidade": [100, 95, 10]})).set_index("faixa")["vagas"]
    assert f["90–99"] == 2 and f["10–19"] == 1
