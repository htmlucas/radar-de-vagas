-- Esquema da trilha de Engenharia de Dados. Idempotente: pode rodar quantas vezes quiser.
--
-- ISOLAMENTO: este arquivo só cria e só mexe em objetos `dados_*` (silver.dados_* e gold.dados_*).
-- Não referencia nenhuma tabela ou visão da trilha Laravel e não há chave estrangeira entre as duas trilhas.
-- É aplicado só pelo pipeline da trilha de dados (nunca por sql/schema.sql, que continua intacto).
-- As únicas visões recriadas a cada execução são gold.dados_vagas_alvo e gold.dados_vagas.

create schema if not exists silver;
create schema if not exists gold;

-- Cada execução de cada coletor da trilha, para auditoria.
create table if not exists silver.dados_execucoes (
    id             bigserial primary key,
    fonte          text        not null,
    iniciada_em    timestamptz not null default now(),
    finalizada_em  timestamptz,
    qtd_coletada   integer,
    qtd_nova       integer,
    arquivo_bronze text,
    erro           text
);

-- Vagas já classificadas e normalizadas (vagas/trilhas/dados/normalizar.py: montar_vaga_dados).
create table if not exists silver.dados_vagas (
    id                    text primary key,                  -- "<fonte>:<id na fonte>"
    fonte                 text        not null,
    id_externo            text        not null,
    titulo                text        not null,
    empresa               text,
    descricao             text,
    url                   text        not null,
    localizacao           text,
    modelo_trabalho       text check (modelo_trabalho in ('remoto', 'hibrido', 'presencial')),
    nivel                 text check (nivel in ('estagio', 'trainee', 'junior', 'pleno', 'senior')),
    categoria_cargo       text        not null
                          check (categoria_cargo in ('engenharia_dados', 'analytics_engineer', 'dev_etl', 'relacionada')),
    tecnologias           text[]      not null default '{}',   -- mencionadas (fora de seções neutras)
    conceitos             text[]      not null default '{}',
    req_obrigatorios      text[]      not null default '{}',
    req_desejaveis        text[]      not null default '{}',
    citados_em_atividades text[]      not null default '{}',   -- só menção: nunca é requisito
    chave_dedupe          text        not null,                -- título + empresa normalizados
    publicada_em          timestamptz,
    so_titulo             boolean     not null default false,  -- alerta de e-mail: só título, sem descrição
    primeira_coleta       timestamptz not null default now(),
    ultima_coleta         timestamptz not null default now(),
    constraint dados_vagas_fonte_externo_uq unique (fonte, id_externo)
);
create index if not exists dados_vagas_publicada_idx  on silver.dados_vagas (publicada_em desc);
create index if not exists dados_vagas_dedupe_idx     on silver.dados_vagas (chave_dedupe);
create index if not exists dados_vagas_categoria_idx  on silver.dados_vagas (categoria_cargo);

-- O que você decidiu sobre cada vaga (separado para a coleta nunca sobrescrever). Sem linha = "nova".
create table if not exists silver.dados_vaga_status (
    vaga_id          text primary key references silver.dados_vagas (id) on delete cascade,
    status           text not null
                     check (status in ('interessa', 'descartada', 'candidatei', 'entrevista', 'proposta', 'recusado')),
    nota             text,                                     -- observação livre
    motivo_descarte  text,
    detalhe_descarte text,
    atualizado_em    timestamptz not null default now()
);

-- Cada mudança de status, com data e motivo (base do funil e do "dias sem retorno"). 'nova' = voltou a não ter status.
create table if not exists silver.dados_vaga_status_historico (
    id      bigserial primary key,
    vaga_id text        not null references silver.dados_vagas (id) on delete cascade,
    status  text        not null,
    em      timestamptz not null default now(),
    motivo  text
);
create index if not exists dados_status_hist_vaga_idx on silver.dados_vaga_status_historico (vaga_id, em);

-- Avaliação da vaga (vagas/trilhas/dados/nota.py: Avaliacao), recalculada a cada coleta.
create table if not exists silver.dados_vaga_pontuacao (
    vaga_id           text primary key references silver.dados_vagas (id) on delete cascade,
    compatibilidade   integer     not null check (compatibilidade between 0 and 100),
    faixa             text        not null check (faixa in ('alta', 'media', 'baixa')),
    parcelas          jsonb       not null default '[]',        -- [{nome, pontos, maximo, detalhe}, ...]
    motivos           text[]      not null default '{}',        -- inclui os alertas (prefixo ⚠️)
    alertas           text[]      not null default '{}',
    confianca_pontos  integer     not null check (confianca_pontos between 0 and 7),
    confianca_nivel   text        not null check (confianca_nivel in ('alta', 'media', 'baixa')),
    confianca_motivos text[]      not null default '{}',
    elegibilidade     text        not null check (elegibilidade in ('ok', 'alerta', 'nao_se_aplica')),
    formacao_exigida  text,                                     -- o que a vaga exige de formação (parcela "formacao")
    calculado_em      timestamptz not null default now()
);

-- As visões gold da trilha são recriadas a cada execução (acompanham colunas novas da silver).
-- Só gold.dados_* são afetadas; nada da trilha Laravel.
drop view if exists gold.dados_vagas_alvo;
drop view if exists gold.dados_vagas;

-- Gold: uma linha por vaga real (a mesma vaga vinda de fontes diferentes aparece uma vez), já com
-- status, avaliação e a coluna `alvo`. Os nomes das colunas de status/avaliação seguem os de gold.vagas
-- (status, nota = observação, compatibilidade, motivos, status_em, motivo_descarte, detalhe_descarte, alvo).
create view gold.dados_vagas as
select distinct on (v.chave_dedupe)
       v.*,
       coalesce(s.status, 'nova') as status,
       s.nota,
       p.compatibilidade,
       p.faixa,
       p.parcelas,
       p.motivos,
       p.alertas,
       p.confianca_pontos,
       p.confianca_nivel,
       p.confianca_motivos,
       p.elegibilidade,
       p.formacao_exigida,
       s.atualizado_em as status_em,
       -- Alvo: categoria de cargo-alvo (nunca 'relacionada') e nível estágio, trainee, júnior ou não informado.
       (v.categoria_cargo in ('engenharia_dados', 'analytics_engineer', 'dev_etl')
        and coalesce(v.nivel, 'junior') in ('estagio', 'trainee', 'junior')) as alvo,
       s.motivo_descarte,
       s.detalhe_descarte
  from silver.dados_vagas v
  left join silver.dados_vaga_status s on s.vaga_id = v.id
  left join silver.dados_vaga_pontuacao p on p.vaga_id = v.id
 -- Entre as cópias da mesma vaga, fica a de cargo-alvo, depois a de descrição mais longa, depois a mais recente.
 order by v.chave_dedupe, (v.categoria_cargo <> 'relacionada') desc, length(coalesce(v.descricao, '')) desc,
          v.publicada_em desc nulls last, v.id;

-- Gold: as vagas-alvo que você não descartou.
create view gold.dados_vagas_alvo as
select *
  from gold.dados_vagas
 where alvo
   and status <> 'descartada';
