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

## Painel

Interface no estilo de um SaaS: tema claro, índigo, fonte Inter, ícones Lucide (SVGs oficiais do pacote
`lucide-static`, licença ISC, em `vagas/painel/icones/`) e gráficos com paleta validada para daltonismo.

| Página | Para que serve |
|---|---|
| Visão geral | Indicadores (vagas, no perfil, novas na semana, candidaturas, acompanhamento), evolução semanal, melhores oportunidades, o que precisa de ação e resumo do mercado |
| Vagas | Busca, filtros rápidos (modalidade, status, só meu perfil) e avançados (nível, tecnologia, fonte, período), ordenação, cards com nota explicável e ações; detalhes em janela sem sair da lista |
| Candidaturas | Tabela editável (status, observação, próxima ação, dias sem retorno) e kanban com as etapas existentes |
| Sugestões de currículo | Vaga e requisitos à esquerda; resumo, experiência, projetos, tecnologias e lacunas à direita, cada trecho com botão de copiar |
| Relatórios | Candidaturas, Descartadas, Mercado, Stack, Empresas e Fontes |
| Configurações | Coleta, estado de cada fonte, camadas Bronze/Silver/Gold, histórico de execuções e integrações (sem expor chaves) |

Tema em `.streamlit/config.toml`; componentes visuais em `vagas/painel/ui.py`; gráficos em `vagas/painel/graficos.py`;
regras de apresentação testadas em `vagas/painel/logica.py`.

## Relatórios

Página **📊 Relatórios** do painel (menu lateral), tudo na tela. Filtros no topo: período, vagas
(alvo ou todas), fontes e modelo de trabalho.

| Aba | O que responde |
|---|---|
| 📨 Minhas candidaturas | Candidaturas, taxa de resposta, entrevistas, propostas, dias até se candidatar; funil; candidaturas por semana; **tabela editável das empresas em que você se candidatou** (andamento e observação); **quem cobrar** (sem retorno há 7+ dias); vagas paradas em "interessa"; boas vagas recentes que você ainda não marcou |
| 🗑️ Descartadas | Por que você descarta (gráfico dos motivos) com dica para o motivo mais comum; tabela das descartadas para corrigir motivo/detalhe ou **restaurar** a vaga |
| 📈 Mercado | Vagas por semana e fonte, % remotas, nível, modelo de trabalho, dia da semana em que as vagas saem, onde estão as híbridas/presenciais |
| 🧩 Stack e lacunas | O que as vagas pedem, colorido por "você domina / conhece / não tem"; **o que estudar**; distribuição das notas |
| 🏢 Empresas | Quem mais anuncia, nota média e sua situação em cada empresa |
| 📡 Fontes | Qual fonte traz vagas do alvo (e qual é ruído) e a saúde das coletas |

Na página **Vagas**, depois de se candidatar, atualize o **Andamento** (entrevista, proposta, recusado)
e use a **Observação**. Ao descartar (🗑️), uma janela pede o **motivo** (lista fixa, para dar para contar)
e um detalhe opcional. A lista mostra 25 vagas por vez, com "Mostrar mais". Cada mudança fica em `silver.vaga_status_historico`, com data, e é isso que
alimenta o funil, a taxa de resposta e os lembretes.

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

### Como o Python roda

Tudo roda com o ambiente virtual do projeto, `.venv\Scripts\python.exe` (nunca o Python do sistema).
São três peças, e as duas de Python dependem do banco estar no ar:

| O quê | Comando | Como roda |
|---|---|---|
| **Coleta** (pipeline) | `.venv\Scripts\python -m vagas.pipeline` | Sozinha, todo dia às 8h (tarefa `ColetaDiaria`); ou pelo botão "Coletar agora" em Configurações |
| **Painel** (Streamlit, servidor web em `localhost:8501`) | `.venv\Scripts\python -m streamlit run vagas/painel/app.py` | Sozinho ao fazer logon no Windows (tarefa `Painel`); ou pelo atalho "Radar de Vagas" da Área de Trabalho |
| **Banco** (PostgreSQL) | `docker compose up -d` | Docker Desktop, que já inicia com o Windows |

O painel é um servidor que fica no ar: se ninguém o iniciar, `localhost:8501` não abre. O painel **não depende do
Docker para subir**: se o Docker estiver fechado, ele continua no ar e mostra "Banco de dados indisponível",
verificando o banco a cada 5 segundos e voltando ao normal sozinho quando o container responder.

### Execução automática (Windows)

O script `scripts\agendar.ps1` cria duas tarefas no Agendador de Tarefas (pasta `\RadarDeVagas\`):

- **`ColetaDiaria`**: coleta **todo dia às 8h** e, como rede de segurança, **3 minutos depois de fazer logon**
  (recupera uma coleta perdida com o PC desligado). O script abre o Docker Desktop se estiver fechado, garante
  o banco no ar, roda o pipeline e grava o log em `dados/logs/coleta-AAAA-MM-DD.log` (logs com mais de 30 dias
  são apagados). Se já houve uma coleta bem-sucedida há menos de 4 horas, ele pula (`-Forcar` ignora a trava).
- **`Painel`**: sobe o painel ao fazer logon, sem janela, esperando o banco ficar pronto; log em
  `dados/logs/painel.log`. Não abre um segundo servidor se já estiver no ar.

Também cria o atalho **Radar de Vagas** na Área de Trabalho, que inicia o painel (se estiver desligado) e abre
o navegador. A página **Configurações** mostra o horário, a próxima execução e o resultado da última coleta.

```bash
powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1                  # criar/atualizar (08:00)
powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1 -Horario 07:30   # outro horário
powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1 -SemPainel       # só a coleta (remove painel e atalho)
powershell -ExecutionPolicy Bypass -File scripts\coletar.ps1 -Forcar          # coletar agora, à mão
powershell -ExecutionPolicy Bypass -File scripts\painel.ps1                   # iniciar o painel, à mão
```

Para remover tudo: `Unregister-ScheduledTask -TaskPath "\RadarDeVagas\" -TaskName "ColetaDiaria" -Confirm:$false`
e o mesmo com `"Painel"`. As tarefas rodam com o seu usuário e só com você logado no Windows.

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
├── relatorios.py        cálculos dos relatórios (funções puras, testadas)
└── painel/              Streamlit
    ├── app.py           navegação, tema e barra lateral
    ├── paginas/         visao_geral, vagas, candidaturas, sugestoes, relatorios, configuracoes
    ├── ui.py            identidade visual, ícones e componentes (cartões, selos, estados vazios)
    ├── graficos.py      gráficos Altair padronizados
    ├── acoes.py         ações de status e janelas (detalhes, descarte)
    ├── logica.py        regras de apresentação (filtros, classificação da nota, próxima ação)
    └── comum.py         carregamento de dados e estado do pipeline
curriculo/exemplo.yaml   modelo do currículo base
sql/schema.sql           esquemas silver e gold (idempotente)
tests/                   testes das regras de tratamento, nota e sugestões
```

## Privacidade

`.env`, `dados/` e as pastas de currículo ficam fora do Git (ver `.gitignore`).
O código pode ser público sem expor dados pessoais.
