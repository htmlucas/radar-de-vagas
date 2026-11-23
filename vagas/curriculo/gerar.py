"""Gera um currículo adaptado para uma vaga usando a API do Claude.

Divisão de responsabilidades, para o modelo não ter como inventar dados:
  - O Claude decide só o CONTEÚDO adaptável: título, resumo, quais atividades
    destacar e como reescrevê-las, quais projetos mostrar, e as lacunas.
  - O código monta o documento final: nome, contato, empresas, cargos, datas,
    formação e certificações vêm sempre do currículo base, nunca do modelo.
  - Depois, `verificar_invencoes` confere se apareceu alguma tecnologia que
    não existe no currículo base.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import anthropic
import yaml
from pydantic import BaseModel, Field

from vagas.config import RAIZ
from vagas.curriculo import base as curriculo_base
from vagas.tratamento.normalizar import detectar_tecnologias, sem_acento

MODELO = "claude-opus-5-5"
PASTA_GERADOS = RAIZ / "curriculo" / "gerados"


# --------------------------------------------------------------------------- saída do modelo
class ExperienciaAdaptada(BaseModel):
    id: str = Field(description="id da experiência no currículo base (ex.: 'acme')")
    atividades: list[str] = Field(description="atividades reescritas e reordenadas, as mais relevantes primeiro")


class ProjetoAdaptado(BaseModel):
    id: str = Field(description="id do projeto no currículo base")
    descricao: str


class CurriculoAdaptado(BaseModel):
    titulo_profissional: str
    resumo: str
    experiencias: list[ExperienciaAdaptada]
    projetos: list[ProjetoAdaptado]
    competencias_em_destaque: list[str] = Field(description="competências do currículo base que a vaga pede")
    palavras_chave_atendidas: list[str]
    lacunas: list[str] = Field(description="requisitos da vaga que o currículo base NÃO cobre")
    observacoes: str = Field(description="dicas curtas para a candidatura, em português")


SISTEMA = """Você adapta currículos de desenvolvedores para vagas específicas, em português do Brasil.

Regras inegociáveis:
1. Use SOMENTE fatos presentes no currículo base. Você pode reescrever, reordenar, resumir e \
enfatizar, mas nunca acrescentar tecnologias, números, resultados, responsabilidades ou \
experiências que não estejam lá. Na dúvida, deixe de fora.
2. Inclua TODAS as experiências do currículo base, usando exatamente os mesmos ids. Em cada uma, \
coloque primeiro as atividades mais relevantes para a vaga; pode omitir as irrelevantes, mas \
mantenha ao menos duas. No máximo seis atividades por experiência.
3. Atividades começam com verbo no passado ou substantivo de ação, são objetivas e usam os \
termos que a vaga usa quando o currículo base de fato comprova aquilo.
4. Resumo com 3 a 5 frases, focado no que a vaga pede e o candidato comprova.
5. Escolha de 1 a 2 projetos do currículo base, os mais relevantes para a vaga.
6. Em `lacunas`, liste com honestidade os requisitos da vaga que o currículo base não cobre. \
Isso é para o candidato se preparar; não aparece no currículo.
7. Se a descrição da vaga for curta, adapte com o que houver e não especule sobre requisitos \
que não foram informados."""


# --------------------------------------------------------------------------- chamada à API
class FalhaNaGeracao(RuntimeError):
    pass


def _texto_vaga(vaga: dict, descricao_completa: str | None) -> str:
    descricao = (descricao_completa or "").strip() or (vaga.get("descricao") or "").strip()
    partes = [
        f"Cargo: {vaga.get('titulo')}",
        f"Empresa: {vaga.get('empresa') or 'não informada'}",
        f"Nível: {vaga.get('nivel') or 'não informado'}",
        f"Modelo de trabalho: {vaga.get('modelo_trabalho') or 'não informado'}",
        f"Local: {vaga.get('localizacao') or 'não informado'}",
        "",
        "Descrição:",
        descricao or "(sem descrição)",
    ]
    return "<vaga>\n" + "\n".join(partes) + "\n</vaga>\n\nAdapte o currículo base para esta vaga."


def chamar_claude(vaga: dict, base: dict, descricao_completa: str | None = None,
                  cliente: anthropic.Anthropic | None = None) -> tuple[CurriculoAdaptado, dict]:
    cliente = cliente or anthropic.Anthropic()
    base_txt = yaml.safe_dump(
        {k: v for k, v in base.items() if k not in ("contato", "pontuacao")},
        allow_unicode=True, sort_keys=False,
    )
    try:
        resposta = cliente.beta.messages.parse(
            model=MODELO,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # se o modelo recusar, a API tenta outro modelo automaticamente
            output_config={"effort": "high"},
            system=[
                {"type": "text", "text": SISTEMA},
                # O currículo base muda pouco: fica em cache entre vagas diferentes.
                {"type": "text", "text": f"<curriculo_base>\n{base_txt}</curriculo_base>",
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": _texto_vaga(vaga, descricao_completa)}],
            output_format=CurriculoAdaptado,
        )
    except anthropic.AuthenticationError as e:
        raise FalhaNaGeracao("Chave da API do Claude inválida ou ausente (ANTHROPIC_API_KEY no .env).") from e
    except anthropic.RateLimitError as e:
        raise FalhaNaGeracao("Limite de uso da API atingido. Tente de novo em alguns minutos.") from e
    except anthropic.APIConnectionError as e:
        raise FalhaNaGeracao("Sem conexão com a API do Claude.") from e
    except anthropic.APIStatusError as e:
        raise FalhaNaGeracao(f"Erro da API do Claude ({e.status_code}): {e.message}") from e

    if resposta.stop_reason == "refusal":
        raise FalhaNaGeracao("O modelo recusou gerar este currículo.")
    if resposta.stop_reason == "max_tokens" or resposta.parsed_output is None:
        raise FalhaNaGeracao("A resposta veio incompleta. Tente gerar de novo.")

    uso = {
        "modelo": resposta.model,
        "tokens_entrada": resposta.usage.input_tokens,
        "tokens_saida": resposta.usage.output_tokens,
    }
    return resposta.parsed_output, uso


# --------------------------------------------------------------------------- montagem segura
def montar_documento(base: dict, adaptado: CurriculoAdaptado) -> dict:
    """Junta o currículo base (fatos fixos) com o conteúdo adaptado pelo modelo."""
    por_id = {e.id: e for e in adaptado.experiencias}
    experiencias = []
    for exp in base["experiencias"]:  # ordem e dados fixos vêm do currículo base
        adapt = por_id.get(exp["id"])
        atividades = [a.strip() for a in (adapt.atividades if adapt else []) if a.strip()]
        experiencias.append({
            "empresa": exp["empresa"], "cargo": exp["cargo"], "periodo": exp["periodo"],
            "atividades": atividades or exp["atividades"],
        })

    projetos_base = {p["id"]: p for p in base.get("projetos", [])}
    projetos = [
        {"nome": projetos_base[p.id]["nome"], "link": projetos_base[p.id].get("link", ""), "descricao": p.descricao}
        for p in adaptado.projetos if p.id in projetos_base
    ]

    destaque = {sem_acento(c) for c in adaptado.competencias_em_destaque}
    grupos = list((base.get("competencias") or {}).items())
    # Áreas com mais competências pedidas pela vaga aparecem primeiro.
    grupos.sort(key=lambda g: -sum(sem_acento(i) in destaque for i in g[1]))

    return {
        "contato": base["contato"] | {"titulo": adaptado.titulo_profissional},
        "resumo": adaptado.resumo,
        "experiencias": experiencias,
        "projetos": projetos,
        "competencias": dict(grupos),
        "formacao": base.get("formacao", []),
        "certificacoes": base.get("certificacoes", []),
    }


def verificar_invencoes(documento: dict, base: dict) -> list[str]:
    """Tecnologias que aparecem no currículo gerado mas não existem no base."""
    def tudo(d) -> str:
        return json.dumps(d, ensure_ascii=False)

    no_base = set(detectar_tecnologias(tudo(base)))
    gerado = tudo({k: documento[k] for k in ("resumo", "experiencias", "projetos")})
    return sorted(set(detectar_tecnologias(gerado)) - no_base)


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(texto)).strip("-")[:60]


# --------------------------------------------------------------------------- fluxo completo
def gerar(vaga: dict, descricao_completa: str | None = None, cliente=None) -> dict:
    """Gera, salva .docx/.pdf/.json e devolve um resumo do resultado."""
    from vagas.curriculo import render  # import tardio: só carrega docx/fpdf quando precisa

    base = curriculo_base.carregar()
    adaptado, uso = chamar_claude(vaga, base, descricao_completa, cliente)
    documento = montar_documento(base, adaptado)
    invencoes = verificar_invencoes(documento, base)

    nome_pasta = f"{datetime.now():%Y%m%d-%H%M%S}-{_slug(vaga.get('empresa') or '')}-{_slug(vaga['titulo'])}".replace("--", "-")
    pasta: Path = PASTA_GERADOS / nome_pasta
    pasta.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f"Curriculo - {base['contato']['nome']}"
    caminho_docx = render.salvar_docx(documento, pasta / f"{nome_arquivo}.docx")
    caminho_pdf = render.salvar_pdf(documento, pasta / f"{nome_arquivo}.pdf")
    (pasta / "analise.json").write_text(
        json.dumps({
            "vaga": {k: vaga.get(k) for k in ("id", "titulo", "empresa", "url")},
            "palavras_chave_atendidas": adaptado.palavras_chave_atendidas,
            "lacunas": adaptado.lacunas,
            "observacoes": adaptado.observacoes,
            "tecnologias_sem_comprovacao": invencoes,
            "uso": uso,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "pasta": str(pasta), "docx": str(caminho_docx), "pdf": str(caminho_pdf),
        "lacunas": adaptado.lacunas, "observacoes": adaptado.observacoes,
        "palavras_chave": adaptado.palavras_chave_atendidas,
        "invencoes": invencoes, **uso,
    }
