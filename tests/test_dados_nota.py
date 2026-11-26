"""Etapa 3: nota, confiança, elegibilidade e alertas da trilha de Engenharia de Dados.

As vagas são montadas pelo normalizador real (montar_vaga_dados); o perfil abaixo espelha a seção
pontuacao_dados de curriculo/base/curriculo_dados.yaml (que fica fora do Git).
"""

from pathlib import Path

import pytest

from vagas.trilhas.dados.nota import (
    MSG_ESTAGIO_GRADUACAO, MSG_FORA_DO_BRASIL, anos_de_experiencia_exigidos, calcular, carregar_perfil,
    exige_ingles_avancado, faixa_da_nota,
)
from vagas.trilhas.dados.normalizar import montar_vaga_dados

PROF, PROJ, LAB, EST, NEN = "profissional", "projeto", "laboratorio", "estudo", "nenhuma"


def _t(nivel, *nomes):
    return {n: {"nivel": nivel} for n in nomes}


PERFIL = {
    "pesos_evidencia": {PROF: 1.0, PROJ: 0.8, LAB: 0.6, EST: 0.3, NEN: 0.0},
    "aws_generica": 0.8,
    "tecnologias": {
        **_t(PROF, "SQL", "PostgreSQL", "MySQL", "S3", "SQS", "Lambda", "Docker", "CI/CD", "Testes"),
        **_t(PROJ, "Python", "Pandas", "Parquet", "Snappy", "Terraform", "GitHub Actions", "Docker Compose"),
        **_t(LAB, "Databricks", "Spark"), **_t(EST, "Airflow", "dbt"),
        **_t(NEN, "Delta Lake", "Glue", "Athena", "Redshift"),
    },
    "conceitos": {
        **_t(PROF, "integração de fontes externas", "ETL / importação de dados", "importação idempotente",
             "processamento assíncrono e filas", "modelagem e consultas relacionais", "enriquecimento de dados com IA"),
        **_t(PROJ, "organização de dados em camadas", "armazenamento colunar", "infraestrutura como código",
             "metadados e auditoria de execução", "testes e CI em pipeline de dados"),
        **_t(LAB, "arquitetura Medallion", "validação e qualidade de dados"),
    },
}
FORMACAO_SEM_CONCLUSAO = [{"origem_curso": "Pós-graduação em Engenharia de Dados", "inicio": "2026-08"},
                          {"origem_curso": "Tecnólogo em ADS", "conclusao": None}]


def vaga(titulo, descricao=None, **kw):
    v = montar_vaga_dados(fonte="x", id_externo="1", titulo=titulo, url="u", descricao=descricao, **kw)
    assert v is not None, titulo
    return v


def pontos(av):
    return {p.nome: p.pontos for p in av.parcelas}


def confere(av, **esperado):
    obtido = pontos(av)
    for nome, valor in esperado.items():
        assert obtido[nome] == pytest.approx(valor, abs=0.01), (nome, obtido)


DESC_A = """\
Vaga remota para pessoa engenheira de dados. Você vai construir pipelines de dados com ingestão de APIs externas
e garantir a qualidade de dados.
Requisitos:
- Python e SQL
- {aws}
- Airflow
Diferenciais:
- Spark
- dbt
- Docker
"""


# =========================================================================== exemplos aprovados
def test_exemplo_a_engenheiro_de_dados_junior_remoto():
    av = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", DESC_A.format(aws="AWS")), PERFIL)
    confere(av, area=10, senioridade=20, fundamentos=9, ecossistema=21.30, conceitos=8.6667, formacao=4, modalidade=15)
    assert av.nota == 88 and av.faixa == "alta"
    assert av.confianca.pontos == 7 and av.confianca.nivel == "alta" and av.confianca.motivos == []
    assert av.elegibilidade == "nao_se_aplica" and av.alertas == []


def test_exemplo_a_o_ecossistema_usa_aws_generica_a_08():
    av = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", DESC_A.format(aws="AWS")), PERFIL)
    assert av.parcela("ecossistema").detalhe == "C=0.5857"          # 2,05 / 3,5
    assert any(m.startswith("➕ AWS (genérica)") for m in av.motivos)


def test_exemplo_a2_aws_substituida_por_s3_e_glue():
    av = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", DESC_A.format(aws="S3 e Glue")), PERFIL)
    confere(av, fundamentos=9, ecossistema=19.50, conceitos=8.6667)
    assert av.nota == 86 and av.parcela("ecossistema").detalhe == "C=0.5000"   # 2,25 / 4,5
    assert "⚠️ Lacuna obrigatória: Glue" in av.motivos       # Glue não é tratado como conhecido
    assert "✅ Experiência profissional: S3, Docker" in av.motivos


def test_exemplo_b_so_python_e_sql():
    av = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", "Vaga remota.\nRequisitos:\n- Python\n- SQL"), PERFIL)
    confere(av, area=10, senioridade=20, fundamentos=9, ecossistema=9, conceitos=3, formacao=4, modalidade=15)
    assert av.nota == 70 and av.faixa == "media"
    assert av.confianca.pontos == 4 and av.confianca.nivel == "media"
    assert "❔ Sem requisitos de ecossistema identificados (piso de 9 pontos)" in av.motivos


def test_exemplo_c_backend_python_django_fica_fora_da_trilha():
    descricao = "Python, Django, SQL e APIs REST. Requisitos:\n- Python\n- Django\n- SQL"
    assert montar_vaga_dados(fonte="x", id_externo="1", titulo="Desenvolvedor Backend Python (Django, SQL, APIs)",
                             url="u", descricao=descricao) is None
    with pytest.raises(ValueError):
        calcular(None, PERFIL)


DESC_D = """\
Estágio híbrido em São Paulo. Exige estar cursando graduação em Ciência da Computação.
Requisitos:
- Python e SQL
Desejável:
- Power BI
"""


def test_exemplo_d_estagio_hibrido_com_graduacao_exigida():
    av = calcular(vaga("Estágio em Engenharia de Dados", DESC_D), PERFIL, FORMACAO_SEM_CONCLUSAO)
    confere(av, area=10, senioridade=15, fundamentos=9, ecossistema=9, conceitos=3, formacao=2, modalidade=2)
    assert av.nota == 50 and av.faixa == "baixa"
    assert av.elegibilidade == "alerta" and av.alertas == [MSG_ESTAGIO_GRADUACAO]
    assert f"⚠️ {MSG_ESTAGIO_GRADUACAO}" in av.motivos
    assert av.confianca.pontos == 6 and av.confianca.nivel == "alta"
    assert "⚠️ Lacuna desejável: Power BI" in av.motivos


def test_exemplo_e_alerta_do_gmail_so_com_titulo():
    v = montar_vaga_dados(fonte="linkedin", id_externo="1", titulo="Data Engineer Júnior", url="u",
                          descricao="Acme · Brasil (Remoto)", localizacao="Brasil (Remoto)", so_titulo=True)
    av = calcular(v, PERFIL)
    confere(av, area=10, senioridade=20, fundamentos=5, ecossistema=9, conceitos=3, formacao=4, modalidade=15)
    assert av.nota == 66 and av.faixa == "media"
    assert av.confianca.pontos == 2 and av.confianca.nivel == "baixa"
    assert "❔ Só o título (sem descrição da vaga)" in av.confianca.motivos


def test_nota_e_confianca_sao_independentes():
    a = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", "Vaga remota.\nRequisitos:\n- Python\n- SQL"), PERFIL)
    e = calcular(montar_vaga_dados(fonte="l", id_externo="1", titulo="Data Engineer Júnior", url="u",
                                   descricao="Acme · Remoto", so_titulo=True), PERFIL)
    assert e.nota == 66 and a.nota == 70           # notas parecidas...
    assert e.confianca.nivel == "baixa" and a.confianca.nivel == "media"     # ...confianças diferentes


# =========================================================================== evidências
@pytest.mark.parametrize("tecnologia, peso", [
    ("Python", 0.8), ("SQL", 1.0), ("Spark", 0.6), ("Airflow", 0.3), ("Glue", 0.0), ("Athena", 0.0),
    ("Redshift", 0.0), ("Delta Lake", 0.0), ("Kinesis", 0.0), ("EMR", 0.0), ("S3", 1.0), ("Lambda", 1.0),
])
def test_cada_nivel_de_evidencia_no_ecossistema(tecnologia, peso):
    if tecnologia in ("Python", "SQL"):      # fundamentos: 5 × evidência
        av = calcular(vaga("Engenheiro de Dados Júnior", f"Requisitos:\n- {tecnologia}"), PERFIL)
        assert av.parcela("fundamentos").pontos == pytest.approx(5 * peso + 2.5)
    else:
        av = calcular(vaga("Engenheiro de Dados Júnior", f"Requisitos:\n- {tecnologia}"), PERFIL)
        assert av.parcela("ecossistema").pontos == pytest.approx(30 * (0.3 + 0.7 * peso), abs=0.01)


def test_python_e_projeto_pessoal_nunca_profissional():
    av = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Python"), PERFIL)
    assert av.parcela("fundamentos").pontos == pytest.approx(4 + 2.5)        # 5 × 0,8 + SQL não citado
    assert "Python (projeto pessoal)" in av.parcela("fundamentos").detalhe


def test_aws_generica_versus_servicos_especificos():
    so_aws = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- AWS"), PERFIL)
    assert so_aws.parcela("ecossistema").pontos == pytest.approx(30 * (0.3 + 0.7 * 0.8))
    com_servico = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- AWS (S3)"), PERFIL)
    assert com_servico.parcela("ecossistema").pontos == pytest.approx(30 * (0.3 + 0.7 * 1.0))   # só o S3 conta
    sem_experiencia = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- AWS Glue e Redshift"), PERFIL)
    assert sem_experiencia.parcela("ecossistema").pontos == pytest.approx(9)     # AWS genérica ignorada; Glue e Redshift = 0


def test_obrigatorio_pesa_o_dobro_do_desejavel():
    # Airflow (0,3) obrigatório + Docker (1,0) desejável: C = (1×0,3 + 0,5×1,0) / 1,5
    av = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Airflow\nDiferenciais:\n- Docker"), PERFIL)
    c = (0.3 + 0.5) / 1.5
    assert av.parcela("ecossistema").pontos == pytest.approx(30 * (0.3 + 0.7 * c))
    inverso = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Docker\nDiferenciais:\n- Airflow"), PERFIL)
    assert inverso.parcela("ecossistema").pontos > av.parcela("ecossistema").pontos


def test_lacuna_isolada_nao_zera_o_ecossistema():
    av = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Glue\n- Redshift\n- Athena"), PERFIL)
    assert av.parcela("ecossistema").pontos == pytest.approx(9)       # piso: 30 × 0,3
    # área 10 + nível 20 + fundamentos 5 + ecossistema 9 + conceitos 3 + formação 4 + modalidade 6 = 57
    assert av.nota == 57
    assert "⚠️ Lacuna obrigatória: Glue, Athena, Redshift" in av.motivos


def test_item_so_citado_em_atividades_nao_conta_como_requisito():
    descricao = "Responsabilidades:\n- Construir DAGs de Airflow e usar Spark\nRequisitos:\n- Docker"
    v = vaga("Engenheiro de Dados Júnior", descricao)
    assert v["citados_em_atividades"] == ["Spark", "Airflow"]
    av = calcular(v, PERFIL)
    assert av.parcela("ecossistema").pontos == pytest.approx(30 * (0.3 + 0.7 * 1.0))   # só Docker


def test_python_e_sql_nao_contam_de_novo_no_ecossistema():
    so_fundamentos = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Python\n- SQL"), PERFIL)
    assert so_fundamentos.parcela("ecossistema").pontos == pytest.approx(9)


def test_sem_requisitos_de_ecossistema_vale_o_piso_de_9():
    av = calcular(vaga("Engenheiro de Dados Júnior", "Vaga para quem gosta de dados."), PERFIL)
    assert av.parcela("ecossistema").pontos == pytest.approx(9)


# =========================================================================== fundamentos, conceitos, área, nível, modalidade
@pytest.mark.parametrize("titulo, area", [
    ("Engenheiro de Dados Júnior", 10), ("Analytics Engineer Jr", 8), ("Desenvolvedor ETL Jr", 8),
])
def test_area_do_cargo(titulo, area):
    assert pontos(calcular(vaga(titulo), PERFIL))["area"] == area


def test_area_relacionada_recebe_5_e_um_aviso():
    v = vaga("Desenvolvedor Python Júnior", "Atuação com ETL, Spark e Airflow.")
    assert v["categoria_cargo"] == "relacionada"
    av = calcular(v, PERFIL)
    assert pontos(av)["area"] == 5 and any("apenas relacionado" in m for m in av.motivos)


@pytest.mark.parametrize("titulo, nivel_pts", [
    ("Engenheiro de Dados Júnior", 20), ("Engenheiro de Dados Trainee", 18), ("Engenheiro de Dados Estágio", 15),
    ("Engenheiro de Dados", 12), ("Engenheiro de Dados Pleno", 4), ("Engenheiro de Dados Sênior", 0),
])
def test_senioridade(titulo, nivel_pts):
    assert pontos(calcular(vaga(titulo), PERFIL))["senioridade"] == nivel_pts


@pytest.mark.parametrize("modelo_no_titulo, pts", [("[Remoto] ", 15), ("[Híbrido] ", 2), ("[Presencial] ", 0), ("", 6)])
def test_modalidade_so_remoto_pontua_cheio(modelo_no_titulo, pts):
    av = calcular(vaga(f"{modelo_no_titulo}Engenheiro de Dados Júnior"), PERFIL)
    assert pontos(av)["modalidade"] == pts


def test_cidade_viavel_nao_vale_mais_nada():
    av = calcular(vaga("[Híbrido] Engenheiro de Dados Júnior", localizacao="Alfaville, SP"), PERFIL)
    assert pontos(av)["modalidade"] == 2


def test_conceitos_usam_a_media_das_evidencias():
    descricao = "Pipelines de dados com Parquet e Terraform, arquitetura Medallion e importações idempotentes."
    av = calcular(vaga("Engenheiro de Dados Júnior", descricao), PERFIL)
    # ETL (prof 1,0) + armazenamento colunar (proj 0,8) + IaC (proj 0,8) + Medallion (lab 0,6) + idempotente (prof 1,0)
    assert av.parcela("conceitos").pontos == pytest.approx(10 * (1.0 + 0.8 + 0.8 + 0.6 + 1.0) / 5)


def test_fundamento_nao_citado_vale_2_5_e_gera_motivo():
    av = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Python"), PERFIL)
    assert av.parcela("fundamentos").pontos == pytest.approx(4 + 2.5)
    assert "❔ SQL não citado" in av.motivos


# =========================================================================== sem informações e confiança
def test_vaga_sem_descricao_e_sem_informacoes():
    av = calcular(vaga("Engenheiro de Dados"), PERFIL)
    confere(av, area=10, senioridade=12, fundamentos=5, ecossistema=9, conceitos=3, formacao=4, modalidade=6)
    assert av.nota == 49 and av.faixa == "baixa"
    assert av.confianca.pontos == 0 and av.confianca.nivel == "baixa"
    assert {"❔ Só o título (sem descrição da vaga)", "❔ Nível não informado", "❔ Modalidade não informada"} <= set(av.confianca.motivos)


def test_descricao_igual_ao_titulo_nao_conta_como_descricao():
    av = calcular(montar_vaga_dados(fonte="x", id_externo="1", titulo="Engenheiro de Dados Júnior", url="u",
                                    descricao="Engenheiro de Dados Júnior"), PERFIL)
    assert "❔ Só o título (sem descrição da vaga)" in av.confianca.motivos


def test_confianca_pontua_cada_sinal():
    cheia = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", DESC_A.format(aws="AWS")), PERFIL).confianca
    assert cheia.pontos == 7 and cheia.nivel == "alta"
    tres_itens = calcular(vaga("Engenheiro de Dados", "Requisitos:\n- Python\n- SQL\n- Spark"), PERFIL).confianca
    assert tres_itens.pontos == 3 and tres_itens.nivel == "media"      # descrição 2 + 3 itens 1
    assert any("Poucas tecnologias" in m for m in tres_itens.motivos)
    so_um_grupo = calcular(vaga("Engenheiro de Dados", "Requisitos:\n- Python"), PERFIL).confianca
    assert any("não separa requisitos" in m for m in so_um_grupo.motivos)


@pytest.mark.parametrize("n, faixa", [(0, "baixa"), (59, "baixa"), (60, "media"), (74, "media"), (75, "alta"), (100, "alta")])
def test_faixas(n, faixa):
    assert faixa_da_nota(n) == faixa


def test_nota_limitada_entre_0_e_100():
    av = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", DESC_A.format(aws="AWS")), PERFIL)
    assert 0 <= av.nota <= 100 and isinstance(av.nota, int)


# =========================================================================== elegibilidade
def test_estagio_exige_graduacao_em_curso_gera_alerta_e_nota_2():
    av = calcular(vaga("Estágio em Engenharia de Dados", "Requisitos:\n- Cursando graduação em Computação"), PERFIL)
    assert av.elegibilidade == "alerta" and av.parcela("formacao").pontos == 2 and av.alertas == [MSG_ESTAGIO_GRADUACAO]


def test_trainee_que_exige_ensino_superior_recebe_o_alerta():
    av = calcular(vaga("Trainee Engenharia de Dados", "Requisitos:\n- Ensino superior em andamento"), PERFIL)
    assert av.elegibilidade == "alerta" and av.alertas == [MSG_ESTAGIO_GRADUACAO]


def test_estagio_sem_exigir_graduacao_nao_tem_alerta():
    av = calcular(vaga("Estágio em Engenharia de Dados", "Requisitos:\n- Python"), PERFIL)
    assert av.elegibilidade == "nao_se_aplica" and av.parcela("formacao").pontos == 4 and av.alertas == []


def test_graduacao_desejavel_nao_e_exigencia():
    av = calcular(vaga("Estágio em Engenharia de Dados", "Requisitos:\n- Python\nDiferenciais:\n- Graduação em andamento"), PERFIL)
    assert av.elegibilidade == "nao_se_aplica"


def test_pos_graduacao_nao_e_graduacao():
    av = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Pós-graduação em dados"), PERFIL)
    assert av.elegibilidade == "nao_se_aplica"


def test_graduacao_exigida_fora_do_estagio_com_formacao_nao_confirmada_fica_desconhecida():
    descricao = "Minimum qualifications:\n- Bachelor's degree in Computer Science."
    av = calcular(vaga("Engenheiro de Dados Júnior", descricao), PERFIL, FORMACAO_SEM_CONCLUSAO)
    assert av.elegibilidade == "alerta" and av.parcela("formacao").pontos == 2
    assert av.alertas and "não está confirmada" in av.alertas[0]
    sem_dados_de_formacao = calcular(vaga("Engenheiro de Dados Júnior", descricao), PERFIL)
    assert sem_dados_de_formacao.parcela("formacao").pontos == 2


def test_graduacao_exigida_com_formacao_concluida_no_perfil_atende():
    formacao = [{"origem_curso": "Tecnólogo em ADS", "conclusao": "2023"}]
    av = calcular(vaga("Engenheiro de Dados Júnior", "Requisitos:\n- Graduação em Computação"), PERFIL, formacao)
    assert av.elegibilidade == "ok" and av.parcela("formacao").pontos == 5


# =========================================================================== alertas independentes da nota
@pytest.mark.parametrize("texto, anos", [
    ("3+ years of experience with Spark", 3), ("At least 3 years working with data", 3),
    ("Mínimo de 3 anos de experiência", 3), ("5 anos de experiência em dados", 5),
    ("Experiência mínima de 4 anos", 4), ("minimum 6 years in data engineering", 6),
    ("1 ano de experiência", None), ("2 years of experience", None), ("sem exigência de tempo", None),
    ("Trabalhamos 40 anos no mercado", None),
])
def test_anos_de_experiencia_exigidos(texto, anos):
    assert anos_de_experiencia_exigidos(texto) == anos


def test_alerta_de_anos_nao_muda_nota_nem_categoria_nem_alvo():
    base = "Requisitos:\n- Python\n- SQL"
    sem = vaga("[Remoto] Engenheiro de Dados Júnior", base)
    com = vaga("[Remoto] Engenheiro de Dados Júnior", base + "\n- 5 anos de experiência com dados")
    a_sem, a_com = calcular(sem, PERFIL), calcular(com, PERFIL)
    assert a_com.nota == a_sem.nota and com["categoria_cargo"] == sem["categoria_cargo"] and com["alvo"] == sem["alvo"]
    assert a_com.alertas == ["Exige 5 anos de experiência ou mais; senioridade provável acima do nível da vaga."]
    assert any(m.startswith("⚠️ Exige 5 anos") for m in a_com.motivos) and a_sem.alertas == []


def test_localizacao_fora_do_brasil_sem_remoto_confirmado():
    v = vaga("Data Engineer", "Requisitos:\n- SQL", localizacao="Cidade do México, México")
    av = calcular(v, PERFIL)
    assert av.alertas == [MSG_FORA_DO_BRASIL] and f"⚠️ {MSG_FORA_DO_BRASIL}" in av.motivos
    assert v["modelo_trabalho"] is None          # não presume presencial
    assert pontos(av)["modalidade"] == 6


@pytest.mark.parametrize("localizacao, descricao, alerta", [
    ("São Paulo, Brasil / Santiago, Chile + 3 cidades", "Requisitos:\n- SQL", False),   # inclui o Brasil
    ("Brasil", "Requisitos:\n- SQL", False),
    ("São Paulo, SP", "Requisitos:\n- SQL", False),
    (None, "Requisitos:\n- SQL", False),
    ("Buenos Aires, Argentina", "Requisitos:\n- SQL\nRemote work for candidates in Brazil", False),
    ("Lisboa, Portugal", "Requisitos:\n- SQL\nTrabalho remoto para o Brasil (LATAM)", False),
    ("Buenos Aires, Argentina", "Requisitos:\n- SQL", True),
    ("New York, United States", "Requisitos:\n- SQL\nRemote", True),
])
def test_localizacao_internacional(localizacao, descricao, alerta):
    av = calcular(vaga("Data Engineer Junior", descricao, localizacao=localizacao), PERFIL)
    assert (MSG_FORA_DO_BRASIL in av.alertas) is alerta


@pytest.mark.parametrize("texto, exige", [
    ("Inglês avançado", True), ("Inglês fluente", True), ("Fluent English required", True), ("Advanced English", True),
    ("Fluência em inglês", True), ("Inglês C1", True), ("Proficient in English", True),
    ("Inglês técnico para leitura", False), ("Inglês intermediário", False), ("Conhecimento de inglês desejável", False),
])
def test_ingles_avancado(texto, exige):
    assert exige_ingles_avancado(texto) is exige


def test_ingles_avancado_so_alerta_sem_desconto_na_nota():
    base = "Requisitos:\n- Python\n- SQL"
    sem = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", base), PERFIL)
    com = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", base + "\n- Inglês avançado"), PERFIL)
    assert com.nota == sem.nota
    assert com.alertas == ["Exige inglês avançado ou fluente (sem desconto na nota)."]
    assert all("seu inglês" not in m.lower() for m in com.motivos)      # nada afirma o nível de inglês do candidato


def test_alertas_ficam_nos_motivos_com_o_prefixo_de_atencao():
    v = vaga("Estágio em Engenharia de Dados", "Requisitos:\n- Cursando graduação\n- 3 anos de experiência\n- Inglês avançado",
             localizacao="Santiago, Chile")
    av = calcular(v, PERFIL)
    assert len(av.alertas) == 4 and all(f"⚠️ {a}" in av.motivos for a in av.alertas)


# =========================================================================== o perfil real (fora do Git)
def test_perfil_real_reproduz_os_exemplos_aprovados():
    caminho = Path(__file__).resolve().parents[1] / "curriculo" / "base" / "curriculo_dados.yaml"
    if not caminho.exists():
        pytest.skip("curriculo_dados.yaml não existe nesta máquina")
    perfil, formacao = carregar_perfil(caminho)
    a = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", DESC_A.format(aws="AWS")), perfil, formacao)
    a2 = calcular(vaga("[Remoto] Engenheiro de Dados Júnior", DESC_A.format(aws="S3 e Glue")), perfil, formacao)
    d = calcular(vaga("Estágio em Engenharia de Dados", DESC_D), perfil, formacao)
    assert (a.nota, a2.nota, d.nota) == (88, 86, 50)
    assert d.elegibilidade == "alerta"
