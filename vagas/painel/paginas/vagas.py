"""Página Vagas: busca, filtros e lista de oportunidades (a tela mais usada)."""

from datetime import date

import pandas as pd
import streamlit as st

from vagas.painel import logica, ui
from vagas.painel.acoes import acoes_rapidas
from vagas.painel.comum import FUSO, carregar_base, carregar_vagas, quando
from vagas.painel.horario import adicionada_ao_radar
from vagas.painel.logica import ORDENACOES, SEM_MODALIDADE, Filtros

POR_BLOCO = 25
MODALIDADES = ["remoto", "hibrido", "presencial", SEM_MODALIDADE]
ROTULO_MODALIDADE = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial",
                     SEM_MODALIDADE: "Não informada"}
NIVEIS = ["junior", "pleno", "senior", SEM_MODALIDADE]
ROTULO_NIVEL = {"junior": "Júnior", "pleno": "Pleno", "senior": "Sênior", SEM_MODALIDADE: "Não informado"}
PERIODOS = {7: "Últimos 7 dias", 30: "Últimos 30 dias", 90: "Últimos 90 dias", 365: "Último ano", None: "Qualquer data"}

MODOS = {"dia": "Por dia", "periodo": "Por período"}
PERIODO_PADRAO = 90

# Padrão: as vagas que o radar encontrou no dia (hoje, ou o último dia com vagas), remoto em destaque
# (e as que não informam a modalidade, para não esconder boas vagas), só o que ainda precisa de
# decisão (novas e com interesse), dentro do seu perfil.
CHAVES = {"busca": "f_busca", "so_perfil": "f_perfil", "modalidades": "f_modal",
          "niveis": "f_nivel", "tecnologias": "f_tec", "fontes": "f_fontes", "status": "f_status"}


def _padrao(dia: date) -> Filtros:
    return Filtros(modalidades=["remoto", SEM_MODALIDADE], status=["nova", "interessa"], dias=None, dia=dia)


def _restaurar_padrao(dia: date) -> None:
    padrao = _padrao(dia)
    for campo, chave in CHAVES.items():
        valor = getattr(padrao, campo)
        st.session_state[chave] = list(valor) if isinstance(valor, list) else valor
    st.session_state["f_modo"] = "dia"
    st.session_state["f_dia"] = dia
    st.session_state["f_dias"] = PERIODO_PADRAO
    st.session_state["f_ordem"] = "compatibilidade"


def _filtros_atuais() -> Filtros:
    valores = {campo: st.session_state[chave] for campo, chave in CHAVES.items()}
    if st.session_state["f_modo"] == "dia":
        return Filtros(**valores, dias=None, dia=st.session_state["f_dia"])
    return Filtros(**valores, dias=st.session_state["f_dias"], dia=None)


def _escolher_data() -> None:
    if st.session_state.get("f_dia_cal"):
        st.session_state["f_dia"] = st.session_state["f_dia_cal"]


def _rotulo_dia(d: date, contagem: dict) -> str:
    hoje = pd.Timestamp.now(tz=FUSO).date()
    nome = "Hoje" if d == hoje else "Ontem" if (hoje - d).days == 1 else d.strftime("%d/%m")
    return f"{nome} · {contagem.get(d, 0)}"


def _seletor_de_data(df) -> None:
    """Linha de cima da barra: ver por dia (padrão) ou por período de publicação."""
    m, resto = st.columns([2.2, 7.7], vertical_alignment="bottom")
    m.segmented_control("Ver vagas", list(MODOS), key="f_modo", format_func=MODOS.get, required=True,
                        help="Por dia: as vagas que o radar encontrou em um dia. "
                             "Por período: pela data de publicação da vaga.")
    with resto:
        if st.session_state["f_modo"] == "dia":
            escopo = df[df["alvo"]] if st.session_state["f_perfil"] else df
            recentes = logica.dias_com_vagas(escopo, limite=7)
            contagem = dict(logica.dias_com_vagas(escopo, limite=1000))
            opcoes = [d for d, _ in recentes]
            if st.session_state["f_dia"] not in opcoes:
                opcoes.append(st.session_state["f_dia"])
            d1, d2 = st.columns([6, 1.4], vertical_alignment="bottom")
            d1.pills("Encontradas no dia", opcoes, key="f_dia", required=True,
                     format_func=lambda d: _rotulo_dia(d, contagem),
                     help="Dias em que o radar encontrou vagas (no seu escopo), com a quantidade.")
            with d2.popover("Outra data", icon=":material/calendar_month:", width="stretch"):
                st.date_input("Escolha o dia", value=st.session_state["f_dia"], key="f_dia_cal",
                              format="DD/MM/YYYY", on_change=_escolher_data,
                              max_value=pd.Timestamp.now(tz=FUSO).date())
        else:
            st.selectbox("Publicadas", list(PERIODOS), key="f_dias", format_func=PERIODOS.get)


def _mostrar_mais() -> None:
    st.session_state["limite_vagas"] += POR_BLOCO


def _barra_de_filtros(df, dia_padrao: date) -> Filtros:
    with st.container(border=True):
        c1, c2, c3 = st.columns([6, 2.4, 1.5], vertical_alignment="bottom")
        c1.text_input("Buscar", key="f_busca", icon=":material/search:", label_visibility="collapsed",
                      placeholder="Buscar por cargo, empresa ou tecnologia (ex.: Laravel, filas, BairesDev)")
        c2.selectbox("Ordenar por", list(ORDENACOES), key="f_ordem", label_visibility="collapsed",
                     format_func=lambda k: ORDENACOES[k][0])
        ativos = logica.filtros_ativos(_filtros_atuais(), _padrao(dia_padrao))
        c3.button("Limpar" + (f" ({ativos})" if ativos else ""), icon=":material/filter_alt_off:",
                  on_click=_restaurar_padrao, args=(dia_padrao,), width="stretch", disabled=not ativos,
                  help="Volta todos os filtros para o padrão (vagas encontradas no dia mais recente)")

        _seletor_de_data(df)

        r1, r2, r3 = st.columns([3.3, 5, 1.5], vertical_alignment="bottom")
        r1.pills("Modalidade", MODALIDADES, selection_mode="multi", key="f_modal",
                 format_func=ROTULO_MODALIDADE.get, wrap=True)
        r2.pills("Status", list(ui.STATUS_UI), selection_mode="multi", key="f_status",
                 format_func=lambda s: ui.STATUS_UI[s][0], wrap=True)
        r3.toggle("Só meu perfil", key="f_perfil",
                  help="Laravel júnior/pleno (e PHP vindo de alertas por e-mail, que só trazem o título).")

        atuais = _filtros_atuais()
        extras = sum(bool(getattr(atuais, c)) for c in ("niveis", "tecnologias", "fontes"))
        with st.expander("Mais filtros" + (f" · {extras} ativo(s)" if extras else ""), icon=":material/tune:"):
            m1, m2, m3 = st.columns(3)
            m1.multiselect("Nível", NIVEIS, key="f_nivel", format_func=ROTULO_NIVEL.get, placeholder="Todos")
            tecs = sorted({t for ts in df["tecnologias"] for t in ts})
            m2.multiselect("Tecnologia", tecs, key="f_tec", placeholder="Todas")
            fontes = sorted({f for fs in df["fontes"] for f in fs})
            m3.multiselect("Fonte", fontes, key="f_fontes", placeholder="Todas",
                           format_func=lambda f: ui.FONTE_UI.get(f, (f,))[0])
    return _filtros_atuais()


def _info_vaga(v: dict, dominio: set) -> str:
    modal, ic_modal = ui.MODALIDADE_UI.get(v.get("modelo_trabalho"), ui.MODALIDADE_UI[None])
    nivel = ui.NIVEL_UI.get(v.get("nivel"), "Nível não informado")
    local = f'<span>·</span><span>{ui.esc(v["localizacao"])}</span>' if v.get("localizacao") else ""
    rotulo_data = "Recebida por e-mail" if v["fonte"] == "linkedin" and v.get("so_titulo") else "Publicada"
    fontes = v.get("fontes") or [v["fonte"]]
    nomes_fontes = ", ".join(ui.FONTE_UI.get(f, (f,))[0] for f in fontes)
    rotulo_fontes = f"{len(fontes)} fontes: {nomes_fontes}" if len(fontes) > 1 else nomes_fontes
    partes = [
        f'<div class="rv-vaga-tit"><a href="{ui.url_segura(v["url"])}" target="_blank" rel="noopener noreferrer">'
        f'{ui.esc(v["titulo"])}</a></div>',
        f'<div class="rv-vaga-emp">{ui.icone("building-2", 15, "#4b5563")}<span>{ui.esc(v.get("empresa") or "Empresa não identificada")}</span>{local}</div>',
        f'<div class="rv-badges">{ui.badge_status(v["status"])}{ui.badge(modal, "neutro", ic_modal)}'
        f'{ui.badge(nivel, "neutro", "award")}</div>',
        ui.chips(v.get("tecnologias"), destaque=dominio),
        '<div class="rv-metas">'
        + ui.meta("calendar", f"{rotulo_data} {quando(v.get('publicada_em'))}")
        + ui.meta("radar", adicionada_ao_radar(v.get("primeira_coleta")))
        + ui.meta("layers", ui.esc(rotulo_fontes))
        + (ui.meta("clock", f"{ui.STATUS_UI[v['status']][0]} {quando(v.get('status_em'))}") if v["status"] != "nova" else "")
        + "</div>",
    ]
    if v.get("so_titulo") and not v.get("cita_laravel"):
        partes.append(f'<div class="rv-aviso">{ui.icone("mail", 14, "#b45309")}<span>Veio de um alerta por e-mail, só com o título: '
                      'confirme na vaga se pede Laravel.</span></div>')
    if v["status"] == "descartada":
        motivo = ui.esc(v.get("motivo_descarte") or "sem motivo registrado")
        detalhe = f" — {ui.esc(v['detalhe_descarte'])}" if v.get("detalhe_descarte") else ""
        partes.append(f'<div class="rv-aviso" style="color:#4b5563">{ui.icone("trash-2", 14, "#4b5563")}'
                      f'<span>Descartada: {motivo}{detalhe}</span></div>')
    return "".join(partes)


def card_vaga(v: dict, indice: int, dominio: set) -> None:
    rotulo, tom = logica.classificar_nota(v.get("compatibilidade"))
    with st.container(border=True, key=f"vaga-{indice}"):
        c_nota, c_info, c_acoes = st.columns([1.05, 6.2, 1.9], gap="medium")
        c_nota.html(ui.nota_bloco(v.get("compatibilidade"), rotulo, tom))
        c_info.html(_info_vaga(v, dominio))
        with c_acoes:
            acoes_rapidas(v, "lv")


def pagina() -> None:
    df = carregar_vagas()
    if df.empty:
        ui.cabecalho("Vagas", "Oportunidades encontradas pelo radar.", "briefcase-business")
        ui.vazio("Nenhuma vaga coletada ainda",
                 "Vá em <b>Configurações</b> e clique em <b>Coletar agora</b> para buscar as primeiras vagas.",
                 "inbox")
        return

    dia_padrao = logica.dia_padrao(df)
    if "f_modo" not in st.session_state:
        _restaurar_padrao(dia_padrao)
    no_perfil = int((df["alvo"] & (df["status"] != "descartada")).sum())
    ui.cabecalho("Vagas", f"{len(df)} oportunidades no radar · <b>{no_perfil}</b> dentro do seu perfil",
                 "briefcase-business")

    filtros = _barra_de_filtros(df, dia_padrao)
    resultado = logica.ordenar(logica.filtrar_vagas(df, filtros), st.session_state["f_ordem"])

    if filtros.dia:
        hoje = pd.Timestamp.now(tz=FUSO).date()
        ui.secao(f"Vagas encontradas em {filtros.dia:%d/%m/%Y}" + (" (hoje)" if filtros.dia == hoje else ""),
                 "calendar")
        if filtros.dia == dia_padrao and dia_padrao != hoje:
            st.caption("O radar ainda não encontrou vagas hoje: mostrando o último dia com vagas. "
                       "Rode a coleta em Configurações para buscar as de hoje.")

    # Paginação: mudar qualquer filtro volta para o primeiro bloco
    assinatura = (tuple(sorted(vars(filtros).items(), key=str)).__repr__(), st.session_state["f_ordem"])
    if st.session_state.get("assinatura_vagas") != assinatura:
        st.session_state["assinatura_vagas"] = assinatura
        st.session_state["limite_vagas"] = POR_BLOCO
    limite = st.session_state["limite_vagas"]

    if resultado.empty:
        dica = ("Escolha outro dia, troque para <b>Por período</b> ou inclua outras modalidades e status."
                if filtros.dia else
                "Tente incluir outras modalidades ou status, aumentar o período ou clique em <b>Limpar</b>.")
        ui.vazio("Nenhuma vaga com esses filtros", dica, "search")
        return

    st.caption(f"**{len(resultado)}** vaga(s) · ordenadas por {ORDENACOES[st.session_state['f_ordem']][0].lower()}")
    dominio = set((carregar_base() or {}).get("pontuacao", {}).get("dominio", []))
    for i, (_, v) in enumerate(resultado.head(limite).iterrows()):
        card_vaga(v.to_dict(), i, dominio)

    if len(resultado) > limite:
        st.caption(f"Mostrando {limite} de {len(resultado)} vagas.")
        st.button(f"Mostrar mais {min(POR_BLOCO, len(resultado) - limite)}", icon=":material/expand_more:",
                  on_click=_mostrar_mais, width="stretch")
