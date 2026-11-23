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

create index if not exists vagas_publicada_idx on silver.vagas (publicada_em desc);
create index if not exists vagas_dedupe_idx    on silver.vagas (chave_dedupe);

-- O que você decidiu sobre cada vaga (fica separado para a coleta nunca sobrescrever).
create table if not exists silver.vaga_status (
    vaga_id       text primary key references silver.vagas (id) on delete cascade,
    status        text not null check (status in ('interessa', 'descartada', 'candidatei')),
    nota          text,
    atualizado_em timestamptz not null default now()
);

-- Gold: uma linha por vaga real (remove a mesma vaga vinda de fontes diferentes),
-- já com o status do usuário.
create or replace view gold.vagas as
select distinct on (v.chave_dedupe)
       v.*,
       coalesce(s.status, 'nova') as status,
       s.nota
  from silver.vagas v
  left join silver.vaga_status s on s.vaga_id = v.id
 order by v.chave_dedupe, v.publicada_em desc nulls last;

-- Gold: o alvo do projeto. Laravel, nível júnior/pleno ou não informado, não descartada.
create or replace view gold.vagas_alvo as
select *
  from gold.vagas
 where cita_laravel
   and coalesce(nivel, 'pleno') in ('junior', 'pleno')
   and status <> 'descartada';
