"""Gráficos Altair padronizados para todo o painel.

Paleta categórica validada para daltonismo (validador da skill de visualização):
índigo da identidade no 1º lugar; claro e escuro passam em todas as checagens.
Cores seguem a ENTIDADE (cada fonte tem sempre a mesma cor), nunca a posição.
"""

import altair as alt
import pandas as pd
import streamlit as st

PALETAS = {
    "light": {
        "series": ["#4f46e5", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#2a78d6", "#e34948"],
        "texto": "#111827", "texto2": "#4b5563", "apagado": "#6b7280",
        "grade": "#eceef3", "eixo": "#d1d5db", "fundo": "#ffffff",
    },
    "dark": {
        "series": ["#6366f1", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#3987e5", "#e66767"],
        "texto": "#f0efec", "texto2": "#c3c2b7", "apagado": "#898781",
        "grade": "#2c2c2a", "eixo": "#383835", "fundo": "#0e1117",
    },
}
FONTE = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"


def paleta() -> dict:
    tema = getattr(st.context.theme, "type", None) or "light"
    return PALETAS.get(tema, PALETAS["light"])


def estilo(grafico: alt.Chart) -> alt.Chart:
    p = paleta()
    return (
        grafico.configure(background="transparent", font=FONTE,
                          # Margem extra à esquerda: o Vega mede os rótulos com a fonte padrão e depois
                          # desenha com a Inter (mais larga); sem folga, o começo do rótulo corta.
                          padding={"left": 22, "right": 18, "top": 6, "bottom": 4})
        .configure_axis(labelColor=p["apagado"], titleColor=p["texto2"], gridColor=p["grade"],
                        domainColor=p["eixo"], tickColor=p["eixo"], labelFontSize=12,
                        titleFontSize=12, titleFontWeight="normal", labelPadding=6)
        .configure_view(stroke=None)
        .configure_legend(labelColor=p["texto2"], titleColor=p["texto2"], orient="top",
                          labelFontSize=12, symbolType="circle", symbolSize=80)
    )


def cores(dominio: list[str]) -> alt.Scale:
    """Cor fixa por entidade. Passe o domínio COMPLETO para a cor não mudar com filtros.
    Acima de 8 entidades, as excedentes ficam cinza."""
    p = paleta()
    serie = p["series"]
    return alt.Scale(domain=dominio, range=[serie[i] if i < len(serie) else p["apagado"] for i in range(len(dominio))])


def mostrar(grafico: alt.Chart, tabela: pd.DataFrame | None = None, chave: str = "") -> None:
    """Gráfico + a mesma informação em tabela (acessibilidade e números exatos)."""
    st.altair_chart(estilo(grafico), theme=None, width="stretch")
    if tabela is not None:
        with st.expander("Ver em tabela"):
            st.dataframe(tabela, hide_index=True, width="stretch", key=f"tab-{chave}")


def barras(dados: pd.DataFrame, categoria: str, valor: str, titulo_valor: str, *, ordenar=True,
           cor_por: str | None = None, dominio: list[str] | None = None, formato: str = "d",
           dica: list | None = None, largura_rotulo: int = 240, legenda_vertical: bool = False) -> alt.Chart:
    """Barras horizontais finas, ponta arredondada, valor na ponta e dica ao passar o mouse."""
    p = paleta()
    base = alt.Chart(dados)
    # Ordem explícita: em gráfico de camadas (barra + rótulo) o sort="-x" do Vega-Lite é ignorado.
    ordem = list((dados.sort_values(valor, ascending=False) if ordenar else dados)[categoria])
    y = alt.Y(f"{categoria}:N", sort=ordem, title=None,
              axis=alt.Axis(labelLimit=largura_rotulo, ticks=False, domain=False, labelColor=p["texto2"]))
    x = alt.X(f"{valor}:Q", title=titulo_valor, axis=alt.Axis(tickMinStep=1, format=formato))
    # Em espaços estreitos a legenda vai para baixo, um item por linha (não corta o texto)
    legenda = (alt.Legend(title=None, orient="bottom", direction="vertical") if legenda_vertical
               else alt.Legend(title=None))
    cor = (alt.Color(f"{cor_por}:N", scale=cores(dominio), legend=legenda)
           if cor_por else alt.value(p["series"][0]))
    dica = dica or [alt.Tooltip(f"{categoria}:N", title="Item"),
                    alt.Tooltip(f"{valor}:Q", title=titulo_valor, format=formato)]
    barra = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.62}).encode(y=y, x=x, color=cor, tooltip=dica)
    rotulo = base.mark_text(align="left", dx=5, fontSize=12, color=p["texto2"]).encode(
        y=y, x=x, text=alt.Text(f"{valor}:Q", format=formato))
    return (barra + rotulo).properties(height=max(110, 30 * len(dados)))


def _ordem_semanas(semanas: pd.Series) -> list[str]:
    # Todas as semanas do intervalo, inclusive as vazias (senão semanas distantes parecem seguidas)
    return [d.strftime("%d/%m") for d in pd.date_range(semanas.min(), semanas.max(), freq="7D")]


def colunas_semanais(dados: pd.DataFrame, valor: str, titulo: str, cor_por: str | None = None,
                     dominio: list[str] | None = None, altura: int = 260) -> alt.Chart:
    p = paleta()
    semanas = pd.to_datetime(dados["semana"])
    dados = dados.assign(rotulo=semanas.dt.strftime("%d/%m"))
    ordem = _ordem_semanas(semanas)
    x = alt.X("rotulo:O", sort=ordem, scale=alt.Scale(domain=ordem), title="Semana iniciada em",
              axis=alt.Axis(labelAngle=0))
    y = alt.Y(f"sum({valor}):Q", title=titulo, axis=alt.Axis(tickMinStep=1))
    if cor_por:
        cor = alt.Color(f"{cor_por}:N", scale=cores(dominio), legend=alt.Legend(title=None))
        marca = alt.Chart(dados).mark_bar(stroke=p["fundo"], strokeWidth=2, size=30)  # 2px separam segmentos
        dica = [alt.Tooltip("rotulo:N", title="Semana de"), alt.Tooltip(f"{cor_por}:N", title="Fonte"),
                alt.Tooltip(f"{valor}:Q", title=titulo)]
    else:
        cor = alt.value(p["series"][0])
        marca = alt.Chart(dados).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=30)
        dica = [alt.Tooltip("rotulo:N", title="Semana de"), alt.Tooltip(f"{valor}:Q", title=titulo)]
    return marca.encode(x=x, y=y, color=cor, tooltip=dica).properties(height=altura)


def linhas_semanais(dados: pd.DataFrame, series: list[str], titulo: str, altura: int = 250) -> alt.Chart:
    """Linhas por semana para séries na MESMA unidade (um eixo só), com pontos e dica."""
    p = paleta()
    semanas = pd.to_datetime(dados["semana"])
    longo = dados.assign(rotulo=semanas.dt.strftime("%d/%m")).melt(
        id_vars=["semana", "rotulo"], value_vars=series, var_name="serie", value_name="vagas")
    ordem = _ordem_semanas(semanas)
    x = alt.X("rotulo:O", sort=ordem, scale=alt.Scale(domain=ordem), title=None, axis=alt.Axis(labelAngle=0))
    y = alt.Y("vagas:Q", title=titulo, axis=alt.Axis(tickMinStep=1))
    cor = alt.Color("serie:N", scale=cores(series), legend=alt.Legend(title=None))
    dica = [alt.Tooltip("rotulo:N", title="Semana de"), alt.Tooltip("serie:N", title="Série"),
            alt.Tooltip("vagas:Q", title="Vagas")]
    base = alt.Chart(longo).encode(x=x, y=y, color=cor, tooltip=dica)
    return (base.mark_line(strokeWidth=2) + base.mark_point(size=60, filled=True, stroke=p["fundo"],
                                                            strokeWidth=2)).properties(height=altura)
