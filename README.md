# Radar de vagas Laravel

Pipeline pessoal que coleta vagas de desenvolvedor, filtra as que pedem **Laravel em nível júnior/pleno**,
dá uma **nota de compatibilidade** com o seu perfil e gera um **currículo adaptado para cada vaga**
(.docx e PDF) com a API do Claude. Tudo num painel no navegador. Próxima etapa: aviso no Telegram.

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
gold    gold.vagas (sem duplicadas, com nota) · gold.vagas_alvo (Laravel júnior/pleno)
   ▼
painel/ Streamlit ──► curriculo/ (Claude) ──► curriculo/gerados/<vaga>/*.docx, *.pdf
```

- **Bronze em arquivo**: dá para reprocessar a silver quando as regras mudarem, sem coletar de novo.
- **Upsert por id**: rodar a coleta várias vezes não duplica vagas.
- **Duplicidade entre fontes**: a mesma vaga em sites diferentes tem a mesma `chave_dedupe` e aparece uma vez só no gold.
- **Status separado da vaga**: a coleta nunca apaga o que você marcou (interessa, candidatei, descartada).
- **Fontes isoladas**: se uma falha, as outras continuam e o erro aparece no painel.

## Nota de compatibilidade (0 a 100)

Regra determinística em `vagas/pontuacao/nota.py`, recalculada a cada coleta para todas as vagas:

| Critério | Peso | Como pontua |
|---|---|---|
| Stack | 60 | Tecnologias da vaga que você domina (100%) ou conhece (50%). Com menos de 4 tecnologias detectadas, fica limitada a 75% |
| Nível | 15 | Pleno 15 · Júnior 11 · Não informado 10 · Sênior 3 |
| Modelo/local | 15 | Remoto 15 · Híbrido/presencial em cidade viável 13 · Não informado 8 · Fora da região 2–4 |
| Cargo | 10 | Desenvolvimento 10 · Front-end puro 5 · Outra área (DevOps, suporte...) multiplica a nota por 0,6 |

O perfil (o que você domina, conhece e as cidades viáveis) fica na seção `pontuacao` do currículo base.

## Currículo adaptado

1. Seu currículo fica em `curriculo/base/curriculo.yaml` (modelo em `curriculo/exemplo.yaml`).
2. No painel, em cada vaga, **Gerar currículo adaptado**. Para vagas da Adzuna, cole a descrição completa
   (a API só traz um trecho).
3. O Claude (`claude-opus-5-5`, saída estruturada) escolhe e reescreve o conteúdo; o código monta o documento.

Proteções contra invenção:
- Nome, contato, empresas, cargos, datas, formação e certificações vêm **sempre** do currículo base.
- Ids de experiência/projeto que não existem no base são descartados.
- Depois de gerar, o sistema confere se apareceu alguma tecnologia que não está no base e mostra um alerta.

Cada geração salva `.docx`, `.pdf` e `analise.json` (lacunas, palavras-chave, dicas, tokens usados)
em `curriculo/gerados/`. O custo por currículo fica na casa de centavos de dólar.

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
copy .env.example .env          # troque a senha do banco e coloque as chaves de API
copy curriculo\exemplo.yaml curriculo\base\curriculo.yaml   # e preencha com seus dados
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
├── pontuacao/nota.py    nota de compatibilidade
├── curriculo/           leitura do base, geração com Claude, .docx/.pdf
└── painel/app.py        painel Streamlit
curriculo/exemplo.yaml   modelo do currículo base
sql/schema.sql           esquemas silver e gold (idempotente)
tests/                   testes (a geração é testada com um cliente falso, sem gastar API)
```

## Privacidade

`.env`, `dados/` e as pastas de currículo ficam fora do Git (ver `.gitignore`).
O código pode ser público sem expor dados pessoais.
