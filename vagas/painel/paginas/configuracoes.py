"""Configurações e monitoramento: coleta, estado das fontes, camadas do pipeline e integrações.
Nunca mostra valores de chaves/tokens: só se estão configurados."""

import pandas as pd
import streamlit as st

from vagas import db
from vagas.coleta import gmail
from vagas.config import config
from vagas.painel import ui
from vagas.painel.comum import (
    FONTES_COLETA, FUSO, agendamento, carregar_base, estado_pipeline, ha_quanto, limpar_cache,
    situacao_execucao, ultimas_execucoes,
)
from vagas.pipeline import rodar

DESCRICAO_FONTE = {
    "github": ("GitHub", "github", "Issues abertas de repositórios de vagas (backend-br, phpdevbr)."),
    "adzuna": ("Adzuna", "globe", "API que agrega vagas de vários sites do Brasil."),
    "gmail": ("Gmail", "mail", "Alertas de vaga do LinkedIn, Glassdoor e Indeed no seu e-mail (só leitura)."),
}


def _linha_agendamento() -> None:
    """Coleta automática (Agendador de Tarefas do Windows): horário, próxima e última execução."""
    ag = agendamento()
    if ag is None:
        st.html('<div class="rv-metas">' + ui.badge("Coleta automática desligada", "atencao", "calendar-clock")
                + ui.meta("info", "Para ligar: <code>powershell -ExecutionPolicy Bypass -File scripts\\agendar.ps1</code>")
                + "</div>")
        return
    ok = ag["resultado"] == 0
    ultima = (f"última {ha_quanto(ag['ultima'])} ({'OK' if ok else 'com erro, veja dados/logs'})"
              if ag["ultima"] is not None else "ainda não rodou")
    proxima = f"próxima em {ag['proxima']:%d/%m às %H:%M}" if ag["proxima"] is not None else ""
    st.html('<div class="rv-metas">'
            + ui.badge(f"Automática: todo dia às {ag['horario']}", "sucesso" if ok else "erro", "calendar-clock")
            + ui.meta("clock", proxima) + ui.meta("activity", ultima)
            + ui.meta("file-text", "log em dados/logs") + "</div>")


def _coletar() -> None:
    with st.status("Coletando vagas nas fontes...", expanded=True) as status:
        st.write("Buscando em GitHub, Adzuna e Gmail, gravando bronze → silver e recalculando as notas.")
        try:
            resumo = rodar()
        except Exception as e:  # erro de conexão com o banco, por exemplo
            status.update(label="A coleta falhou", state="error")
            st.error(f"Não foi possível concluir a coleta: {e}. Verifique se o banco (Docker) está rodando.")
            return
        for chave, valor in resumo.items():
            st.write(f"**{chave}**: {valor}")
        status.update(label="Coleta concluída", state="complete", expanded=False)
    limpar_cache()
    st.toast("Coleta concluída", icon="✅")


def _cartao_fonte(fonte: str, execucao: dict | None) -> None:
    nome, ic, desc = DESCRICAO_FONTE.get(fonte, (fonte, "globe", ""))
    with st.container(border=True):
        if execucao is None:
            rotulo, tom = "Nunca executada", "neutro"
        else:
            rotulo, tom = situacao_execucao(execucao)
        st.html(f'<div class="rv-kan-cab"><span class="rv-secao" style="margin:0"><h3>'
                f'<span class="rv-secao-ic">{ui.icone(ic, 18, ui.COR_PRIMARIA)}</span>{ui.esc(nome)}</h3></span>'
                f'{ui.badge(rotulo, tom, {"sucesso": "circle-check", "erro": "circle-x", "atencao": "triangle-alert"}.get(tom, "circle-dot"))}</div>'
                f'<p class="rv-secao-desc">{ui.esc(desc)}</p>')
        if execucao is not None:
            inicio = pd.Timestamp(execucao["iniciada_em"]).tz_convert(FUSO)
            st.html('<div class="rv-metas">'
                    + ui.meta("clock", f"Última coleta {ha_quanto(inicio)} ({inicio:%d/%m %H:%M})")
                    + (ui.meta("database", f"{int(execucao['qtd_coletada'])} coletadas · {int(execucao['qtd_nova'])} novas")
                       if pd.notna(execucao.get("qtd_coletada")) else "")
                    + "</div>")
            erro = execucao.get("erro")
            if tom == "erro":
                st.error(erro or "A última coleta começou e não terminou (o processo pode ter sido interrompido).",
                         icon=":material/error:")
            elif tom == "atencao":
                st.warning(erro, icon=":material/warning:")


def _camadas() -> None:
    estado = estado_pipeline()
    b, s, g = st.columns(3, gap="medium")
    with b, st.container(border=True):
        ui.secao("Bronze", "layers", "Respostas brutas das fontes, em JSON (dados/bronze)")
        bronze = estado["bronze"]
        st.html(ui.lista_itens([
            f"{DESCRICAO_FONTE[f][0]}: {d['arquivos']} arquivo(s), {d['tamanho_mb']} MB"
            + (f", último {ha_quanto(d['ultimo'])}" if d["ultimo"] is not None else "")
            for f, d in bronze.items()], "file-text", "neutro"))
    with s, st.container(border=True):
        ui.secao("Silver", "database", "Vagas limpas e padronizadas (PostgreSQL)")
        total = sum(x["vagas"] for x in estado["silver"])
        st.html(f'<div class="rv-kpi-val" style="margin:2px 0 6px">{total}</div>'
                + ui.lista_itens([f"{ui.FONTE_UI.get(x['fonte'], (x['fonte'],))[0]}: {x['vagas']}"
                                  for x in estado["silver"]], "circle-dot", "primario"))
    with g, st.container(border=True):
        ui.secao("Gold", "target", "Uma linha por vaga real, com nota e status")
        gold = estado["gold"]
        pontuado = ha_quanto(pd.Timestamp(gold["pontuado_em"]).tz_convert(FUSO)) if gold["pontuado_em"] else "nunca"
        st.html(f'<div class="rv-kpi-val" style="margin:2px 0 6px">{gold["vagas"]}</div>' + ui.lista_itens([
            f"{gold['alvo']} no seu perfil ({gold['alvo_ativas']} ativas)",
            f"{gold['marcadas']} marcadas por você",
            f"Notas recalculadas {pontuado}",
        ], "check", "sucesso"))


def _historico() -> None:
    execs = pd.DataFrame(db.carregar_execucoes())
    if execs.empty:
        ui.vazio("Nenhuma execução registrada", "Clique em <b>Coletar agora</b> para a primeira coleta.", "activity")
        return
    execs["situacao"] = [situacao_execucao(e)[0] for e in execs.to_dict("records")]
    execs["iniciada_em"] = pd.to_datetime(execs["iniciada_em"], utc=True).dt.tz_convert(FUSO)
    fim = pd.to_datetime(execs["finalizada_em"], utc=True).dt.tz_convert(FUSO)
    execs["duracao"] = (fim - execs["iniciada_em"]).dt.total_seconds().round(1)
    execs["detalhe"] = execs["erro"].fillna("")
    problemas = execs[execs["situacao"].isin(["Erro", "Não concluída"])]
    if not problemas.empty:
        st.warning(f"{len(problemas)} execução(ões) com erro ou não concluída(s) no histórico recente.",
                   icon=":material/warning:")
    st.dataframe(
        execs[["iniciada_em", "fonte", "situacao", "qtd_coletada", "qtd_nova", "duracao", "detalhe"]].head(60),
        hide_index=True, width="stretch",
        column_config={
            "iniciada_em": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm"),
            "fonte": "Fonte", "situacao": "Situação",
            "qtd_coletada": st.column_config.NumberColumn("Coletadas", format="%d"),
            "qtd_nova": st.column_config.NumberColumn("Novas", format="%d"),
            "duracao": st.column_config.NumberColumn("Duração (s)", format="%.1f"),
            "detalhe": st.column_config.TextColumn("Detalhe", width="large"),
        },
    )


def _integracoes() -> None:
    base = carregar_base()
    perfil = (base or {}).get("pontuacao", {})
    itens = [
        ("Currículo base", base is not None, "curriculo/base/curriculo.yaml" if base else
         "crie a partir de curriculo/exemplo.yaml"),
        ("Gmail (somente leitura)", gmail.ARQ_TOKEN.exists(),
         "autorizado" if gmail.ARQ_TOKEN.exists() else "rode: python -m vagas.coleta.gmail --autorizar"),
        ("Adzuna", bool(config.adzuna_app_id and config.adzuna_app_key),
         "chave configurada no .env" if config.adzuna_app_id else "adicione ADZUNA_APP_ID e ADZUNA_APP_KEY no .env"),
        ("GitHub (token opcional)", bool(config.github_token),
         "token configurado" if config.github_token else "sem token: limite de 60 requisições/hora (suficiente)"),
    ]
    e, d = st.columns(2, gap="medium")
    with e, st.container(border=True):
        ui.secao("Integrações", "server", "Só mostra se está configurado; nenhum valor de chave aparece aqui.")
        for nome, ok, detalhe in itens:
            st.html(f'<div class="rv-kan-cab" style="padding:6px 0;border-bottom:1px solid #f1f2f6">'
                    f'<span><b style="font-size:.88rem">{ui.esc(nome)}</b><br><span class="rv-meta">{ui.esc(detalhe)}</span></span>'
                    f'{ui.badge("Ativo" if ok else "Pendente", "sucesso" if ok else "atencao", "circle-check" if ok else "circle-alert")}</div>')
    with d, st.container(border=True):
        ui.secao("Perfil usado na nota", "user", "Seção <code>pontuacao</code> do currículo base")
        if not perfil:
            st.caption("Currículo base sem a seção de pontuação.")
        else:
            for titulo, chave, tom in (("Domina", "dominio", "sucesso"), ("Conhece", "conhecimento", "primario"),
                                       ("Cidades viáveis", "cidades_viaveis", "neutro")):
                st.html(f'<div class="rv-secao-desc" style="margin-top:6px">{titulo}</div><div class="rv-badges">'
                        + "".join(ui.badge(x, tom) for x in perfil.get(chave, [])) + "</div>")


def pagina() -> None:
    ui.cabecalho("Configurações", "Coleta, monitoramento do pipeline e integrações.", "settings")

    with st.container(border=True):
        c1, c2 = st.columns([4, 1.4], vertical_alignment="center")
        c1.html('<div class="rv-secao"><h3><span class="rv-secao-ic">' + ui.icone("refresh-cw", 18, ui.COR_PRIMARIA) +
                '</span>Coleta de vagas</h3><p class="rv-secao-desc">Busca vagas novas em todas as fontes e '
                'recalcula as notas. Leva alguns segundos.</p></div>')
        if c2.button("Coletar agora", icon=":material/refresh:", type="primary", width="stretch"):
            _coletar()
        _linha_agendamento()

    ui.secao("Estado das fontes", "activity")
    execs = ultimas_execucoes()
    por_fonte = {e["fonte"]: e for e in execs.to_dict("records")} if not execs.empty else {}
    colunas = st.columns(len(FONTES_COLETA), gap="medium")
    for col, fonte in zip(colunas, FONTES_COLETA):
        with col:
            _cartao_fonte(fonte, por_fonte.get(fonte))

    ui.secao("Camadas do pipeline", "layers", "Bronze → Silver → Gold")
    _camadas()

    with st.container(border=True):
        ui.secao("Histórico de execuções", "calendar-clock", "Cada coleta de cada fonte, mais recentes primeiro")
        _historico()

    _integracoes()
    st.caption(f"Banco: PostgreSQL em {config.db_host}:{config.db_porta} · dados brutos em {config.pasta_dados.name}/")
