"""Etapa 2.1: testes das regras de cabeçalhos, seções, HTML, tecnologias, conceito de IA, títulos e senioridade.

(Os testes da etapa 2 continuam em test_dados_normalizar.py.)
"""

import pytest

from vagas.trilhas.dados.normalizar import (
    _cabecalho, classificar_cargo, detectar_conceitos, detectar_nivel, html_para_linhas, montar_vaga_dados,
    separar_requisitos,
)

OBRIGATORIOS_NOVOS = ["Requisitos e qualificações", "Requisitos mínimos", "Requisitos principais",
                      "Requisitos técnicos", "Qualifications", "Minimum qualifications", "Basic qualifications",
                      "Perfil desejado", "Perfil que buscamos", "Perfil buscado", "Habilidades"]
DESEJAVEIS_NOVOS = ["Requisitos desejáveis", "Diferencial", "Diferenciais", "Preferred experience",
                    "Preferred qualifications", "Nice to have", "Plus", "Bonus"]
STACK = ["Stack", "Stack principal", "Tecnologias", "Tecnologias e ambiente de desenvolvimento"]
ATIVIDADES = ["Responsabilidades", "Principais responsabilidades", "Atribuições", "O que você vai fazer",
              "O que você fará", "As principais atividades incluem", "Responsibilities", "What you'll do",
              "What you will do", "What you'd own"]
NEUTROS = ["Benefícios", "Sobre a empresa", "Nossa empresa", "Como se candidatar", "Labels", "Categoria",
           "Faixa salarial", "Contratação", "Regime", "Modalidade", "Nível", "Confirmações", "Company",
           "About the company", "Benefits", "Perks", "Salary range", "Contract type", "Work model", "How to apply",
           "Local", "Local de trabalho", "Localização", "Location", "Alocação", "Modelo de trabalho", "Modality",
           "Site da empresa", "Company website", "Nossa missão", "Level", "Type of contract", "Confirmations",
           "Regime de contratação", "Modalidade de contratação"]
CONTEINERES = ["Descrição da vaga", "Job Description", "About the job"]   # "About the job": acréscimo da calibração


# --------------------------------------------------------------------------- reconhecimento de cabeçalhos
@pytest.mark.parametrize("sufixo", ["", ":"])
@pytest.mark.parametrize("grupo, termos", [
    ("obrigatorio", OBRIGATORIOS_NOVOS), ("desejavel", DESEJAVEIS_NOVOS), ("stack", STACK),
    ("atividades", ATIVIDADES), ("neutro", NEUTROS), ("conteiner", CONTEINERES),
])
def test_cada_termo_novo_e_reconhecido_no_seu_grupo(grupo, termos, sufixo):
    for termo in termos:
        achado = _cabecalho(termo + sufixo)
        assert achado is not None and achado[0] == grupo, termo


@pytest.mark.parametrize("linha, grupo", [
    ("Diferenciais — nice to have", "desejavel"),
    ("🔎 Stack principal", "stack"),
    ("**Requisitos e qualificações**", "obrigatorio"),
    ("# Requisitos técnicos:", "obrigatorio"),
    ("Requisitos (obrigatórios)", "obrigatorio"),
    ("Benefícios 💎", "neutro"),
    ("## Descrição da vaga: ", "conteiner"),
    ("- Responsabilidades -", "atividades"),
    ("Requisitos | Python", "obrigatorio"),
    ("Requisitos / diferenciais", "obrigatorio"),
    ("What you’d own in the first 90 days", "atividades"),   # aspa tipográfica e continuação livre
    ("Perks that Acme offers!", None),                       # fora do vocabulário
    ("Requisitos para a vaga", None),
    ("Projeto A — Assistente", None),
])
def test_separadores_e_enfeites_nos_cabecalhos(linha, grupo):
    achado = _cabecalho(linha)
    assert (achado[0] if achado else None) == grupo


def test_cabecalho_com_mais_de_60_caracteres_nunca_vale():
    assert _cabecalho("Requisitos: " + "x" * 49) is None


def test_cabecalho_mais_longo_vence():
    assert _cabecalho("Requisitos desejáveis:")[0] == "desejavel"
    assert _cabecalho("Requisitos:")[0] == "obrigatorio"
    assert _cabecalho("Preferred qualifications")[0] == "desejavel"
    assert _cabecalho("Qualifications")[0] == "obrigatorio"


@pytest.mark.parametrize("linha, e_cabecalho", [
    ("Bônus:", True), ("Bonus", True), ("Plus:", True),
    ("- Bônus: até 2 salários", False), ("Bônus anual", False), ("Plus de 20% no salário", False),
])
def test_plus_e_bonus_so_valem_sozinhos(linha, e_cabecalho):
    assert (_cabecalho(linha) is not None) is e_cabecalho


def test_perfil_desejado_e_requisito_nao_diferencial():
    r = separar_requisitos("Perfil desejado:\n- Python e SQL\nDiferenciais:\n- Spark")
    assert r.obrigatorios == ["Python", "SQL"] and r.desejaveis == ["Spark"]


# --------------------------------------------------------------------------- seções neutras
def test_beneficios_nao_herdam_nem_contaminam():
    r = separar_requisitos("Requisitos:\n- SQL\nBenefícios:\n- Auxílio para estudar Python e Spark")
    assert r.obrigatorios == ["SQL"] and r.desejaveis == []
    assert "python" not in r.texto_relevante.lower() and r.cabecalhos_neutros == 1


def test_como_se_candidatar_interrompe_os_diferenciais():
    r = separar_requisitos("Diferenciais:\n- Spark\nComo se candidatar:\nEnvie o currículo (quem sabe Airflow ganha pontos)")
    assert r.desejaveis == ["Spark"]


def test_labels_do_template_nao_geram_nada():
    r = separar_requisitos("### Labels\nPython, Spark, Scala, MongoDB\n### Requisitos\n- SQL")
    assert r.obrigatorios == ["SQL"] and "spark" not in r.texto_relevante.lower()


# --------------------------------------------------------------------------- contêiner
def test_conteiner_nao_engole_o_conteudo_e_os_cabecalhos_internos_funcionam():
    texto = ("## Descrição da vaga\nVaga de pipelines de dados com Spark.\n"
             "Requisitos:\n- SQL\nDiferenciais:\n- dbt")
    r = separar_requisitos(texto)
    assert r.obrigatorios == ["SQL"] and r.desejaveis == ["dbt"]
    assert "spark" in r.texto_relevante.lower()          # conteúdo do contêiner continua disponível
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="Engenheiro de Dados Júnior", url="u", descricao=texto)
    assert v["tecnologias"] == ["SQL", "Spark", "dbt"] and "ETL / importação de dados" in v["conceitos"]
    assert "Spark" not in v["req_obrigatorios"] + v["req_desejaveis"]   # só menção


def test_about_the_job_depois_de_preferred_nao_herda_o_grupo_desejavel():   # caso real 12461
    r = separar_requisitos("Preferred qualifications:\n- Experience with Spark\nAbout the job\n"
                           "You will build data pipelines and ensure data quality.\nResponsibilities\n- Use Airflow")
    assert r.desejaveis == ["Spark"] and r.obrigatorios == [] and r.citados_em_atividades == ["Airflow"]
    assert "ETL / importação de dados" not in r.desejaveis      # a apresentação virou só menção
    assert "data pipelines" in r.texto_relevante


def test_job_description_em_ingles_tambem_e_conteiner():
    r = separar_requisitos("Job Description\nWe use Spark.\nRequirements\n- SQL")
    assert r.obrigatorios == ["SQL"] and "spark" in r.texto_relevante.lower()


# --------------------------------------------------------------------------- atividades
def test_atividades_nao_viram_requisito_quando_ha_grupo_explicito():
    r = separar_requisitos("Responsabilidades:\n- Construir jobs em Airflow\nRequisitos:\n- SQL")
    assert r.obrigatorios == ["SQL"] and r.citados_em_atividades == ["Airflow"] and r.desejaveis == []
    assert r.cabecalhos_atividades == 1


def test_atividades_viram_obrigatorias_sem_nenhum_grupo_de_requisitos():
    r = separar_requisitos("Responsabilidades:\n- Construir jobs em Airflow\n- Usar Python")
    assert r.obrigatorios == ["Python", "Airflow"] and r.citados_em_atividades == []


def test_item_em_atividades_e_em_requisitos_fica_so_como_obrigatorio():
    r = separar_requisitos("Responsabilidades:\n- Usar Spark\nRequisitos:\n- Spark")
    assert r.obrigatorios == ["Spark"] and r.citados_em_atividades == []


# --------------------------------------------------------------------------- stack
def test_stack_vale_como_obrigatorio_e_conta_como_grupo_explicito():
    r = separar_requisitos("Stack principal: Spark, Airflow\nDiferenciais:\n- dbt")
    assert r.obrigatorios == ["Spark", "Airflow"] and r.desejaveis == ["dbt"]
    assert r.cabecalhos_obrigatorios == 1 and r.tem_grupo_explicito


def test_so_stack_ja_e_grupo_explicito_e_desliga_o_fallback():
    r = separar_requisitos("Contexto: usamos Python no dia a dia.\nTecnologias:\n- SQL")
    assert r.obrigatorios == ["SQL"]       # "Python" antes do cabeçalho é só menção


def test_diferencial_no_singular_torna_os_itens_desejaveis():   # caso real 12481
    r = separar_requisitos("Requisitos:\n- Python\nDiferencial:\n- AWS\n- Lambda")
    assert r.obrigatorios == ["Python"] and r.desejaveis == ["AWS", "Lambda"]


# --------------------------------------------------------------------------- HTML
HTML_UMA_LINHA = ("<p>Role summary.</p><h3>Minimum qualifications:</h3><ul><li>Experience with Python and SQL.</li>"
                  "<li>Experience with Spark</li></ul><br><h3>Preferred qualifications:</h3>"
                  "<ul><li>Experience with Airflow.</li></ul><h3>Responsibilities:</h3><ul><li>Build dbt models</li></ul>")


def test_html_vira_uma_linha_por_bloco_na_ordem_original():
    linhas = [l.strip() for l in html_para_linhas(HTML_UMA_LINHA) if l.strip()]
    assert linhas[:3] == ["Role summary.", "Minimum qualifications:", "Experience with Python and SQL."]
    assert linhas.index("Preferred qualifications:") < linhas.index("Experience with Airflow.")


def test_html_de_uma_linha_so_tem_os_cabecalhos_reconhecidos():
    r = separar_requisitos(HTML_UMA_LINHA)
    assert r.obrigatorios == ["Python", "SQL", "Spark"] and r.desejaveis == ["Airflow"]
    assert r.citados_em_atividades == ["dbt"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis, r.cabecalhos_atividades) == (1, 1, 1)


def test_texto_sem_html_nao_e_alterado():
    assert html_para_linhas("a < b\nRequisitos: SQL") == ["a < b", "Requisitos: SQL"]
    assert html_para_linhas(None) == []


def test_tag_inline_nao_quebra_a_frase():
    r = separar_requisitos("<ul><li>Requisitos: <b>Python</b> e SQL</li></ul>")
    assert r.obrigatorios == ["Python", "SQL"] and r.cabecalhos_obrigatorios == 1


# --------------------------------------------------------------------------- montar_vaga_dados
def test_rotulos_do_github_nao_entram_nas_tecnologias_mas_definem_o_nivel():
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="Engenheiro de Dados", url="u",
                          descricao="Requisitos:\n- SQL", rotulos=["Python", "Spark", "Scala", "Júnior"])
    assert v["tecnologias"] == ["SQL"] and v["nivel"] == "junior"


def test_modalidade_continua_sendo_lida_em_secao_neutra():
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="Engenheiro de Dados", url="u",
                          descricao="Requisitos:\n- SQL\nModelo de trabalho:\nRemoto")
    assert v["modelo_trabalho"] == "remoto" and v["tecnologias"] == ["SQL"]


def test_classificacao_ignora_sinais_de_secoes_neutras():
    descricao = "Benefícios:\n- ETL, Spark e Airflow no wiki\nRequisitos:\n- SQL"
    assert montar_vaga_dados(fonte="x", id_externo="1", titulo="Desenvolvedor Python", url="u", descricao=descricao) is None


def test_atividades_ajudam_na_classificacao_sem_virar_requisito():
    descricao = "Responsabilidades:\n- ETL com Spark e Airflow\nRequisitos:\n- Python"
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="Desenvolvedor Python", url="u", descricao=descricao)
    assert v["categoria_cargo"] == "relacionada" and v["alvo"] is False
    assert v["req_obrigatorios"] == ["Python"]
    assert set(v["citados_em_atividades"]) == {"Spark", "Airflow", "ETL / importação de dados"}
    assert {"Spark", "Airflow"} <= set(v["tecnologias"])      # menções preservadas


# --------------------------------------------------------------------------- conceito "enriquecimento de dados com IA"
@pytest.mark.parametrize("texto", [
    "Enriquecimento de dados com IA", "Usar LLMs para classificar dados de clientes",
    "AI-powered data enrichment", "inteligência artificial aplicada a dados de vagas",
    "Utilizamos OpenAI para enriquecer os dados dos candidatos",
])
def test_conceito_de_ia_casa_quando_ha_dados_por_perto(texto):
    assert "enriquecimento de dados com IA" in detectar_conceitos(texto)


@pytest.mark.parametrize("texto", [
    "Experience integrating generative AI tools or LLM interfaces into workflows.",
    "Experiência com OpenAI", "DeepSeek", "LLM", "Integração de ferramentas de IA nos processos",
    "Usamos IA no atendimento.\nOs dados ficam no PostgreSQL.",                # IA e dados em frases diferentes
    "Machine learning, uma equipe muito grande de vendas internas e dados",    # mais de 4 palavras no meio
])
def test_conceito_de_ia_nao_casa_sem_contexto_de_dados(texto):
    assert "enriquecimento de dados com IA" not in detectar_conceitos(texto)


# --------------------------------------------------------------------------- títulos novos
@pytest.mark.parametrize("titulo, categoria", [
    ("ETL Developer", "dev_etl"), ("Senior ETL Developer", "dev_etl"),
    ("Data Platform Engineer", "engenharia_dados"), ("Data Platform Engineering Intern", "engenharia_dados"),
    ("Engenheiro de Plataforma de Dados", "engenharia_dados"),
    ("Engenheira de Plataforma de Dados Júnior", "engenharia_dados"),
    ("Engenheiro de Big Data", "engenharia_dados"), ("Engenheiro(a) de Big Data Jr", "engenharia_dados"),
])
def test_titulos_novos(titulo, categoria):
    assert classificar_cargo(titulo).categoria == categoria


def test_analista_etl_continua_fora_e_negativos_continuam_mandando():
    assert classificar_cargo("Analista ETL").categoria is None
    assert classificar_cargo("Cientista de Dados / Data Platform Engineer").categoria is None
    assert classificar_cargo("ETL Developer BI").categoria is None


# --------------------------------------------------------------------------- senioridade por qualificador
@pytest.mark.parametrize("titulo", [
    "Lead Data Engineer", "Staff Data Engineer", "Principal Data Engineer", "Engenheiro de Dados Lead",
    "Tech Lead de Dados", "Lead Database & Data Platform Engineer", "Engenheiro de Dados Staff",
    "Principal Software Engineer",
])
def test_lead_staff_principal_com_cargo_sao_senior(titulo):
    assert detectar_nivel(titulo) == "senior"


@pytest.mark.parametrize("titulo", [
    "Engenheiro de Dados - Projeto Principal", "Engenheiro de Dados (stack principal Spark)",
    "Engenheiro de Dados na Staffing", "Engenheiro de Dados no time Leading Edge",
])
def test_lead_staff_principal_soltos_nao_sao_senior(titulo):
    assert detectar_nivel(titulo) is None


def test_qualificador_senior_nao_vem_da_descricao():
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="Engenheiro de Dados", url="u",
                          descricao="Você falará com o tech lead e com a Principal Engineer do time.")
    assert v["nivel"] is None


def test_lead_data_platform_engineer_nao_e_alvo():
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="[Remoto] Lead Database & Data Platform Engineer (Acme)", url="u")
    assert (v["categoria_cargo"], v["nivel"], v["alvo"]) == ("engenharia_dados", "senior", False)


def test_dois_niveis_com_lead_continua_valendo_o_menor():
    assert detectar_nivel("Data Engineer Junior ou Lead Data Engineer") == "junior"
