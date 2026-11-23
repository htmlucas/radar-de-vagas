from vagas.curriculo.sugestoes import analisar, formatar, prompt_para_chat

BASE = {
    "contato": {"nome": "Pessoa Teste", "email": "pessoa@exemplo.com"},
    "resumo": "Desenvolvedor de software com experiência profissional desde 2021.",
    "experiencias": [
        {"id": "a", "empresa": "Empresa A", "cargo": "Dev Pleno", "atividades": [
            "Manutenção de telas administrativas.",
            "Processamento assíncrono com filas no AWS SQS.",
            "APIs REST em Laravel com PostgreSQL.",
        ]},
        {"id": "b", "empresa": "Empresa B", "cargo": "Dev Júnior", "atividades": [
            "Sistemas legados em PHP e MySQL.",
        ]},
    ],
    "projetos": [
        {"id": "p1", "nome": "Pipeline de Dados", "descricao": "ETL em Python com PostgreSQL."},
        {"id": "p2", "nome": "Jogo", "descricao": "Jogo da velha."},
    ],
    "competencias": {"Backend": ["PHP", "Laravel"]},
}

VAGA = {
    "titulo": "Desenvolvedor Backend Pleno",
    "descricao": "APIs REST com Laravel, filas e PostgreSQL. Desejável Kubernetes.",
    "tecnologias": ["Laravel", "PostgreSQL", "Filas", "Kubernetes"],
}


def test_ordena_atividades_pela_relevancia_para_a_vaga():
    a = analisar(VAGA, BASE)
    destaque = [atividade for atividade, _ in a["experiencias"][0]["destaque"]]
    assert destaque[0] == "APIs REST em Laravel com PostgreSQL."
    assert "Manutenção de telas administrativas." not in destaque


def test_separa_o_que_voce_comprova_do_que_falta():
    a = analisar(VAGA, BASE)
    assert "Laravel" in a["comprovadas"] and "PostgreSQL" in a["comprovadas"]
    assert a["lacunas"] == ["Kubernetes"]
    assert "APIs REST" in a["temas_comuns"]


def test_projeto_irrelevante_nao_e_sugerido():
    nomes = [p["nome"] for p in analisar(VAGA, BASE)["projetos"]]
    assert nomes == ["Pipeline de Dados"]


def test_titulo_e_resumo_usam_so_fatos_do_base():
    a = analisar(VAGA, BASE)
    assert a["titulo"] == "Desenvolvedor Backend PHP/Laravel"
    assert "desde 2021" in a["resumo"]
    assert "Kubernetes" not in a["resumo"]
    assert "APIs REST" in a["resumo"]  # sigla não pode virar "aPIs"


def test_descricao_colada_acrescenta_requisitos():
    a = analisar(VAGA | {"tecnologias": ["Laravel"], "descricao": ""}, BASE,
                 descricao_completa="Também usamos Redis e Docker.")
    assert {"Redis", "Docker"} <= set(a["lacunas"])
    assert a["usou_descricao_completa"]


def test_texto_formatado_tem_todas_as_secoes():
    texto = formatar(analisar(VAGA, BASE))
    for secao in ("Título sugerido", "Rascunho de resumo", "você comprova", "topo de cada experiência",
                  "Projetos para destacar", "não aparece no seu currículo"):
        assert secao in texto


def test_prompt_nao_inclui_contato():
    p = prompt_para_chat(VAGA, BASE)
    assert "pessoa@exemplo.com" not in p and "Pessoa Teste" not in p
    assert "Desejável Kubernetes" in p
