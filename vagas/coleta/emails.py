"""Extrai vagas do HTML de e-mails de alerta (LinkedIn, Indeed, Gupy e outros).

Estratégia genérica, que funciona com a maioria dos alertas:
  1. Procura links que apontam para páginas de vaga de plataformas conhecidas
     (cada plataforma tem um padrão de URL com o id da vaga).
  2. Agrupa os vários links de uma mesma vaga (logo, título, botão "Ver vaga").
  3. Usa o texto do link mais descritivo como título e as linhas de texto
     logo abaixo dele como empresa e local.

Os padrões são ajustados com e-mails reais (modo --descobrir do coletor).
"""

import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from vagas.tratamento.normalizar import montar_vaga

# plataforma -> (regex que acha o id da vaga na URL, URL canônica ou None para manter a original)
PLATAFORMAS = {
    "linkedin": (r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?\"]*-)?(\d{6,})", "https://www.linkedin.com/jobs/view/{id}"),
    "indeed": (r"indeed\.com[^\"]*?[?&](?:jk|vjk)=([0-9a-f]{16})", "https://br.indeed.com/viewjob?jk={id}"),
    "gupy": (r"([a-z0-9-]+\.gupy\.io/jobs?/\d+)", "https://{id}"),
    "glassdoor": (r"glassdoor\.com[^\"]*?(?:jobListingId|jl)=(\d+)", None),
    "catho": (r"catho\.com\.br/vagas/[^\"?#]*?/(\d{5,})", None),
    "infojobs": (r"infojobs\.com\.br/vaga-de-[^\"?#]*?__(\d+)\.aspx", None),
    "programathor": (r"programathor\.com\.br/jobs/(\d+)", "https://programathor.com.br/jobs/{id}"),
    "vagas.com": (r"vagas\.com\.br/vagas/v(\d+)", "https://www.vagas.com.br/vagas/v{id}"),
    "remotar": (r"remotar\.com\.br/job/(\d+)", "https://remotar.com.br/job/{id}"),
}

# Textos de link que não são título de vaga
_GENERICOS = re.compile(
    r"^(ver|veja|visualizar|candidat|aplicar|apply|see|view|saiba|mais|detalhes|confira|acessar|clique|"
    r"vagas semelhantes|similar jobs)",
    re.IGNORECASE,
)
_NOTA_ESTRELAS = re.compile(r"^\d[.,]\d\s*★?$")


# --------------------------------------------------------------------------- formatos por plataforma
# Recebem as linhas de texto DENTRO do link da vaga (quando o cartão inteiro é um link)
# e devolvem (titulo, empresa, local, dias_atras) ou None para usar a regra genérica.

def _cartao_linkedin(linhas: list[str]):
    # ['Desenvolvedor Back-end Jr.', 'Smart NX · Brasil (Remoto)', 'Candidatura simplificada']
    if len(linhas) < 2 or "·" not in linhas[1]:
        return None
    empresa, _, local = (p.strip() for p in linhas[1].partition("·"))
    return linhas[0], empresa or None, local or None, None


def _cartao_glassdoor(linhas: list[str]):
    # ['Multilog', '3.9 ★', 'Desenvolvedor Full Stack', 'Trabalho remoto', 'R$ 6 mil ...', '9 dia(s)']
    resto = [l for l in linhas if not _NOTA_ESTRELAS.match(l)]
    if len(resto) < 3:
        return None
    dias = None
    for l in resto:
        if m := re.match(r"^(\d+)\s*dia", l):
            dias = int(m.group(1))
        elif re.match(r"^\d+\s*h$", l):
            dias = 0
    return resto[1], resto[0], resto[2], dias


FORMATOS_CARTAO = {"linkedin": _cartao_linkedin, "glassdoor": _cartao_glassdoor}


def _destino_real(href: str) -> str:
    """Muitos e-mails embrulham o link num redirecionador de rastreamento
    (ex.: ...?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F123). Desembrulha."""
    href = unquote(unquote(href))
    for valores in parse_qs(urlparse(href).query).values():
        for v in valores:
            if v.startswith("http"):
                return v
    return href


def _identificar(href: str) -> tuple[str, str, str] | None:
    destino = _destino_real(href)
    for plataforma, (padrao, canonica) in PLATAFORMAS.items():
        m = re.search(padrao, destino, re.IGNORECASE)
        if m:
            id_vaga = m.group(1)
            url = canonica.format(id=id_vaga) if canonica else destino.split("#")[0]
            return plataforma, id_vaga, url
    return None


def _linhas_do_bloco(link) -> list[str]:
    """Linhas de texto do menor bloco (célula/linha de tabela/div) que contém o link
    e tem algum conteúdo além dele — normalmente é o "cartão" da vaga."""
    bloco = link
    for _ in range(6):
        bloco = bloco.parent
        if bloco is None:
            return []
        linhas = [l.strip() for l in bloco.get_text("\n").split("\n") if l.strip()]
        if len(linhas) >= 3:
            return linhas
    return []


def _titulo(textos: list[str]) -> str | None:
    candidatos = [t for t in textos if len(t) >= 4 and not _GENERICOS.search(t)]
    return max(candidatos, key=len) if candidatos else None


def extrair_vagas(html: str, remetente: str = "", assunto: str = "", data: str | None = None) -> list[dict]:
    if not html:
        return []
    sopa = BeautifulSoup(html, "html.parser")
    grupos: dict[tuple[str, str], dict] = {}
    for a in sopa.find_all("a", href=True):
        achado = _identificar(a["href"])
        if not achado:
            continue
        plataforma, id_vaga, url = achado
        g = grupos.setdefault((plataforma, id_vaga), {"url": url, "textos": [], "links": [], "cartoes": []})
        texto = " ".join(a.get_text(" ").split())
        if texto:
            g["textos"].append(texto)
        g["links"].append(a)
        g["cartoes"].append([l.strip() for l in a.get_text("\n").split("\n") if l.strip()])

    # Obs.: o assunto do e-mail NÃO é usado para marcar Laravel. No LinkedIn, por exemplo,
    # o assunto é o título da primeira vaga, não o termo do alerta.
    vagas = []
    for (plataforma, id_vaga), g in grupos.items():
        cartao = _ler_cartao(plataforma, g["cartoes"])
        if cartao:
            titulo, empresa, local, dias = cartao
            linhas = max(g["cartoes"], key=len)
            vagas.append(montar_vaga(
                fonte=plataforma, id_externo=id_vaga, titulo=titulo, url=g["url"],
                empresa=empresa, localizacao=local, descricao="\n".join(linhas),
                publicada_em=_menos_dias(data, dias),
                so_titulo=True,
            ))
            continue

        titulo = _titulo(g["textos"])
        if not titulo:
            continue
        linhas = []
        for link in g["links"]:
            linhas = _linhas_do_bloco(link)
            if titulo in linhas:
                break
        depois = linhas[linhas.index(titulo) + 1:] if titulo in linhas else []
        depois = [l for l in depois if not _GENERICOS.search(l)]
        vagas.append(
            montar_vaga(
                fonte=plataforma,
                id_externo=id_vaga,
                titulo=titulo,
                url=g["url"],
                empresa=depois[0] if len(depois) > 0 else None,
                localizacao=depois[1] if len(depois) > 1 else None,
                descricao="\n".join(linhas) or None,
                publicada_em=data,
                so_titulo=True,  # e-mail traz só o cartão da vaga, não a descrição
            )
        )
    return vagas


def _ler_cartao(plataforma: str, cartoes: list[list[str]]):
    """Tenta o formato específico da plataforma em cada link da vaga (o mais completo primeiro)."""
    formato = FORMATOS_CARTAO.get(plataforma)
    if not formato:
        return None
    for linhas in sorted(cartoes, key=len, reverse=True):
        r = formato(linhas)
        if r and r[0] and not _GENERICOS.search(r[0]):
            return r
    return None


def _menos_dias(data_iso: str | None, dias: int | None) -> str | None:
    """Data da vaga = data do e-mail menos a idade informada ("9 dia(s)")."""
    if not data_iso or dias is None:
        return data_iso
    return (datetime.fromisoformat(data_iso) - timedelta(days=dias)).isoformat()
