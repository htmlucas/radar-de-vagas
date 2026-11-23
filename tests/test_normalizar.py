from vagas.tratamento.normalizar import (
    chave_dedupe,
    detectar_modelo,
    detectar_nivel,
    detectar_tecnologias,
    montar_vaga,
)


def test_nivel_pelo_titulo():
    assert detectar_nivel("Desenvolvedor(a) Laravel Júnior") == "junior"
    assert detectar_nivel("Back-end Developer JR - PORT LOUIS") == "junior"
    assert detectar_nivel("Desenvolvedor PHP Pleno") == "pleno"
    assert detectar_nivel("Senior Laravel Developer + React") == "senior"
    assert detectar_nivel("Tech Lead PHP") == "senior"


def test_nivel_misto_fica_com_o_menor():
    # "Pleno/Sênior" aceita pleno, então não pode sumir do filtro júnior/pleno.
    assert detectar_nivel("Desenvolvedor Full Stack PHP/Python — Pleno/Sênior") == "pleno"
    assert detectar_nivel("Developer ASP.NET/C# Junior/Pleno") == "junior"


def test_nivel_pelos_rotulos_quando_titulo_nao_diz():
    assert detectar_nivel("Backend Developer", ["PJ", "Pleno", "Remoto"]) == "pleno"
    assert detectar_nivel("Backend Developer", ["Especialista"]) == "senior"
    assert detectar_nivel("Backend Developer", ["PHP"]) is None


def test_pl_sql_nao_vira_pleno():
    assert detectar_nivel("Analista PL/SQL") is None


def test_modelo_de_trabalho():
    assert detectar_modelo("[Remoto] Dev Laravel") == "remoto"
    assert detectar_modelo("Dev Laravel", ["Híbrido"]) == "hibrido"
    assert detectar_modelo("Dev Laravel", [], "Trabalho 100% home office") == "remoto"
    assert detectar_modelo("Dev", [], "Local: Remoto híbrido para Betópolis") == "hibrido"
    assert detectar_modelo("Dev Laravel") is None


def test_tecnologias():
    techs = detectar_tecnologias("Dev PHP", "Laravel 11, filas com Horizon, PostgreSQL e AWS SQS")
    assert {"PHP", "Laravel", "Filas", "PostgreSQL", "AWS", "SQS"} <= set(techs)
    assert "React" not in techs


def test_mesma_vaga_em_fontes_diferentes_tem_mesma_chave():
    a = chave_dedupe("[Remoto] Desenvolvedor Laravel Pleno", "Acme Ltda")
    b = chave_dedupe("Desenvolvedor  Laravel   Pleno", "ACME LTDA")
    assert a == b


def test_tecnologia_confirmada_pela_fonte_conta_mesmo_fora_do_trecho():
    v = montar_vaga(
        fonte="adzuna",
        id_externo="1",
        titulo="Desenvolvedor PHP - Recrutamento Aberto",
        url="https://exemplo/1",
        descricao="Desenvolvimento e manutenção de software em PHP...",
        tecnologias_confirmadas=["Laravel"],
    )
    assert v["cita_laravel"] is True
    assert v["tecnologias"].count("Laravel") == 1


def test_montar_vaga():
    v = montar_vaga(
        fonte="github",
        id_externo="42",
        titulo="[Remoto] Dev Laravel Pleno na Acme",
        url="https://exemplo/42",
        empresa="Acme",
        descricao="Laravel, MySQL e Docker",
    )
    assert v["id"] == "github:42"
    assert v["so_titulo"] is False  # padrão: fontes com descrição
    assert v["cita_laravel"] is True
    assert v["nivel"] == "pleno"
    assert v["modelo_trabalho"] == "remoto"
