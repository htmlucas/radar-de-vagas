"""Etapa 2.1: fixtures anonimizadas que reproduzem a ESTRUTURA de vagas reais (textos sintéticos,
sem empresas, URLs ou e-mails reais), com o resultado exato esperado da separação de requisitos."""

from pathlib import Path

from vagas.trilhas.dados.normalizar import montar_vaga_dados, separar_requisitos

FIXTURES = Path(__file__).parent / "fixtures" / "dados"


def ler(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


def montar(nome, titulo, rotulos=None):
    return montar_vaga_dados(fonte="github", id_externo=nome, titulo=titulo, url="https://exemplo.test",
                             descricao=ler(nome), rotulos=rotulos)


def test_template_portugues_do_backend_br():
    descricao = ler("backendbr_template_pt.md")
    r = separar_requisitos(descricao)
    assert r.obrigatorios == ["Python", "SQL", "AWS", "S3"]
    assert r.desejaveis == ["Spark", "dbt"]
    assert r.citados_em_atividades == ["Airflow"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis, r.cabecalhos_atividades, r.cabecalhos_neutros) == (1, 1, 1, 9)

    v = montar("backendbr_template_pt.md", "[Remoto] Engenheiro de Dados Júnior - Empresa Exemplo",
               rotulos=["Júnior", "Python", "Spark"])
    assert (v["categoria_cargo"], v["nivel"], v["modelo_trabalho"], v["alvo"]) == ("engenharia_dados", "junior", "remoto", True)
    # Java, Go, Databricks e Terraform só aparecem em seções neutras; Scala, Hadoop e MongoDB só nos Labels.
    assert v["tecnologias"] == ["Python", "SQL", "Spark", "Airflow", "dbt", "AWS", "S3"]
    assert v["conceitos"] == ["ETL / importação de dados"]


def test_html_do_google_em_ingles_numa_linha_so():
    descricao = ler("google_html_en.html")
    assert "\n" not in descricao.strip()
    r = separar_requisitos(descricao)
    assert r.obrigatorios == ["Python", "Spark", "Hadoop"]
    assert r.desejaveis == []
    assert r.citados_em_atividades == ["ETL / importação de dados"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis, r.cabecalhos_atividades) == (1, 1, 1)

    v = montar("google_html_en.html", "[Cidade Exemplo] Data Engineer, Marketing na Empresa Exemplo",
               rotulos=["JavaScript", "Python", "Java", "Go", "MongoDB", "C++"])
    assert (v["categoria_cargo"], v["nivel"], v["alvo"]) == ("engenharia_dados", None, True)
    assert v["tecnologias"] == ["Python", "Spark", "Hadoop"]
    # "generative AI tools or LLM interfaces" e "data mining, or machine learning" não são enriquecimento de dados com IA.
    assert v["conceitos"] == ["ETL / importação de dados"]


def test_atividades_e_stack():
    r = separar_requisitos(ler("atividades_e_stack.md"))
    assert r.obrigatorios == ["SQL", "Spark", "Databricks", "validação e qualidade de dados"]
    assert r.desejaveis == ["Terraform", "infraestrutura como código"]
    assert r.citados_em_atividades == ["Airflow", "dbt"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis, r.cabecalhos_atividades) == (2, 1, 1)
    v = montar("atividades_e_stack.md", "Analytics Engineer Jr")
    assert (v["categoria_cargo"], v["nivel"], v["alvo"]) == ("analytics_engineer", "junior", True)


def test_diferencial_no_singular_caso_real_12481():
    r = separar_requisitos(ler("diferencial_singular.md"))
    assert r.obrigatorios == ["Python", "PostgreSQL"]
    assert r.desejaveis == ["AWS", "Lambda"]
    assert r.citados_em_atividades == ["Airflow"]
    v = montar("diferencial_singular.md", "Data Engineer")
    assert "Docker" not in v["tecnologias"]        # só aparece em Benefícios
    assert "Terraform" not in v["tecnologias"]     # só aparece em Como se candidatar


def test_requisitos_e_diferenciais_misturados_caso_real_12493():
    r = separar_requisitos(ler("misturado_pt.md"))
    assert r.obrigatorios == ["Python", "SQL", "Spark", "Airflow", "Docker", "CI/CD", "testes e CI em pipeline de dados"]
    assert r.desejaveis == ["Terraform", "infraestrutura como código"]
    assert r.citados_em_atividades == ["PostgreSQL"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis, r.cabecalhos_atividades, r.cabecalhos_neutros) == (5, 1, 1, 5)
    v = montar("misturado_pt.md", "[Remoto] Engenheiro de Dados Júnior")
    assert "dbt" not in v["tecnologias"]           # só aparece em Benefícios
    assert v["tecnologias"] == ["Python", "SQL", "PostgreSQL", "Spark", "Airflow", "Docker", "Terraform", "CI/CD"]
