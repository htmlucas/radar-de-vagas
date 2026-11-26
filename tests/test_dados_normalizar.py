"""Testes da classificação e normalização da trilha de Engenharia de Dados (etapa 2).

Só funções puras: sem banco, sem rede. Nada aqui toca na trilha Laravel.
"""

from pathlib import Path

import pytest
import yaml

from vagas.trilhas.dados import config as cfg
from vagas.trilhas.dados.normalizar import (
    classificar_cargo, contar_sinais_fortes, detectar_conceitos, detectar_nivel, detectar_tecnologias,
    e_alvo, montar_vaga_dados, separar_requisitos,
)

DESCRICAO_BACKEND = (
    "Procuramos pessoa desenvolvedora backend com Python e Django para construir APIs REST. "
    "Requisitos: Python, Django, SQL, Docker, testes automatizados e Git."
)


# --------------------------------------------------------------------------- categoria: títulos positivos
@pytest.mark.parametrize("titulo, categoria", [
    ("Engenheiro de Dados Júnior", "engenharia_dados"),
    ("Engenheira de Dados", "engenharia_dados"),
    ("Engenheiro(a) de Dados Jr", "engenharia_dados"),
    ("Engenharia de Dados - Estágio", "engenharia_dados"),
    ("[Remoto] Data Engineer Junior", "engenharia_dados"),
    ("Data Engineering Trainee", "engenharia_dados"),
    ("Big Data Engineer", "engenharia_dados"),
    ("Analytics Engineer Jr", "analytics_engineer"),
    ("Analytics Engineering", "analytics_engineer"),
    ("Desenvolvedor ETL", "dev_etl"),
    ("Desenvolvedora de ETL Júnior", "dev_etl"),
    ("Dev ETL", "dev_etl"),
    ("Dev. ETL Pleno", "dev_etl"),
    ("Desenvolvedor de Dados", "dev_etl"),
    ("Desenvolvedor(a) de Dados Júnior", "dev_etl"),
])
def test_titulos_positivos(titulo, categoria):
    r = classificar_cargo(titulo)
    assert r.categoria == categoria and r.motivo == "titulo_positivo"


def test_prioridade_entre_categorias_positivas():
    assert classificar_cargo("Desenvolvedor de Dados / Engenheiro de Dados").categoria == "engenharia_dados"


# --------------------------------------------------------------------------- categoria: títulos negativos
@pytest.mark.parametrize("titulo, motivo", [
    ("Cientista de Dados Júnior", "Cientista de Dados"),
    ("Data Scientist", "Cientista de Dados"),
    ("Analista de Dados Pleno", "Analista de Dados"),
    ("Data Analyst Junior", "Analista de Dados"),
    ("Desenvolvedor BI", "BI"),
    ("Analista de BI", "BI"),
    ("Business Intelligence Developer", "BI"),
    ("ML Engineer", "ML Engineer"),
    ("Machine Learning Engineer", "ML Engineer"),
    ("Engenheiro de Machine Learning", "ML Engineer"),
    ("DBA PostgreSQL", "DBA"),
    ("Administrador de Banco de Dados", "DBA"),
])
def test_titulos_negativos_ficam_fora(titulo, motivo):
    r = classificar_cargo(titulo)
    assert r.categoria is None and r.motivo == f"titulo_negativo:{motivo}"


def test_titulo_negativo_tem_prioridade_sobre_a_descricao_de_dados():
    descricao = "Pipelines de dados com Spark, Airflow, dbt, Databricks, ETL e data lake."
    assert len(contar_sinais_fortes("", descricao)) >= 3
    r = classificar_cargo("Cientista de Dados", descricao)
    assert r.categoria is None and r.motivo.startswith("titulo_negativo")


def test_titulo_negativo_vence_ate_titulo_positivo_no_mesmo_titulo():
    assert classificar_cargo("Engenheiro de Dados / Cientista de Dados").categoria is None


def test_power_bi_e_ferramenta_nao_cargo_de_bi():
    assert classificar_cargo("Engenheiro de Dados (SQL, Power BI)").categoria == "engenharia_dados"
    assert classificar_cargo("Desenvolvedor Power BI").categoria is None  # genérico sem sinais


def test_analista_etl_continua_fora_dos_cargos_alvo():
    assert classificar_cargo("Analista ETL Júnior").categoria is None
    com_sinais = "ETL, Spark, Airflow e data warehouse no dia a dia."
    r = classificar_cargo("Analista ETL Júnior", com_sinais)
    assert r.categoria == "relacionada" and not e_alvo(r.categoria, "junior")


# --------------------------------------------------------------------------- categoria: títulos genéricos
def test_titulo_generico_com_tres_sinais_fortes_vira_relacionada():
    descricao = "Atuação com Spark, Airflow e data lake em ambiente AWS."
    r = classificar_cargo("Desenvolvedor Python Júnior", descricao)
    assert r.categoria == "relacionada"
    assert set(r.sinais) == {"Spark", "Airflow", "Data Lake"}


def test_titulo_generico_com_dois_sinais_fica_fora():
    r = classificar_cargo("Desenvolvedor Python", "Experiência com Spark e Airflow.")
    assert r.categoria is None and r.motivo == "sinais_insuficientes:2"


def test_relacionada_nunca_e_alvo():
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="Desenvolvedor Python Júnior", url="u",
                          descricao="ETL, Spark e Airflow.")
    assert v["categoria_cargo"] == "relacionada" and v["nivel"] == "junior" and v["alvo"] is False


def test_backend_python_com_django_sql_e_apis_nao_e_engenharia_de_dados():
    r = classificar_cargo("Desenvolvedor Backend Python (Django, SQL, APIs)", DESCRICAO_BACKEND)
    assert r.categoria is None
    assert r.sinais == ()  # Python e SQL não são sinais fortes
    assert montar_vaga_dados(fonte="x", id_externo="1", titulo="Desenvolvedor Backend Python Júnior",
                             url="u", descricao=DESCRICAO_BACKEND) is None


def test_python_e_sql_sozinhos_nao_contam_como_sinal():
    assert contar_sinais_fortes("Python, SQL, PostgreSQL, Pandas e APIs") == []


# --------------------------------------------------------------------------- nível
@pytest.mark.parametrize("titulo, nivel", [
    ("Estágio em Engenharia de Dados", "estagio"),
    ("Estagiário de Dados", "estagio"),
    ("Data Engineer Intern", "estagio"),
    ("Data Engineering Internship", "estagio"),
    ("Trainee Engenharia de Dados", "trainee"),
    ("Engenheiro de Dados Júnior", "junior"),
    ("Engenheiro de Dados Jr.", "junior"),
    ("Junior Data Engineer", "junior"),
    ("Data Engineer Entry-Level", "junior"),
    ("Engenheiro de Dados Pleno", "pleno"),
    ("Engenheiro de Dados PL", "pleno"),
    ("Data Engineer Mid-Level", "pleno"),
    ("Engenheiro de Dados Sênior", "senior"),
    ("Senior Data Engineer", "senior"),
    ("Data Engineer Sr", "senior"),
    ("Engenheiro de Dados Especialista", "senior"),
    ("Engenheiro de Dados", None),
])
def test_niveis(titulo, nivel):
    assert detectar_nivel(titulo) == nivel


@pytest.mark.parametrize("titulo, nivel", [
    ("Engenheiro de Dados Júnior/Pleno", "junior"),
    ("Engenheiro de Dados Pleno/Sênior", "pleno"),
    ("Engenheiro de Dados Júnior ou Sênior", "junior"),
    ("Estágio / Trainee Engenharia de Dados", "estagio"),
    ("Trainee ou Júnior - Data Engineer", "trainee"),
])
def test_titulo_com_dois_niveis_vale_o_menor(titulo, nivel):
    assert detectar_nivel(titulo) == nivel


def test_nivel_usa_o_titulo_primeiro_e_depois_os_rotulos():
    assert detectar_nivel("Engenheiro de Dados", ["Júnior"]) == "junior"
    assert detectar_nivel("Engenheiro de Dados Sênior", ["Júnior"]) == "senior"  # título manda
    assert detectar_nivel("Engenheiro de Dados", ["remoto", "Estágio"]) == "estagio"
    assert detectar_nivel("Engenheiro de Dados", ["remoto"]) is None


def test_nivel_nao_usa_a_descricao():
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo="Engenheiro de Dados", url="u",
                          descricao="Você vai trabalhar com engenheiros sênior e pleno.")
    assert v["nivel"] is None


def test_pl_sql_nao_e_nivel_pleno():
    assert detectar_nivel("Engenheiro de Dados PL/SQL") is None


# --------------------------------------------------------------------------- alvo (categoria x nível)
@pytest.mark.parametrize("titulo, alvo", [
    ("Engenheiro de Dados Estágio", True),
    ("Engenheiro de Dados Trainee", True),
    ("Engenheiro de Dados Júnior", True),
    ("Engenheiro de Dados", True),                # nível não informado entra como "a confirmar"
    ("Analytics Engineer Jr", True),
    ("Desenvolvedor ETL Júnior", True),
    ("Engenheiro de Dados Pleno", False),
    ("Engenheiro de Dados Sênior", False),
    ("Analytics Engineer Pleno", False),
    ("Desenvolvedor ETL Sênior", False),
])
def test_regra_de_alvo(titulo, alvo):
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo=titulo, url="u")
    assert v is not None and v["alvo"] is alvo


def test_precisao_da_categoria_e_do_alvo_em_conjunto_misto():
    casos = [  # (título, descrição, categoria, alvo)
        ("Engenheiro de Dados Júnior", None, "engenharia_dados", True),
        ("Analytics Engineer Pleno", None, "analytics_engineer", False),
        ("Estágio Desenvolvedor ETL", None, "dev_etl", True),
        ("Desenvolvedor Python Jr", "ETL, Spark e Airflow", "relacionada", False),
        ("Desenvolvedor Backend Python Jr", DESCRICAO_BACKEND, None, False),
        ("Cientista de Dados Jr", "ETL, Spark e Airflow", None, False),
        ("Analista de Dados Jr", None, None, False),
        ("Desenvolvedor Laravel Pleno", "PHP, Laravel e MySQL", None, False),
    ]
    for titulo, descricao, categoria, alvo in casos:
        v = montar_vaga_dados(fonte="x", id_externo="1", titulo=titulo, url="u", descricao=descricao)
        assert (v["categoria_cargo"] if v else None) == categoria, titulo
        assert (v["alvo"] if v else False) is alvo, titulo


def test_e_alvo_direto():
    assert e_alvo("engenharia_dados", "junior") and e_alvo("dev_etl", None)
    assert not e_alvo("relacionada", "junior") and not e_alvo(None, "junior")
    assert not e_alvo("engenharia_dados", "pleno") and not e_alvo("engenharia_dados", "senior")


# --------------------------------------------------------------------------- tecnologias e conceitos
def test_tecnologias_de_dados_sao_detectadas():
    texto = ("Python, Pandas, SQL e PostgreSQL. Spark (PySpark) no Databricks, Airflow, dbt, Delta Lake. "
             "AWS: S3, Glue, Athena, Redshift e Lambda. Docker e Terraform.")
    achadas = set(detectar_tecnologias(texto))
    assert {"Python", "Pandas", "SQL", "PostgreSQL", "Spark", "Databricks", "Airflow", "dbt", "Delta Lake",
            "AWS", "S3", "Glue", "Athena", "Redshift", "Lambda", "Docker", "Terraform"} <= achadas


def test_sql_nao_casa_dentro_de_postgresql_mysql_ou_nosql():
    assert detectar_tecnologias("PostgreSQL") == ["PostgreSQL"]
    assert detectar_tecnologias("MySQL") == ["MySQL"]
    assert detectar_tecnologias("NoSQL") == ["NoSQL"]
    assert detectar_tecnologias("PL/SQL e T-SQL") == ["SQL"]


def test_aws_generica_e_servicos_especificos_sao_detectados_separadamente():
    assert detectar_tecnologias("Experiência com AWS") == ["AWS"]
    assert detectar_tecnologias("AWS (S3 e Glue)") == ["AWS", "S3", "Glue"]


def test_detecta_sem_acento_e_sem_diferenciar_maiusculas():
    assert detectar_tecnologias("EXPERIÊNCIA COM PYTHON E AIRFLOW") == ["Python", "Airflow"]


def test_conceitos_de_dados():
    texto = ("Construir pipelines de dados com ingestão de APIs externas, importações idempotentes e filas. "
             "Arquitetura Medallion (bronze, silver, gold), Parquet, Terraform, qualidade de dados, "
             "metadados de execução, CI/CD e testes automatizados.")
    achados = set(detectar_conceitos(texto))
    assert {"ETL / importação de dados", "integração de fontes externas", "importação idempotente",
            "processamento assíncrono e filas", "arquitetura Medallion", "organização de dados em camadas",
            "armazenamento colunar", "infraestrutura como código", "validação e qualidade de dados",
            "metadados e auditoria de execução", "testes e CI em pipeline de dados"} <= achados


def test_nomes_do_vocabulario_cobrem_o_perfil_aprovado():
    """Cada tecnologia e conceito de pontuacao_dados (curriculo_dados.yaml) existe no vocabulário.
    O YAML fica fora do Git: sem ele o teste é pulado. O módulo em si NÃO lê o YAML."""
    caminho = Path(__file__).resolve().parents[1] / "curriculo" / "base" / "curriculo_dados.yaml"
    if not caminho.exists():
        pytest.skip("curriculo_dados.yaml não existe nesta máquina")
    pont = yaml.safe_load(caminho.read_text(encoding="utf-8"))["pontuacao_dados"]
    faltam_tec = [t for t in pont["tecnologias"] if t not in cfg.TECNOLOGIAS]
    faltam_con = [c for c in pont["conceitos"] if c not in cfg.CONCEITOS]
    assert faltam_tec == [] and faltam_con == []


# --------------------------------------------------------------------------- requisitos: cabeçalhos
DESC_PT = """\
Somos uma empresa de dados.
Requisitos:
- Python e SQL
- Experiência com AWS
- Airflow
Diferenciais:
- Spark
- dbt
"""

DESC_EN = """\
About the role: build data pipelines.
Requirements
* Python and SQL
* Docker
Nice to have:
* Spark
* Terraform
"""


def test_cabecalhos_em_portugues():
    r = separar_requisitos(DESC_PT)
    assert r.obrigatorios == ["Python", "SQL", "Airflow", "AWS"]   # ordem do vocabulário
    assert r.desejaveis == ["Spark", "dbt"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis) == (1, 1)


def test_cabecalhos_em_ingles():
    r = separar_requisitos(DESC_EN)
    assert "Python" in r.obrigatorios and "SQL" in r.obrigatorios and "Docker" in r.obrigatorios
    assert r.desejaveis == ["Spark", "Terraform", "infraestrutura como código"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis) == (1, 1)


@pytest.mark.parametrize("linha, grupo", [
    ("Requisitos", "o"), ("REQUISITOS:", "o"), ("## Requisitos obrigatórios", "o"), ("**Requisitos:**", "o"),
    ("1. Pré-requisitos:", "o"), ("Pre requisitos", "o"), ("- Qualificações", "o"), ("O que esperamos:", "o"),
    ("Obrigatório:", "o"), ("Obrigatórios", "o"), ("Must have", "o"), ("Must-have:", "o"),
    ("Required:", "o"), ("Requirements:", "o"),
    ("Diferenciais", "d"), ("DIFERENCIAIS:", "d"), ("• Desejável", "d"), ("Desejáveis:", "d"),
    ("Será um diferencial", "d"), ("Nice to have", "d"), ("Nice-to-have:", "d"), ("Plus:", "d"),
    ("Bônus", "d"), ("Preferred", "d"),
])
def test_cabecalhos_reconhecidos(linha, grupo):
    texto = f"{linha}\nPython" if grupo == "o" else f"Python\n{linha}\nSpark"
    r = separar_requisitos(texto)
    if grupo == "o":
        assert r.cabecalhos_obrigatorios == 1 and r.cabecalhos_desejaveis == 0
    else:
        assert r.cabecalhos_desejaveis == 1 and r.cabecalhos_obrigatorios == 0
        # Etapa 2.1: com grupo explícito, o que vem antes do 1º cabeçalho é só menção (não é obrigatório).
        assert r.desejaveis == ["Spark"] and r.obrigatorios == []


@pytest.mark.parametrize("linha", [
    "Requisitos para a vaga",                    # depois do termo vem uma palavra solta, sem separador
    "Python é um requisito importante",          # não começa com o termo
    "Estes são os requisitos: " + "x" * 60,      # mais de 60 caracteres
    "Experiência desejável em Spark",            # termo no meio da linha
])
def test_linhas_que_nao_sao_cabecalho(linha):
    r = separar_requisitos(linha)
    assert r.cabecalhos_obrigatorios == 0 and r.cabecalhos_desejaveis == 0


def test_cabecalho_longo_demais_nao_vale():
    longo = "Requisitos: " + "a" * 49   # 61 caracteres
    assert len(longo) == 61
    assert separar_requisitos(longo + "\nSpark").cabecalhos_obrigatorios == 0
    curto = "Requisitos: " + "a" * 48   # 60 caracteres
    assert separar_requisitos(curto + "\nSpark").cabecalhos_obrigatorios == 1


def test_itens_na_mesma_linha_do_cabecalho():
    r = separar_requisitos("Requisitos: Python, SQL\nDiferenciais: Spark")
    assert r.obrigatorios == ["Python", "SQL"] and r.desejaveis == ["Spark"]


def test_descricao_sem_cabecalhos_tudo_obrigatorio():
    r = separar_requisitos("Vaga para trabalhar com Python, SQL e Spark em pipelines de dados.")
    assert r.obrigatorios == ["Python", "SQL", "Spark", "ETL / importação de dados"]
    assert r.desejaveis == []
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis) == (0, 0)


def test_descricao_com_somente_o_grupo_obrigatorio():
    r = separar_requisitos("Requisitos:\n- Python\n- SQL")
    assert r.obrigatorios == ["Python", "SQL"] and r.desejaveis == []
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis) == (1, 0)


def test_descricao_com_somente_o_grupo_desejavel():
    r = separar_requisitos("Diferenciais:\n- Spark\n- dbt")
    assert r.obrigatorios == [] and r.desejaveis == ["Spark", "dbt"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis) == (0, 1)


def test_itens_antes_do_primeiro_cabecalho_so_sao_obrigatorios_sem_grupo_explicito():
    # Etapa 2.1 (decisão aprovada): o fallback "tudo obrigatório" vale só sem nenhum grupo de requisitos.
    com_grupo = separar_requisitos("Trabalhamos com Airflow e Python.\nDiferenciais:\n- Spark")
    assert com_grupo.obrigatorios == [] and com_grupo.desejaveis == ["Spark"]
    assert "Airflow" in com_grupo.texto_relevante          # continua valendo como menção
    sem_grupo = separar_requisitos("Trabalhamos com Airflow e Python.")
    assert sem_grupo.obrigatorios == ["Python", "Airflow"]


def test_item_nos_dois_grupos_vale_o_obrigatorio():
    r = separar_requisitos("Requisitos:\n- Python\nDiferenciais:\n- Python avançado\n- Spark")
    assert r.obrigatorios == ["Python"] and r.desejaveis == ["Spark"]


def test_cada_item_herda_o_grupo_do_cabecalho_anterior_ate_o_proximo():
    texto = "Requisitos:\nSQL\nDiferenciais:\nSpark\nRequisitos:\nPython"
    r = separar_requisitos(texto)
    assert r.obrigatorios == ["Python", "SQL"] and r.desejaveis == ["Spark"]
    assert (r.cabecalhos_obrigatorios, r.cabecalhos_desejaveis) == (2, 1)


def test_conceitos_tambem_herdam_o_grupo():
    r = separar_requisitos("Requisitos:\n- Python\nDiferenciais:\n- Experiência com Medallion e Terraform")
    assert "arquitetura Medallion" in r.desejaveis and "Terraform" in r.desejaveis
    assert r.obrigatorios == ["Python"]


def test_descricao_vazia():
    assert separar_requisitos(None).obrigatorios == [] and separar_requisitos("").desejaveis == []


# --------------------------------------------------------------------------- montagem completa
def test_montar_vaga_dados_completa():
    v = montar_vaga_dados(
        fonte="adzuna", id_externo="42", titulo="[Remoto] Engenheiro de Dados Júnior", url="https://x.test/42",
        empresa=" Acme ", descricao=DESC_PT + "\nTrabalho 100% remoto.", localizacao="Brasil",
        publicada_em="2026-11-20T10:00:00Z", rotulos=["Júnior"])
    assert v["id"] == "adzuna:42" and v["empresa"] == "Acme"
    assert (v["categoria_cargo"], v["nivel"], v["modelo_trabalho"], v["alvo"]) == (
        "engenharia_dados", "junior", "remoto", True)
    assert v["req_obrigatorios"] == ["Python", "SQL", "Airflow", "AWS"] and v["req_desejaveis"] == ["Spark", "dbt"]
    assert {"Python", "Spark", "dbt", "AWS"} <= set(v["tecnologias"])
    assert v["chave_dedupe"] == "engenheirodedadosjunior|acme"   # tira o "[Remoto]" do começo, como na trilha Laravel


def test_montar_vaga_dados_fora_da_trilha_devolve_none():
    assert montar_vaga_dados(fonte="x", id_externo="1", titulo="Desenvolvedor PHP Laravel Pleno", url="u",
                             descricao="Laravel, PHP, MySQL") is None


def test_reaproveita_os_utilitarios_da_trilha_laravel_sem_copia():
    from vagas.tratamento import normalizar as laravel
    from vagas.trilhas.dados import normalizar as dados
    assert dados.sem_acento is laravel.sem_acento
    assert dados.chave_dedupe is laravel.chave_dedupe
    assert dados.detectar_modelo is laravel.detectar_modelo
