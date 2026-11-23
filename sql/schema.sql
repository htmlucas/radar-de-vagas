-- Esquema do projeto. Idempotente: pode rodar quantas vezes quiser.
-- bronze = arquivos JSON brutos em dados/bronze (fora do banco)
-- silver = vagas limpas e padronizadas
-- gold   = visões prontas para o painel

create schema if not exists silver;
create schema if not exists gold;

-- Cada execução de cada coletor, para auditoria e para o painel mostrar erros.
create table if not exists silver.execucoes (
    id             bigserial primary key,
    fonte          text        not null,
    iniciada_em    timestamptz not null default now(),
    finalizada_em  timestamptz,
    qtd_coletada   integer,
    qtd_nova       integer,
    arquivo_bronze text,
    erro           text
);

create table if not exists silver.vagas (
    id              text primary key,            -- "<fonte>:<id na fonte>"
    fonte           text        not null,
    id_externo      text        not null,
    titulo          text        not null,
    empresa         text,
    descricao       text,
    url             text        not null,
    localizacao     text,
    modelo_trabalho text check (modelo_trabalho in ('remoto', 'hibrido', 'presencial')),
    nivel           text check (nivel in ('junior', 'pleno', 'senior')),
    tecnologias     text[]      not null default '{}',
    cita_laravel    boolean     not null default false,
    chave_dedupe    text        not null,        -- título + empresa normalizados
    publicada_em    timestamptz,
    primeira_coleta timestamptz not null default now(),
    ultima_coleta   timestamptz not null default now()
);

-- Vagas que vieram só com título/empresa/local (alertas de e-mail): sem descrição,
-- não dá para confirmar Laravel. Coluna adicionada depois da criação da tabela.
alter table silver.vagas add column if not exists so_titulo boolean not null default false;

create index if not exists vagas_publicada_idx on silver.vagas (publicada_em desc);
create index if not exists vagas_dedupe_idx    on silver.vagas (chave_dedupe);

-- O que você decidiu sobre cada vaga (fica separado para a coleta nunca sobrescrever).
create table if not exists silver.vaga_status (
    vaga_id       text primary key references silver.vagas (id) on delete cascade,
    status        text not null check (status in ('interessa', 'descartada', 'candidatei')),
    nota          text,
    atualizado_em timestamptz not null default now()
);

-- Andamento da candidatura além de "candidatei" (constraint recriada para aceitar os novos valores).
alter table silver.vaga_status drop constraint if exists vaga_status_status_check;
alter table silver.vaga_status add constraint vaga_status_status_check
    check (status in ('interessa', 'descartada', 'candidatei', 'entrevista', 'proposta', 'recusado'));

-- Por que a vaga foi descartada (motivo de uma lista fixa + detalhe livre).
alter table silver.vaga_status add column if not exists motivo_descarte text;
alter table silver.vaga_status add column if not exists detalhe_descarte text;

-- Histórico de cada mudança de status, com data: base dos relatórios
-- (funil, tempo até candidatar, tempo sem retorno). 'nova' = voltou a não ter status.
create table if not exists silver.vaga_status_historico (
    id      bigserial primary key,
    vaga_id text not null references silver.vagas (id) on delete cascade,
    status  text not null,
    em      timestamptz not null default now()
);
create index if not exists status_hist_vaga_idx on silver.vaga_status_historico (vaga_id, em);
alter table silver.vaga_status_historico add column if not exists motivo text;

-- Status marcados antes do histórico existir entram com a data da última mudança.
insert into silver.vaga_status_historico (vaga_id, status, em)
select s.vaga_id, s.status, s.atualizado_em
  from silver.vaga_status s
 where not exists (select 1 from silver.vaga_status_historico h where h.vaga_id = s.vaga_id);

-- Nota de compatibilidade com o seu perfil (recalculada a cada coleta).
create table if not exists silver.vaga_pontuacao (
    vaga_id         text primary key references silver.vagas (id) on delete cascade,
    compatibilidade integer not null check (compatibilidade between 0 and 100),
    motivos         text[]  not null default '{}',
    calculado_em    timestamptz not null default now()
);

-- Removida: a geração de currículo com IA foi trocada por sugestões locais em texto.
drop table if exists silver.curriculos_gerados;

-- As visões gold são recriadas a cada execução: assim acompanham colunas novas da silver
-- (o "create or replace view" do Postgres não aceita mudar a ordem das colunas).
drop view if exists gold.vagas_alvo;
drop view if exists gold.vagas;

-- Gold: uma linha por vaga real (remove a mesma vaga vinda de fontes diferentes),
-- já com o status do usuário e a nota de compatibilidade.
create view gold.vagas as
select distinct on (v.chave_dedupe)
       v.*,
       coalesce(s.status, 'nova') as status,
       s.nota,
       p.compatibilidade,
       p.motivos,
       s.atualizado_em as status_em,
       -- O alvo do projeto: júnior/pleno (ou nível não informado) e
       -- Laravel confirmado, ou PHP numa vaga que só tem título (alerta de e-mail).
       ((v.cita_laravel or (v.so_titulo and 'PHP' = any(v.tecnologias)))
        and coalesce(v.nivel, 'pleno') in ('junior', 'pleno')) as alvo,
       s.motivo_descarte,
       s.detalhe_descarte
  from silver.vagas v
  left join silver.vaga_status s on s.vaga_id = v.id
  left join silver.vaga_pontuacao p on p.vaga_id = v.id
 -- Entre as cópias da mesma vaga, fica a que confirma Laravel e tem mais texto
 -- (ex.: a da Adzuna, que tem descrição, em vez da do e-mail, que só tem o título).
 order by v.chave_dedupe, v.cita_laravel desc, length(coalesce(v.descricao, '')) desc,
          v.publicada_em desc nulls last;

-- Gold: as vagas do alvo que você não descartou.
create view gold.vagas_alvo as
select *
  from gold.vagas
 where alvo
   and status <> 'descartada';
