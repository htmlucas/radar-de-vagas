# Radar de vagas Laravel

Pipeline pessoal que coleta vagas de desenvolvedor, filtra as que pedem **Laravel em nível júnior/pleno**,
dá uma **nota de compatibilidade** com o seu perfil e mostra **sugestões em texto para adaptar o
currículo** a cada vaga. Tudo roda localmente, sem custo de API. Próxima etapa: aviso no Telegram.

## Arquitetura

```
fontes (GitHub, Adzuna, alertas no Gmail)
   │  coleta/            requisições às APIs oficiais
   ▼
bronze  dados/bronze/<fonte>/<data>/*.json     resposta bruta, sem alteração
   │  tratamento/        nível, modelo de trabalho, tecnologias, chave de duplicidade
   ▼
silver  silver.vagas, silver.vaga_status, silver.execucoes   (PostgreSQL)
   ▼
gold    gold.vagas (sem duplicadas, com nota) · gold.vagas_alvo (Laravel júnior/pleno + PHP dos e-mails)
   ▼
painel/ Streamlit ──► sugestões para o currículo (cruzando a vaga com curriculo/base/curriculo.yaml)
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

## Sugestões para o currículo

Seu currículo fica em `curriculo/base/curriculo.yaml` (modelo em `curriculo/exemplo.yaml`).
No painel, ligue **📝 Sugestões para adaptar seu currículo** em uma vaga. As sugestões são calculadas
localmente (`vagas/curriculo/sugestoes.py`), cruzando tecnologias e temas da vaga com o seu currículo:

- **Título sugerido** e **rascunho de resumo**, montados só com o que o currículo comprova;
- **O que a vaga pede e você comprova**, para usar os mesmos termos da vaga;
- **Atividades para colocar no topo** de cada experiência, com o motivo de cada uma;
- **Projetos para destacar**;
- **O que a vaga pede e não aparece no seu currículo**, para incluir (se tiver) ou se preparar.

Nas vagas da Adzuna, cole a descrição completa no campo da vaga para sugestões mais precisas
(a API só traz um trecho). As sugestões podem ser baixadas em `.txt`.

Opcional: a aba **Texto para colar num chat de IA** monta um pedido pronto (sem seus dados de contato)
para colar no assistente de IA que você já usa. O projeto não chama nenhuma API paga.

## Fontes

| Fonte | O que é | Precisa de chave? |
|---|---|---|
| GitHub | Issues abertas de `backend-br/vagas` e `phpdevbr/vagas` | Não (token opcional) |
| Adzuna | API que agrega vagas de vários sites do Brasil | Sim, gratuita: https://developer.adzuna.com/ |
| Gmail | Alertas de vaga que chegam no seu e-mail (LinkedIn, Indeed, Gupy...) | Autorização do Google, gratuita (abaixo) |

### Gmail: configuração (uma vez só)

O projeto lê os e-mails pela API oficial do Gmail com permissão **somente de leitura**
(`gmail.readonly`): não consegue apagar, enviar nem alterar nada. Sua senha nunca passa pelo projeto.

1. Acesse https://console.cloud.google.com/ e crie um projeto (ex.: `vagas-laravel`).
2. Em **APIs e serviços → Biblioteca**, procure **Gmail API** e clique em **Ativar**.
3. Em **Google Auth Platform** (tela de permissão OAuth), clique em **Começar**: dê um nome ao app,
   escolha seu e-mail como suporte, público **Externo**, e conclua.
4. Em **Público**, adicione o seu próprio Gmail em **Usuários de teste**.
5. Em **Clientes → Criar cliente**, escolha o tipo **App para computador** e crie. Clique em
   **Baixar JSON** e salve o arquivo como `credenciais/gmail_cliente.json` dentro desta pasta.
6. Rode a autorização. O navegador abre; o Google vai avisar que o app não foi verificado
   (é o seu próprio app): clique em **Continuar** e permita a leitura dos e-mails.

```bash
.venv\Scripts\python -m vagas.coleta.gmail --autorizar
```

> Com o app em modo **Teste**, o Google expira a autorização a cada 7 dias e você precisa rodar o
> `--autorizar` de novo. Para não expirar, em **Público** clique em **Publicar app** (fica "Em produção"
> sem precisar de verificação para uso pessoal; o aviso de "app não verificado" continua aparecendo
> só na hora de autorizar).

Depois de autorizado:

```bash
.venv\Scripts\python -m vagas.coleta.gmail --descobrir   # quem te manda e-mails de vaga e quantas vagas foram lidas
.venv\Scripts\python -m vagas.coleta.gmail --testar      # mostra as vagas extraídas, sem gravar
```

Os alertas por e-mail trazem só título, empresa e local, sem a descrição. Por isso essas vagas entram
no filtro principal quando citam Laravel **ou PHP** no título, e o painel avisa para confirmar Laravel
abrindo a vaga (`so_titulo` na silver).

A busca padrão pega e-mails dos últimos 7 dias que falam de vaga e de Laravel ou PHP. Dá para trocar
com `GMAIL_DIAS` e `GMAIL_CONSULTA` no `.env` (mesma sintaxe da caixa de pesquisa do Gmail).
O arquivo do cliente e o token ficam em `credenciais/`, fora do Git.

## Como rodar

Requisitos: Python 3.12+ e Docker Desktop.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # troque a senha do banco e coloque as chaves da Adzuna
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
├── coleta/              um módulo por fonte (emails.py extrai vagas do HTML dos alertas)
├── tratamento/          regras de padronização
├── pontuacao/nota.py    nota de compatibilidade
├── curriculo/           leitura do currículo base e sugestões por vaga
└── painel/app.py        painel Streamlit
curriculo/exemplo.yaml   modelo do currículo base
sql/schema.sql           esquemas silver e gold (idempotente)
tests/                   testes das regras de tratamento, nota e sugestões
```

## Privacidade

`.env`, `dados/` e as pastas de currículo ficam fora do Git (ver `.gitignore`).
O código pode ser público sem expor dados pessoais.
