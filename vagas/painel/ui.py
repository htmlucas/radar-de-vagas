"""Componentes visuais compartilhados: identidade, ícones Lucide, cartões, selos e estados vazios.

Tudo que vem dos dados (títulos, empresas, descrições) passa por `esc()` antes de virar HTML:
esse conteúdo chega de e-mails e sites de terceiros.
"""

import base64
import html
from functools import lru_cache
from pathlib import Path

import streamlit as st

PASTA_ICONES = Path(__file__).parent / "icones"

# Tons semânticos: (fundo, texto, borda). Texto com contraste AA sobre o fundo.
TONS = {
    "neutro": ("#f3f4f6", "#374151", "#e5e7eb"),
    "primario": ("#eef2ff", "#4338ca", "#c7d2fe"),
    "sucesso": ("#ecfdf3", "#047857", "#a7f3d0"),
    "atencao": ("#fffbeb", "#b45309", "#fde68a"),
    "erro": ("#fef2f2", "#b91c1c", "#fecaca"),
    "info": ("#eff6ff", "#1d4ed8", "#bfdbfe"),
}

STATUS_UI = {
    "nova": ("Nova", "neutro", "circle-dot"),
    "interessa": ("Interesse", "atencao", "star"),
    "candidatei": ("Candidatei", "primario", "send"),
    "entrevista": ("Entrevista", "info", "message-square"),
    "proposta": ("Proposta", "sucesso", "award"),
    "recusado": ("Recusado", "erro", "circle-x"),
    "descartada": ("Descartada", "neutro", "trash-2"),
}
MODALIDADE_UI = {
    "remoto": ("Remoto", "house"),
    "hibrido": ("Híbrido", "building-2"),
    "presencial": ("Presencial", "map-pin"),
    None: ("Modalidade não informada", "circle-dot"),
}
NIVEL_UI = {"junior": "Júnior", "pleno": "Pleno", "senior": "Sênior", None: "Nível não informado"}
FONTE_UI = {
    "adzuna": ("Adzuna", "globe"),
    "github": ("GitHub", "github"),
    "linkedin": ("LinkedIn", "mail"),
    "glassdoor": ("Glassdoor", "mail"),
    "indeed": ("Indeed", "mail"),
}


def esc(texto) -> str:
    return html.escape("" if texto is None else str(texto))


def url_segura(url) -> str:
    u = str(url or "")
    return esc(u) if u.startswith(("http://", "https://")) else "#"


# --------------------------------------------------------------------------- ícones
COR_APAGADA = "#6b7280"
COR_PRIMARIA = "#4f46e5"


@lru_cache(maxsize=None)
def _svg(nome: str) -> str:
    arquivo = PASTA_ICONES / f"{nome}.svg"
    if not arquivo.exists():
        arquivo = PASTA_ICONES / "circle-dot.svg"
    texto = arquivo.read_text(encoding="utf-8")
    return texto[texto.index("<svg"):].replace("\n", " ")


@lru_cache(maxsize=None)
def icone(nome: str, tamanho: int = 16, cor: str = COR_APAGADA) -> str:
    """Ícone Lucide como imagem SVG embutida.

    O st.html remove tags <svg> por segurança, mas aceita <img> com data URI. Como imagem
    não herda a cor do texto, a cor vai "assada" no traço do ícone.
    """
    svg = _svg(nome).replace('stroke="currentColor"', f'stroke="{cor}"')
    dados = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<img class="rv-ic" src="data:image/svg+xml;base64,{dados}" width="{tamanho}" '
            f'height="{tamanho}" alt="" aria-hidden="true">')


def cor_do_tom(tom: str) -> str:
    return TONS.get(tom, TONS["neutro"])[1]


# --------------------------------------------------------------------------- peças em HTML
def badge(texto: str, tom: str = "neutro", nome_icone: str | None = None, titulo: str | None = None) -> str:
    ic = icone(nome_icone, 13, cor_do_tom(tom)) if nome_icone else ""
    dica = f' title="{esc(titulo)}"' if titulo else ""
    return f'<span class="rv-badge rv-tom-{tom}"{dica}>{ic}{esc(texto)}</span>'


def badge_status(status: str) -> str:
    rotulo, tom, ic = STATUS_UI.get(status, STATUS_UI["nova"])
    return badge(rotulo, tom, ic)


def chips(itens, destaque: set | None = None, maximo: int = 8) -> str:
    itens = list(itens or [])
    destaque = destaque or set()
    partes = [f'<span class="rv-chip{" rv-chip-on" if i in destaque else ""}">{esc(i)}</span>' for i in itens[:maximo]]
    if len(itens) > maximo:
        partes.append(f'<span class="rv-chip rv-chip-mais">+{len(itens) - maximo}</span>')
    return f'<div class="rv-chips">{"".join(partes)}</div>' if partes else ""


def nota_bloco(n, rotulo: str, tom: str, compacto: bool = False) -> str:
    valor = "—" if n is None or n != n else int(n)
    classe = "rv-nota rv-nota-compacta" if compacto else "rv-nota"
    return (f'<div class="{classe} rv-tom-{tom}" title="Compatibilidade {valor}/100 ({esc(rotulo)})">'
            f'<div class="rv-nota-num">{valor}</div><div class="rv-nota-rot">{esc(rotulo)}</div></div>')


def meta(nome_icone: str, texto: str) -> str:
    return f'<span class="rv-meta">{icone(nome_icone, 14, COR_APAGADA)}{texto}</span>'


# --------------------------------------------------------------------------- blocos de página
def html_bloco(conteudo: str) -> None:
    st.html(conteudo)


def cabecalho(titulo: str, descricao: str, nome_icone: str) -> None:
    st.html(
        f'<div class="rv-header"><div class="rv-header-ic">{icone(nome_icone, 22, "#4338ca")}</div>'
        f'<div><h1 class="rv-h1">{esc(titulo)}</h1><p class="rv-sub">{descricao}</p></div></div>'
    )


def secao(titulo: str, nome_icone: str | None = None, descricao: str | None = None) -> None:
    ic = f'<span class="rv-secao-ic">{icone(nome_icone, 18, COR_PRIMARIA)}</span>' if nome_icone else ""
    desc = f'<p class="rv-secao-desc">{descricao}</p>' if descricao else ""
    st.html(f'<div class="rv-secao"><h3>{ic}{esc(titulo)}</h3>{desc}</div>')


def kpis(itens: list[dict]) -> None:
    """Cartões de indicador em grade responsiva. Cada item: rotulo, valor, icone, tom?, detalhe?, ajuda?"""
    cartoes = []
    for k in itens:
        tom = k.get("tom", "primario")
        ajuda = f' title="{esc(k["ajuda"])}"' if k.get("ajuda") else ""
        detalhe = f'<div class="rv-kpi-det">{k["detalhe"]}</div>' if k.get("detalhe") else ""
        cartoes.append(
            f'<div class="rv-kpi"{ajuda}><div class="rv-kpi-top">'
            f'<span class="rv-kpi-ic rv-tom-{tom}">{icone(k["icone"], 18, cor_do_tom(tom))}</span>'
            f'<span class="rv-kpi-rot">{esc(k["rotulo"])}</span></div>'
            f'<div class="rv-kpi-val">{esc(k["valor"])}</div>{detalhe}</div>'
        )
    st.html(f'<div class="rv-kpis">{"".join(cartoes)}</div>')


def vazio(titulo: str, texto: str, nome_icone: str = "inbox") -> None:
    st.html(f'<div class="rv-vazio"><div class="rv-vazio-ic">{icone(nome_icone, 28, "#9ca3af")}</div>'
            f'<div class="rv-vazio-tit">{esc(titulo)}</div><div class="rv-vazio-txt">{texto}</div></div>')


def lista_itens(itens: list[str], nome_icone: str, tom: str) -> str:
    linhas = "".join(f'<li><span class="rv-li-ic rv-tom-{tom}">{icone(nome_icone, 13, cor_do_tom(tom))}</span>'
                     f'<span>{esc(i)}</span></li>' for i in itens)
    return f'<ul class="rv-lista">{linhas}</ul>'


# --------------------------------------------------------------------------- estilo global
CSS = """
<style>
:root {
  --rv-primario: #4f46e5; --rv-primario-escuro: #4338ca; --rv-primario-claro: #eef2ff;
  --rv-borda: #e5e7eb; --rv-borda-forte: #d1d5db; --rv-texto: #111827; --rv-texto-2: #4b5563;
  --rv-apagado: #6b7280; --rv-fundo: #f6f7fb; --rv-cartao: #ffffff;
  --rv-sombra: 0 1px 2px rgba(16, 24, 40, .05), 0 1px 3px rgba(16, 24, 40, .04);
  --rv-raio: 12px;
}
/* Topo com folga: com a barra lateral recolhida o cabeçalho do Streamlit cobre o início da página */
.block-container { padding-top: 3.8rem; padding-bottom: 4rem; max-width: 1260px; }
h1, h2, h3 { letter-spacing: -0.01em; }

/* Contêineres com borda viram cartões brancos */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
  background: var(--rv-cartao); box-shadow: var(--rv-sombra);
}
[class*="st-key-vaga-"] { transition: border-color .15s ease; }
[class*="st-key-vaga-"]:hover { border-color: #c7d2fe !important; }

/* Cabeçalho de página */
.rv-header { display: flex; gap: 14px; align-items: center; margin: 0 0 18px; }
.rv-header-ic { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center;
  background: var(--rv-primario-claro); color: var(--rv-primario-escuro); flex: none; }
.rv-h1 { font-size: 1.6rem; font-weight: 700; margin: 0; padding: 0; line-height: 1.2; color: var(--rv-texto); }
.rv-sub { margin: 2px 0 0; color: var(--rv-apagado); font-size: .93rem; }

/* Título de seção */
.rv-secao { margin: 6px 0 6px; }
.rv-secao h3 { font-size: 1.05rem; font-weight: 650; margin: 0; padding: 0; display: flex; align-items: center;
  gap: 8px; color: var(--rv-texto); }
.rv-secao-ic { color: var(--rv-primario); display: inline-flex; }
.rv-secao-desc { margin: 2px 0 0; color: var(--rv-apagado); font-size: .86rem; }

/* Indicadores */
.rv-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 4px 0 8px; }
.rv-kpi { background: var(--rv-cartao); border: 1px solid var(--rv-borda); border-radius: var(--rv-raio);
  padding: 14px 16px; box-shadow: var(--rv-sombra); }
.rv-kpi-top { display: flex; align-items: center; gap: 8px; }
.rv-kpi-ic { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; flex: none; }
.rv-kpi-rot { color: var(--rv-texto-2); font-size: .84rem; font-weight: 500; line-height: 1.2; }
.rv-kpi-val { font-size: 1.75rem; font-weight: 700; color: var(--rv-texto); margin-top: 8px; line-height: 1.1; }
.rv-kpi-det { color: var(--rv-apagado); font-size: .8rem; margin-top: 4px; }

/* Selos, chips e metadados */
.rv-badge { display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px; border-radius: 999px;
  font-size: .76rem; font-weight: 550; border: 1px solid transparent; white-space: nowrap; line-height: 1.6; }
.rv-tom-neutro   { background: #f3f4f6; color: #374151; border-color: #e5e7eb; }
.rv-tom-primario { background: #eef2ff; color: #4338ca; border-color: #c7d2fe; }
.rv-tom-sucesso  { background: #ecfdf3; color: #047857; border-color: #a7f3d0; }
.rv-tom-atencao  { background: #fffbeb; color: #b45309; border-color: #fde68a; }
.rv-tom-erro     { background: #fef2f2; color: #b91c1c; border-color: #fecaca; }
.rv-tom-info     { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
.rv-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 2px; }
.rv-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.rv-chip { font-size: .74rem; padding: 1px 8px; border-radius: 6px; background: #f9fafb; color: #374151;
  border: 1px solid var(--rv-borda); font-weight: 500; }
.rv-chip-on { background: #eef2ff; color: #4338ca; border-color: #c7d2fe; }
.rv-chip-mais { color: var(--rv-apagado); }
.rv-meta { display: inline-flex; align-items: center; gap: 5px; color: var(--rv-apagado); font-size: .8rem; }
.rv-metas { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 10px; }
.rv-ic { flex: none; vertical-align: middle; }

/* Card de vaga */
.rv-vaga-tit { font-size: 1.02rem; font-weight: 650; line-height: 1.35; margin: 0; }
.rv-vaga-tit a { color: var(--rv-texto); text-decoration: none; }
.rv-vaga-tit a:hover { color: var(--rv-primario); text-decoration: underline; }
.rv-vaga-emp { display: flex; align-items: center; gap: 6px; color: var(--rv-texto-2); font-size: .88rem; margin-top: 3px; }
.rv-aviso { display: flex; gap: 6px; align-items: flex-start; font-size: .8rem; color: #b45309; margin-top: 8px; }

/* Nota de compatibilidade */
.rv-nota { border-radius: 12px; padding: 10px 6px; text-align: center; border: 1px solid; min-width: 64px; }
.rv-nota-num { font-size: 1.6rem; font-weight: 750; line-height: 1; }
.rv-nota-rot { font-size: .72rem; font-weight: 600; margin-top: 4px; text-transform: uppercase; letter-spacing: .04em; }
.rv-nota-compacta { padding: 6px 4px; min-width: 52px; border-radius: 10px; }
.rv-nota-compacta .rv-nota-num { font-size: 1.15rem; }
.rv-nota-compacta .rv-nota-rot { font-size: .62rem; margin-top: 2px; }

/* Listas com ícone (pontos positivos / atenção) */
.rv-lista { list-style: none; padding: 0; margin: 4px 0 0; }
.rv-lista li { display: flex; gap: 8px; align-items: flex-start; padding: 4px 0; font-size: .88rem; color: var(--rv-texto); }
.rv-li-ic { width: 20px; height: 20px; border-radius: 6px; display: grid; place-items: center; flex: none; margin-top: 1px; }

/* Estado vazio */
.rv-vazio { text-align: center; padding: 28px 16px; color: var(--rv-apagado); border: 1px dashed var(--rv-borda-forte);
  border-radius: var(--rv-raio); background: #fbfbfd; }
.rv-vazio-ic { color: #9ca3af; display: inline-grid; }
.rv-vazio-tit { font-weight: 600; color: var(--rv-texto-2); margin-top: 6px; }
.rv-vazio-txt { font-size: .86rem; margin-top: 2px; }

/* Linha compacta (listas da visão geral) */
.rv-linha { display: flex; gap: 12px; align-items: center; }
.rv-linha-txt { min-width: 0; }
.rv-linha-tit { font-weight: 600; font-size: .92rem; color: var(--rv-texto); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rv-linha-tit a { color: inherit; text-decoration: none; }
.rv-linha-tit a:hover { color: var(--rv-primario); text-decoration: underline; }
.rv-linha-sub { font-size: .8rem; color: var(--rv-apagado); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Kanban */
.rv-kan-cab { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.rv-kan .rv-badge { white-space: normal; align-items: flex-start; border-radius: 8px; }
.rv-kan .rv-linha-tit { white-space: normal; }

/* Rodapé da sidebar */
.rv-usuario { display: flex; gap: 10px; align-items: center; padding: 10px; border: 1px solid var(--rv-borda);
  border-radius: 10px; background: #fafafa; }
.rv-avatar { width: 34px; height: 34px; border-radius: 999px; background: var(--rv-primario); color: #fff;
  display: grid; place-items: center; font-weight: 650; font-size: .85rem; flex: none; }
.rv-usuario-nome { font-weight: 600; font-size: .86rem; color: var(--rv-texto); line-height: 1.2; }
.rv-usuario-sub { font-size: .74rem; color: var(--rv-apagado); line-height: 1.3; }
.rv-coleta { margin-top: 8px; font-size: .76rem; color: var(--rv-apagado); display: flex; gap: 6px; align-items: center; }
.rv-ponto { width: 8px; height: 8px; border-radius: 999px; flex: none; }

/* Blocos copiáveis (st.code) com texto corrido: Inter em vez de monoespaçada */
[data-testid="stCode"] pre, [data-testid="stCode"] code {
  font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif !important; font-size: .9rem; line-height: 1.55;
}
[data-testid="stCode"] pre { background: #f9fafb !important; border: 1px solid var(--rv-borda); }

/* Abas */
[data-baseweb="tab-list"] { gap: 4px; }
[data-baseweb="tab"] { font-weight: 550; }

/* Telas estreitas */
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 3.6rem; }
  .rv-h1 { font-size: 1.3rem; }
  .rv-kpi-val { font-size: 1.45rem; }
}
</style>
"""


def aplicar_estilo() -> None:
    st.html(CSS)
