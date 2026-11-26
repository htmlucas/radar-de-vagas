"""Combinação dos dois currículos (sem mutação) e sugestões de currículo da trilha de Engenharia de Dados."""

import copy
from pathlib import Path

import pytest

from tests.dados_painel_simulado import BASE, DADOS, linha
from vagas.curriculo import base as carregador
from vagas.trilhas.dados import sugestoes
from vagas.trilhas.dados.curriculo import CAMINHO_DADOS, OrigemNaoEncontrada, carregar_combinado, combinar


def comb():
    return combinar(BASE, DADOS)


# =========================================================================== combinação
def test_combinar_nao_altera_os_dois_arquivos_nem_compartilha_objetos():
    base0, dados0 = copy.deepcopy(BASE), copy.deepcopy(DADOS)
    resultado = combinar(BASE, DADOS)
    assert BASE == base0 and DADOS == dados0
    # mexer no resultado também não pode mexer nas entradas (sem listas ou dicionários compartilhados)
    resultado["profissional"][0]["atividades"].append("ALTERADO")
    resultado["pontuacao_dados"]["tecnologias"]["SQL"]["nivel"] = "nenhuma"
    resultado["estudos"].append("X")
    assert BASE == base0 and DADOS == dados0


def test_combinar_traz_cargo_periodo_e_atividades_da_origem_e_os_complementos_do_perfil():
    acme = comb()["profissional"][0]
    assert (acme["empresa"], acme["cargo"]) == ("Acme Dados", "Desenvolvedor Full Stack Pleno (Freelancer)")
    assert acme["periodo"] == "Maio/2024 – Setembro/2025" and len(acme["atividades"]) == 3
    assert acme["complementos"] == ["Enriquecimento de dados em processos de habilidades."]
    assert [b["base"] for b in acme["bases_importadas"]] == ["CBO", "Receita Federal"]


def test_projeto_do_original_nao_herda_a_descricao_que_mistura_laboratorio():
    occ = next(p for p in comb()["projetos"] if p["id"] == "catalog")
    assert occ["descricao"] is None and occ["link"] == "github.com/exemplo/catalog" and occ["visibilidade"] == "publico"
    assert "Databricks" not in " ".join(occ["destaques"]) and occ["nao_usar_da_origem"] == ["Databricks"]


def test_projeto_local_nao_publicado_nao_tem_link_e_laboratorio_fica_separado():
    c = comb()
    radar = next(p for p in c["projetos"] if p["id"] == "radar_vagas")
    assert radar["link"] == "" and radar["visibilidade"] == "nao_publicado"
    assert [l["id"] for l in c["laboratorios"]] == ["databricks_medallion"] and "databricks_medallion" not in [p["id"] for p in c["projetos"]]
    assert c["entidades"]["databricks_medallion"]["tipo"] == "Laboratório" and c["entidades"]["acme"]["tipo"] == "Experiência profissional"


def test_formacao_e_cursos_combinam_origem_e_complemento():
    c = comb()
    pos = c["formacao"][0]
    assert (pos["instituicao"], pos["status"], pos["inicio"], pos["previsao_termino"]) == ("Universidade Exemplo", "em andamento", "2026-08", None)
    assert c["cursos"][0]["tipo"] == "curso" and c["cursos"][0]["nome"].startswith("AWS Cloud Practitioner Essentials")


@pytest.mark.parametrize("quebra, mensagem", [
    (lambda d: d["experiencia_profissional"].append({"origem_id": "nao_existe"}), "nao_existe"),
    (lambda d: d["projetos_pessoais"].append({"origem_id": "fantasma"}), "fantasma"),
    (lambda d: d["formacao"].append({"origem_curso": "Curso Inexistente"}), "Curso Inexistente"),
    (lambda d: d["cursos"].append({"origem_curso": "Certificação Falsa"}), "Certificação Falsa"),
    (lambda d: d["pontuacao_dados"]["tecnologias"].__setitem__("Kafka", {"nivel": "profissional", "origem": ["nunca_existiu"]}), "nunca_existiu"),
    (lambda d: d["pontuacao_dados"]["conceitos"]["ETL / importação de dados"].__setitem__("origem", ["radar_fantasma"]), "radar_fantasma"),
])
def test_origem_inexistente_e_erro_explicito(quebra, mensagem):
    dados = copy.deepcopy(DADOS)
    quebra(dados)
    with pytest.raises(OrigemNaoEncontrada, match=mensagem):
        combinar(BASE, dados)


def test_ids_locais_do_arquivo_de_dados_sao_aceitos_como_origem():
    # radar_vagas e databricks_medallion só existem no curriculo_dados.yaml: não são procurados no original
    c = comb()
    assert "radar_vagas" in c["entidades"] and "radar_vagas" not in [e["id"] for e in BASE["experiencias"] + BASE["projetos"]]


def test_carregar_combinado_usa_o_carregador_compartilhado_sem_alterar_o_cache():
    if not CAMINHO_DADOS.exists():
        pytest.skip("curriculo_dados.yaml não existe nesta máquina")
    antes_base, antes_dados = copy.deepcopy(carregador.carregar()), copy.deepcopy(carregador.carregar(CAMINHO_DADOS))
    c = carregar_combinado()
    c["profissional"][0]["atividades"].append("ALTERADO")
    c["pontuacao_dados"]["tecnologias"]["SQL"]["nivel"] = "nenhuma"
    assert carregador.carregar() == antes_base and carregador.carregar(CAMINHO_DADOS) == antes_dados


def test_curriculo_laravel_e_o_perfil_laravel_nao_mudam():
    """O carregador devolve o objeto em cache que a trilha Laravel usa: a combinação não pode tê-lo alterado."""
    if not Path(carregador.CAMINHO_BASE).exists():
        pytest.skip("curriculo.yaml não existe nesta máquina")
    antes = copy.deepcopy(carregador.carregar())
    carregar_combinado() if CAMINHO_DADOS.exists() else combinar(BASE, DADOS)
    assert carregador.carregar() == antes and "pontuacao" in carregador.carregar()


# =========================================================================== sugestões
def vaga(**kw):
    return linha("github:S", "[Remoto] Engenheiro de Dados Júnior", **{
        "tecnologias": ("Python", "SQL", "S3", "Glue", "Airflow", "Spark", "dbt", "Terraform"),
        "obrigatorios": ("Python", "SQL", "S3", "Glue", "Airflow"), "desejaveis": ("Spark", "dbt", "Terraform"), **kw})


def por_nome(analise):
    return {r["nome"]: r for r in analise["requisitos"]}


def test_cada_requisito_sai_com_o_nivel_da_evidencia():
    r = por_nome(sugestoes.analisar(vaga(), comb()))
    assert r["SQL"]["nivel"] == "profissional" and r["S3"]["nivel"] == "profissional"
    assert r["Python"]["nivel"] == "projeto"                      # Python nunca é profissional
    assert r["Spark"]["nivel"] == "laboratorio" and r["Terraform"]["nivel"] == "projeto"
    assert r["Airflow"]["nivel"] == "estudo" and r["dbt"]["nivel"] == "estudo"
    assert r["Glue"]["nivel"] == "nenhuma"
    assert (r["SQL"]["grupo"], r["Spark"]["grupo"]) == ("obrigatorio", "desejavel")


def test_lacunas_e_estudos_nao_viram_experiencia():
    a = sugestoes.analisar(vaga(), comb())
    assert a["lacunas_obrigatorias"] == ["Glue"] and a["em_estudo"] == ["Airflow", "dbt"]
    assert "Glue" not in sum(a["comprovados"].values(), []) and "Airflow" not in sum(a["comprovados"].values(), [])
    assert any("Não escreva como experiência" in x for x in a["avisos"]) and any("em estudo" in x.lower() for x in a["avisos"])


def test_projeto_pessoal_e_laboratorio_ficam_separados_da_experiencia_profissional():
    a = sugestoes.analisar(vaga(), comb())
    assert {"Experiência profissional", "Projeto pessoal", "Laboratório"} == {k for k, v in a["destaques"].items() if v}
    assert [e["empresa"] for e in a["experiencias"]] == ["Acme Dados", "Beta Sistemas"]
    assert {o["tipo"] for o in a["outros"]} == {"Projeto pessoal", "Laboratório"}
    lab = next(o for o in a["outros"] if o["tipo"] == "Laboratório")
    occ = next(o for o in a["outros"] if o["nome"] == "Catalog Data Pipeline")
    assert "laboratório, ambiente de estudo" in lab["texto"] and "Databricks" not in occ["texto"]      # sem misturar
    assert "projeto pessoal" in occ["texto"] and "publicado no GitHub: github.com/exemplo/catalog" in occ["texto"]


def test_projeto_nao_publicado_nunca_recebe_link():
    a = sugestoes.analisar(vaga(), comb())
    radar = next(o for o in a["outros"] if o["nome"] == "Radar de Vagas")
    assert "não publicado" in radar["texto"] and "github" not in radar["texto"].lower() and "http" not in radar["texto"]


def test_nunca_apresenta_o_usuario_como_engenheiro_de_dados_profissional():
    a = sugestoes.analisar(vaga(), comb())
    texto = sugestoes.formatar(a, vaga())
    assert "Engenheiro de Dados" not in a["titulo"] and "Engenheiro de Dados" not in a["resumo"]
    assert "pós-graduação em andamento" in a["titulo"]
    assert "Você não tem cargo formal de Engenheiro de Dados" in texto
    corpo = texto.split("## O que a vaga pede", 1)[1]
    assert "experiência profissional como Engenheiro" not in corpo and "Engenheiro de Dados (experiência" not in corpo


def test_volumes_da_acme_sao_aproximados_e_por_base_e_sem_numero_quando_nao_informado():
    acme = next(e for e in sugestoes.analisar(vaga(), comb())["experiencias"] if e["empresa"] == "Acme Dados")
    assert "CBO (≈2.700 ocupações)" in acme["bases"] and "Receita Federal" in acme["bases"] and "Receita Federal (" not in acme["bases"]
    assert "Volumes aproximados de cada base, não de todos os processos" in acme["bases"]


def test_aws_generica_nao_se_confunde_com_o_ecossistema_inteiro():
    a = sugestoes.analisar(vaga(tecnologias=("AWS",), obrigatorios=("AWS",), desejaveis=()), comb())
    r = por_nome(a)["AWS"]
    assert r["nivel"] == "aws_generica" and "S3, SQS e Lambda" in r["rotulo"] and "não com todo o ecossistema" in r["rotulo"]
    com_servico = sugestoes.analisar(vaga(tecnologias=("AWS", "Glue"), obrigatorios=("AWS", "Glue"), desejaveis=()), comb())
    assert "AWS" not in por_nome(com_servico) and por_nome(com_servico)["Glue"]["nivel"] == "nenhuma"      # serviço específico vence


def test_tecnologia_fora_do_perfil_e_lacuna_e_nada_e_inventado():
    a = sugestoes.analisar(vaga(tecnologias=("Kafka",), obrigatorios=("Kafka",), desejaveis=()), comb())
    assert por_nome(a)["Kafka"]["nivel"] == "nenhuma" and a["lacunas_obrigatorias"] == ["Kafka"]
    texto = sugestoes.formatar(a)
    assert "Kafka (obrigatório): sem evidência no perfil" in texto and "Kafka" not in a["resumo"] and a["comprovados"] == {}


def test_citado_so_em_atividades_aparece_como_tal_e_nao_como_requisito():
    a = sugestoes.analisar(vaga(tecnologias=("Python", "Spark"), obrigatorios=("Python",), desejaveis=(), atividades=("Spark",)), comb())
    assert por_nome(a)["Spark"]["grupo"] == "atividade" and por_nome(a)["Spark"]["rotulo_grupo"] == "Citado só em atividades"


def test_descricao_completa_colada_refaz_a_leitura_dos_requisitos():
    base = sugestoes.analisar(vaga(tecnologias=("Python",), obrigatorios=("Python",), desejaveis=()), comb())
    assert "Terraform" not in por_nome(base) and not base["usou_descricao_completa"]
    colada = "Requisitos:\n- Python e SQL\nDiferenciais:\n- Terraform e Glue"
    a = sugestoes.analisar(vaga(tecnologias=("Python",), obrigatorios=("Python",), desejaveis=()), comb(), colada)
    r = por_nome(a)
    assert a["usou_descricao_completa"] and r["Terraform"]["grupo"] == "desejavel" and r["Glue"]["nivel"] == "nenhuma" and r["SQL"]["grupo"] == "obrigatorio"


def test_atividades_sugeridas_vem_do_proprio_curriculo():
    a = sugestoes.analisar(vaga(), comb())
    todas = {t for e in a["experiencias"] for t, _ in e["atividades"]}
    permitido = {t for e in BASE["experiencias"] for t in e["atividades"]} | {t for e in DADOS["experiencia_profissional"] for t in e.get("complementos", [])}
    assert todas and todas <= permitido                     # nenhuma atividade inventada
    assert sugestoes.MAX_ATIVIDADES >= max(len(e["atividades"]) for e in a["experiencias"])


def test_formatar_gera_texto_completo_com_formacao_e_curso_que_nao_e_certificacao():
    texto = sugestoes.formatar(sugestoes.analisar(vaga(), comb()), vaga())
    for esperado in ("## Título sugerido", "## Resumo sugerido", "## Experiência profissional para destacar", "## Projeto pessoal para destacar",
                     "## Laboratório para destacar", "## Em estudo (sem experiência prática)", "## Formação e cursos", "## Lacunas e cuidados",
                     "Pós-graduação em Engenharia de Dados — Universidade Exemplo (em andamento desde 08/2026)",
                     "AWS Cloud Practitioner Essentials (curso) (concluído; curso, não é a certificação)"):
        assert esperado in texto, esperado


def test_vaga_sem_tecnologias_gera_aviso_sem_quebrar():
    a = sugestoes.analisar(linha("github:Z", "Engenheiro de Dados", tecnologias=(), obrigatorios=()), comb())
    assert a["requisitos"] == [] and a["lacunas_obrigatorias"] == [] and "Nenhuma tecnologia identificada" in sugestoes.formatar(a)


def test_sugestoes_com_os_arquivos_reais_se_existirem():
    if not CAMINHO_DADOS.exists():
        pytest.skip("curriculo_dados.yaml não existe nesta máquina")
    a = sugestoes.analisar(vaga(), carregar_combinado())
    r = por_nome(a)
    assert r["Python"]["nivel"] == "projeto" and r["Spark"]["nivel"] == "laboratorio" and r["Glue"]["nivel"] == "nenhuma" and r["Airflow"]["nivel"] == "estudo"
    texto = sugestoes.formatar(a)
    assert "Engenheiro de Dados" not in a["titulo"] and "curso, não é a certificação" in texto
    radar = next(o for o in a["outros"] if o["nome"] == "Radar de Vagas")
    assert "não publicado" in radar["texto"] and "http" not in radar["texto"]
