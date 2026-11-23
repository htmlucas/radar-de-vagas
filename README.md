# Radar de vagas Laravel

Pipeline pessoal que coleta vagas de desenvolvedor, filtra as que pedem **Laravel em nível júnior/pleno**
e mostra tudo num painel no navegador. Próximas etapas: nota de compatibilidade com o currículo,
currículo adaptado por vaga (.docx e PDF) e aviso no Telegram.

## Arquitetura

```
fontes (GitHub, Adzuna)
   │  coleta/            requisições às APIs oficiais
   ▼
bronze  dados/bronze/<fonte>/<data>/*.json     resposta bruta, sem alteração
   │  tratamento/        nível, modelo de trabalho, tecnologias, chave de duplicidade
   ▼
silver  silver.vagas, silver.vaga_status, silver.execucoes   (PostgreSQL)
   ▼
gold    gold.vagas (sem duplicadas) · gold.vagas_alvo (Laravel júnior/pleno)
   ▼
painel/ Streamlit
```

- **Bronze em arquivo**: dá para reprocessar a silver quando as regras mudarem, sem coletar de novo.
- **Upsert por id**: rodar a coleta várias vezes não duplica vagas.
- **Duplicidade entre fontes**: a mesma vaga em sites diferentes tem a mesma `chave_dedupe` e aparece uma vez só no gold.
- **Status separado da vaga**: a coleta nunca apaga o que você marcou (interessa, candidatei, descartada).
- **Fontes isoladas**: se uma falha, as outras continuam e o erro aparece no painel.

## Fontes

| Fonte | O que é | Precisa de chave? |
|---|---|---|
| GitHub | Issues abertas de `backend-br/vagas` e `phpdevbr/vagas` | Não (token opcional) |
| Adzuna | API que agrega vagas de vários sites do Brasil | Sim, gratuita: https://developer.adzuna.com/ |

## Como rodar

Requisitos: Python 3.12+ e Docker Desktop.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # depois troque a senha do banco no .env
docker compose up -d            # sobe o Postgres na porta 5440
```

Coletar vagas:

```bash
.venv\Scripts\python -m vagas.pipeline
```

Abrir o painel (http://localhost:8501):

```bash
.venv\Scripts\python -m streamlit run vagas/painel/app.py
```

Testes:

```bash
.venv\Scripts\python -m pytest
```

## Estrutura

```
vagas/
├── config.py            lê o .env
├── db.py                conexão e gravação no Postgres
├── pipeline.py          orquestra coleta → bronze → silver
├── coleta/              um módulo por fonte
├── tratamento/          regras de padronização
└── painel/app.py        painel Streamlit
sql/schema.sql           esquemas silver e gold (idempotente)
tests/                   testes das regras de tratamento e extração
```

## Privacidade

`.env`, `dados/` e as pastas de currículo ficam fora do Git (ver `.gitignore`).
O código pode ser público sem expor dados pessoais.
