"""Dados sintéticos (no formato de gold.dados_vagas) e currículos de exemplo para os testes do painel da trilha de dados."""

import pandas as pd

from vagas.painel import comum_dados as cd
from vagas.trilhas.dados.nota import faixa_da_nota
from vagas.trilhas.dados.normalizar import e_alvo


def linha(id_, titulo, *, categoria="engenharia_dados", nivel="junior", modelo="remoto", status="nova", fonte="github",
          empresa="Acme", nota=88, publicada="2026-11-20T10:00:00+00:00", so_titulo=False, confianca="alta",
          elegibilidade="nao_se_aplica", alertas=(), tecnologias=("Python", "SQL"), obrigatorios=("Python", "SQL"),
          desejaveis=(), atividades=(), motivo=None, localizacao="Brasil", status_em=None, observacao=None, chave=None):
    return {
        "id": id_, "fonte": fonte, "id_externo": id_.split(":")[-1], "titulo": titulo, "empresa": empresa,
        "descricao": f"Descrição de {titulo}.\nRequisitos:\n- Python e SQL", "url": f"https://exemplo.test/{id_.split(':')[-1]}",
        "localizacao": localizacao, "modelo_trabalho": modelo, "nivel": nivel, "categoria_cargo": categoria,
        "tecnologias": list(tecnologias), "conceitos": ["ETL / importação de dados"], "req_obrigatorios": list(obrigatorios),
        "req_desejaveis": list(desejaveis), "citados_em_atividades": list(atividades), "chave_dedupe": chave or id_,
        "publicada_em": publicada, "so_titulo": so_titulo, "primeira_coleta": publicada, "ultima_coleta": publicada,
        "status": status, "nota": observacao, "compatibilidade": nota, "faixa": faixa_da_nota(nota) if nota is not None else None,
        "parcelas": [{"nome": "area", "pontos": 10, "maximo": 10, "detalhe": categoria},
                     {"nome": "ecossistema", "pontos": 21.3, "maximo": 30, "detalhe": "C=0.5857"}],
        "motivos": ["✅ Nível júnior", "🏠 Remoto", "⚠️ Lacuna obrigatória: Glue"], "alertas": list(alertas),
        "confianca_pontos": 7 if confianca == "alta" else 4, "confianca_nivel": confianca,
        "confianca_motivos": [] if confianca == "alta" else ["❔ Nível não informado"], "elegibilidade": elegibilidade,
        "formacao_exigida": "a vaga não exige formação", "status_em": status_em, "alvo": e_alvo(categoria, nivel),
        "motivo_descarte": motivo, "detalhe_descarte": None, "fontes": [fonte],
    }


def linhas_gold() -> list[dict]:
    return [
        linha("github:A", "[Remoto] Engenheiro de Dados Júnior", empresa="Alfa", nota=88, desejaveis=("Spark", "dbt")),
        linha("adzuna:B", "Estágio em Engenharia de Dados", nivel="estagio", status="interessa", fonte="adzuna", empresa="Beta", nota=70,
              status_em="2026-11-21T10:00:00+00:00", elegibilidade="alerta", alertas=("Exige graduação em curso. Sua formação atual (pós em andamento) pode não atender; confirme com a empresa.",)),
        linha("linkedin:C", "Data Engineer Jr", modelo="hibrido", fonte="linkedin", empresa="Gama", nota=50, so_titulo=True, confianca="baixa"),
        linha("gmail:D", "Analytics Engineer", categoria="analytics_engineer", nivel=None, modelo=None, fonte="glassdoor", empresa="Delta", nota=62, confianca="media"),
        linha("github:E", "Desenvolvedor Python Júnior", categoria="relacionada", empresa="Epsilon", nota=70),
        linha("github:F", "[Remoto] Engenheiro de Dados Pleno", nivel="pleno", empresa="Zeta", nota=55),
        linha("github:G", "[Remoto] Dev ETL Júnior", categoria="dev_etl", status="candidatei", empresa="Eta", nota=75,
              status_em="2026-11-10T10:00:00+00:00", observacao="falei com a recrutadora"),
        linha("github:H", "[Remoto] Analytics Engineer Jr", categoria="analytics_engineer", status="descartada", empresa="Theta", nota=60,
              status_em="2026-11-22T10:00:00+00:00", motivo="Empresa não me interessa"),
    ]


def df_gold() -> pd.DataFrame:
    return cd.preparar_vagas_dados(linhas_gold())


def historico_simulado() -> pd.DataFrame:
    from vagas import relatorios
    return relatorios.preparar_historico([
        {"vaga_id": "adzuna:B", "status": "interessa", "em": "2026-11-21T10:00:00+00:00"},
        {"vaga_id": "github:G", "status": "interessa", "em": "2026-11-09T10:00:00+00:00"},
        {"vaga_id": "github:G", "status": "candidatei", "em": "2026-11-10T10:00:00+00:00"},
        {"vaga_id": "github:H", "status": "descartada", "em": "2026-11-22T10:00:00+00:00"}])


def execucoes_simuladas() -> pd.DataFrame:
    return pd.DataFrame([
        {"fonte": "github", "iniciada_em": "2026-11-25T11:00:00+00:00", "finalizada_em": "2026-11-25T11:00:20+00:00",
         "qtd_coletada": 4, "qtd_nova": 4, "erro": None},
        {"fonte": "adzuna", "iniciada_em": "2026-11-25T11:00:30+00:00", "finalizada_em": "2026-11-25T11:00:40+00:00",
         "qtd_coletada": None, "qtd_nova": None, "erro": "RuntimeError: API fora do ar"}])


# --------------------------------------------------------------------------- currículos de exemplo (mesma estrutura dos YAMLs reais)
BASE = {
    "contato": {"nome": "Pessoa Exemplo"},
    "experiencias": [
        {"id": "acme", "empresa": "Acme Dados", "cargo": "Desenvolvedor Full Stack Pleno (Freelancer)", "periodo": "Maio/2024 – Setembro/2025",
         "atividades": ["Integração com AWS S3, SQS e Lambda utilizando Bref.", "Implementação de processamento assíncrono e operações idempotentes.",
                        "Desenvolvimento de pipelines de importação e processamento de dados de fontes governamentais."]},
        {"id": "beta", "empresa": "Beta Sistemas", "cargo": "Desenvolvedor Laravel Júnior", "periodo": "2022 – 2023",
         "atividades": ["Integração com AWS S3 e serviços auxiliares em Node.js para processamento de arquivos CSV."]},
    ],
    "projetos": [{"id": "catalog", "nome": "Catalog Data Pipeline", "link": "github.com/exemplo/catalog",
                  "descricao": "Pipeline com Databricks, camadas Bronze, Silver e Gold e validação de qualidade."},
                 {"id": "projeto_eventos", "nome": "Projeto Eventos", "link": "", "descricao": "Plataforma de eventos."}],
    "formacao": [{"curso": "Pós-graduação em Engenharia de Dados", "instituicao": "Universidade Exemplo", "status": "em andamento"},
                 {"curso": "Tecnólogo em ADS", "instituicao": "Instituto Exemplo", "status": ""}],
    "certificacoes": ["AWS Cloud Practitioner Essentials (curso)"],
    "pontuacao": {"dominio": ["Laravel"], "conhecimento": []},
}
DADOS = {
    "titulo_sugerido": "Desenvolvedor Backend | Engenharia de Dados (pós-graduação em andamento)",
    "resumo": "Desenvolvedor backend em transição para Engenharia de Dados.",
    "experiencia_profissional": [
        {"origem_id": "acme", "bases_importadas": [{"base": "CBO", "volume": "≈2.700 ocupações"}, {"base": "Receita Federal", "volume": None}],
         "complementos": ["Enriquecimento de dados em processos de habilidades."]},
        {"origem_id": "beta"}],
    "projetos_pessoais": [
        {"origem_id": "catalog", "visibilidade": "publico", "complementos": ["Armazenamento em Parquet.", "Terraform para o S3."],
         "nao_usar_da_origem": ["Databricks"]},
        {"id": "radar_vagas", "nome": "Radar de Vagas", "situacao": "em desenvolvimento", "visibilidade": "nao_publicado",
         "descricao": "Pipeline pessoal de vagas.", "destaques": ["Camadas bronze, silver e gold no PostgreSQL."]}],
    "laboratorios": [{"id": "databricks_medallion", "nome": "Laboratório Databricks", "contexto": "estudo",
                      "destaques": ["Tabelas bronze, silver e gold no Databricks."]}],
    "estudos": {"em_andamento": ["Airflow", "dbt"]},
    "formacao": [{"origem_curso": "Pós-graduação em Engenharia de Dados", "inicio": "2026-08", "previsao_termino": None},
                 {"origem_curso": "Tecnólogo em ADS", "conclusao": None}],
    "cursos": [{"origem_curso": "AWS Cloud Practitioner Essentials (curso)", "situacao": "concluido", "tipo": "curso"}],
    "pontuacao_dados": {
        "pesos_evidencia": {"profissional": 1.0, "projeto": 0.8, "laboratorio": 0.6, "estudo": 0.3, "nenhuma": 0.0},
        "aws_generica": 0.8,
        "tecnologias": {
            "SQL": {"nivel": "profissional", "origem": ["acme"]}, "S3": {"nivel": "profissional", "origem": ["acme", "beta"]},
            "SQS": {"nivel": "profissional", "origem": ["acme"]}, "Lambda": {"nivel": "profissional", "origem": ["acme"]},
            "Python": {"nivel": "projeto", "origem": ["catalog", "radar_vagas"]}, "Terraform": {"nivel": "projeto", "origem": ["catalog"]},
            "Parquet": {"nivel": "projeto", "origem": ["catalog"]},
            "Spark": {"nivel": "laboratorio", "origem": ["databricks_medallion"]}, "Databricks": {"nivel": "laboratorio", "origem": ["databricks_medallion"]},
            "Airflow": {"nivel": "estudo"}, "dbt": {"nivel": "estudo"}, "Glue": {"nivel": "nenhuma"}, "Redshift": {"nivel": "nenhuma"}},
        "conceitos": {"ETL / importação de dados": {"nivel": "profissional", "origem": ["acme"]},
                      "validação e qualidade de dados": {"nivel": "laboratorio", "origem": ["databricks_medallion"]}},
    },
}
