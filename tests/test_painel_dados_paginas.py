"""Páginas do painel da trilha de Engenharia de Dados (AppTest do Streamlit) com dados sintéticos e SEM banco.

Qualquer tentativa de abrir o banco quebra o teste. A integração com banco descartável está em
test_painel_dados_integracao.py.
"""

import re

import pandas as pd
import psycopg
import pytest
from streamlit.testing.v1 import AppTest

from tests.dados_painel_simulado import BASE, DADOS, df_gold, execucoes_simuladas, historico_simulado, linha, linhas_gold
from vagas.painel import acoes_dados as ad
from vagas.painel import comum_dados as cd
from vagas.painel import logica
from vagas.painel.paginas.dados import candidaturas, configuracoes, relatorios, sugestoes, visao_geral
from vagas.painel.paginas.dados import vagas as pagina_vagas
from vagas.trilhas.dados import db as dados_db
from vagas.trilhas.dados.curriculo import combinar

PAGINAS = ("visao_geral", "vagas", "candidaturas", "relatorios", "sugestoes", "configuracoes")

# Funções REAIS do comum_dados, guardadas antes de o cenário trocá-las por dados sintéticos
REAIS = {n: getattr(cd, n) for n in ("inicializada", "carregar_vagas", "historico", "execucoes", "ultimas_execucoes")}


def _executar(nome):
    import importlib
    importlib.import_module(f"vagas.painel.paginas.dados.{nome}").pagina()


def _executar_detalhe(aba, vaga_id):
    from tests.dados_painel_simulado import df_gold
    from vagas.painel import acoes_dados as ad_
    v = df_gold().set_index("id", drop=False).loc[vaga_id].to_dict()
    getattr(ad_, aba)(v)


@pytest.fixture(autouse=True)
def cenario(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("a página tentou abrir o banco de dados")
    monkeypatch.setattr(psycopg, "connect", proibido)
    monkeypatch.setattr(dados_db, "conectar", proibido)
    monkeypatch.setattr(dados_db, "criar_esquema", proibido)
    monkeypatch.setattr(cd, "inicializada", lambda: True)
    monkeypatch.setattr(cd, "carregar_vagas", df_gold)
    monkeypatch.setattr(cd, "historico", historico_simulado)
    monkeypatch.setattr(cd, "execucoes", execucoes_simuladas)
    monkeypatch.setattr(cd, "ultimas_execucoes", execucoes_simuladas)
    monkeypatch.setattr(cd, "curriculo_combinado", lambda: combinar(BASE, DADOS))
    monkeypatch.setattr(cd, "agendamento", lambda: None)


def rodar(nome: str, **sessao) -> AppTest:
    at = AppTest.from_function(_executar, args=(nome,), default_timeout=60)
    for k, v in sessao.items():
        at.session_state[k] = v
    return at.run()


def html(at: AppTest) -> str:
    return "\n".join(e.proto.body for e in at.get("html"))


def kpis(at: AppTest) -> dict:
    return dict(re.findall(r'rv-kpi-rot">([^<]+)</span></div><div class="rv-kpi-val">([^<]+)<', html(at)))


def titulos(at: AppTest) -> list[str]:
    return re.findall(r'rv-vaga-tit"><a [^>]*>([^<]+)</a>', html(at))


# =========================================================================== as seis páginas
@pytest.mark.parametrize("nome", PAGINAS)
def test_cada_uma_das_seis_paginas_abre_sem_erro(nome):
    at = rodar(nome)
    assert not at.exception, [e.value for e in at.exception]
    assert html(at) and "rv-h1" in html(at)


def test_titulos_das_paginas():
    esperado = {"visao_geral": "Visão geral", "vagas": "Vagas", "candidaturas": "Candidaturas", "relatorios": "Relatórios",
                "sugestoes": "Sugestões de currículo", "configuracoes": "Configurações"}
    for nome, titulo in esperado.items():
        assert f'rv-h1">{titulo}<' in html(rodar(nome))


# =========================================================================== visão geral
def test_visao_geral_indicadores():
    df = df_gold()
    n = visao_geral.indicadores(df)
    assert (n["coletadas"], n["alvo"], n["remotas"], n["novas"], n["em_andamento"]) == (8, 5, 3, 3, 1)
    assert (n["relacionadas"], n["pleno_senior"], n["descartadas"]) == (1, 1, 1)


def test_visao_geral_nao_mistura_relacionadas_nem_conta_nao_remotas_como_compativeis():
    df = df_gold()
    alvo = cd.alvo_ativas(df)
    assert set(alvo["id"]) == {"github:A", "adzuna:B", "linkedin:C", "gmail:D", "github:G"}
    assert "github:E" not in set(alvo["id"]) and "github:F" not in set(alvo["id"]) and "github:H" not in set(alvo["id"])
    assert set(cd.remotas_compativeis(df)["id"]) == {"github:A", "adzuna:B", "github:G"}      # C híbrida e D sem modalidade ficam fora


def test_visao_geral_mostra_os_kpis_na_tela():
    k = kpis(rodar("visao_geral"))
    assert k["Vagas coletadas"] == "8" and k["Vagas-alvo"] == "5" and k["Remotas compatíveis"] == "3"
    assert k["Vagas novas"] == "3" and k["Candidaturas em andamento"] == "1"


def test_visao_geral_distribuicoes_so_com_vagas_alvo():
    alvo = cd.alvo_ativas(df_gold())
    notas = visao_geral.distribuicao_notas(alvo).set_index("categoria")["vagas"].to_dict()
    assert notas == {"Alta": 2, "Média": 2, "Baixa": 1}
    fontes = visao_geral.distribuicao_fontes(alvo).set_index("categoria")["vagas"].to_dict()
    assert fontes == {"GitHub": 2, "Adzuna": 1, "LinkedIn": 1, "Glassdoor": 1}
    from vagas import relatorios as r
    cat = r.distribuicao(alvo, "categoria_cargo", {k: cd.CATEGORIAS[k] for k in cd.CATEGORIAS_ALVO}).set_index("categoria")["vagas"].to_dict()
    assert cat == {"Engenharia de Dados": 3, "Analytics Engineer": 1, "Dev ETL": 1}
    assert "Relacionada" not in cat
    niveis = r.distribuicao(alvo, "nivel", {k: cd.NIVEIS[k] for k in ("estagio", "trainee", "junior")}).set_index("categoria")["vagas"].to_dict()
    assert niveis["Júnior"] == 3 and niveis["Estágio"] == 1 and niveis["Não informado"] == 1 and "Pleno" not in niveis


def test_visao_geral_lista_as_ultimas_execucoes_e_o_que_fica_fora_do_alvo():
    at = rodar("visao_geral")
    assert any("API fora do ar" in str(d.value.to_dict()) for d in at.dataframe)
    assert "1 relacionada(s)" in html(at) and "1 de nível pleno ou sênior" in html(at) and "1 descartada(s)" in html(at)


def test_visao_geral_sem_vagas_explica_como_coletar(monkeypatch):
    monkeypatch.setattr(cd, "carregar_vagas", lambda: pd.DataFrame())
    assert "Nenhuma vaga de Engenharia de Dados coletada ainda" in html(rodar("visao_geral"))


# =========================================================================== vagas: filtros e ordenação
def padrao(**mudancas):
    estado = {k: (list(v) if isinstance(v, list) else v) for k, v in pagina_vagas.PADRAO.items()}
    estado.update(mudancas)
    return estado


def filtrar_ids(**mudancas):
    return set(pagina_vagas.filtrar(df_gold(), padrao(**mudancas))["id"])


def test_vagas_filtro_padrao_e_so_remoto_e_so_alvo_sem_descartadas():
    assert filtrar_ids() == {"github:A", "adzuna:B", "github:G"}


def test_vagas_modalidade_nao_informada_e_hibrida_so_aparecem_quando_pedidas():
    assert "gmail:D" not in filtrar_ids() and "linkedin:C" not in filtrar_ids()
    assert filtrar_ids(dv_modal=["remoto", "hibrido", "presencial", logica.SEM_MODALIDADE]) >= {"linkedin:C", "gmail:D"}
    assert filtrar_ids(dv_modal=["hibrido"]) == {"linkedin:C"} and filtrar_ids(dv_modal=[logica.SEM_MODALIDADE]) == {"gmail:D"}


def test_vagas_mostrar_todas_inclui_relacionadas_pleno_e_senior():
    assert filtrar_ids(dv_todas=True) == {"github:A", "adzuna:B", "github:E", "github:F", "github:G"}
    assert filtrar_ids(dv_todas=True, dv_modal=[], dv_status=list(cd.STATUS)) == {l["id"] for l in linhas_gold()}


def test_vagas_categoria_senioridade_nota_confianca_elegibilidade_status_fonte_e_busca():
    todas = dict(dv_modal=[], dv_status=list(cd.STATUS))
    assert filtrar_ids(dv_cat=["dev_etl"], **todas) == {"github:G"}
    assert filtrar_ids(dv_cat=["relacionada"], dv_todas=True, **todas) == {"github:E"}
    assert filtrar_ids(dv_nivel=["estagio"], **todas) == {"adzuna:B"}
    assert filtrar_ids(dv_nivel=[logica.SEM_MODALIDADE], **todas) == {"gmail:D"}
    assert filtrar_ids(dv_nota=["Alta"], **todas) == {"github:A", "github:G"}
    assert filtrar_ids(dv_nota=["Baixa"], **todas) == {"linkedin:C"}
    assert filtrar_ids(dv_conf=["baixa"], **todas) == {"linkedin:C"}
    assert filtrar_ids(dv_eleg=["alerta"], **todas) == {"adzuna:B"}
    assert filtrar_ids(dv_status=["interessa"], dv_modal=[]) == {"adzuna:B"}
    assert filtrar_ids(dv_status=["descartada"], dv_todas=True, dv_modal=[]) == {"github:H"}
    assert filtrar_ids(dv_fontes=["linkedin"], **todas) == {"linkedin:C"}
    assert filtrar_ids(dv_busca="alfa", **todas) == {"github:A"}                 # empresa
    assert filtrar_ids(dv_busca="analytics", **todas) == {"gmail:D", "github:H"}   # título (com todos os status, a descartada entra)
    assert filtrar_ids(dv_busca="analytics", dv_modal=[]) == {"gmail:D"}            # padrão de status: sem a descartada
    assert filtrar_ids(dv_busca="inexistente-xyz", **todas) == set()


def test_vagas_ordenacao():
    df = df_gold()
    ordem = logica.ordenar(df, "compatibilidade")
    assert list(ordem["id"])[:2] == ["github:A", "github:G"]                      # 88 e 75
    assert list(ordem["compatibilidade"]) == sorted(df["compatibilidade"], reverse=True)
    assert list(logica.ordenar(df, "empresa")["empresa"])[0] == "Alfa"


def test_vagas_pagina_mostra_as_vagas_do_padrao_com_os_selos():
    at = rodar("vagas")
    assert not at.exception
    assert sorted(titulos(at)) == sorted(["[Remoto] Engenheiro de Dados Júnior", "Estágio em Engenharia de Dados", "[Remoto] Dev ETL Júnior"])
    corpo = html(at)
    assert "Confiança alta" in corpo and "Elegibilidade: alerta" in corpo and "Engenharia de Dados" in corpo
    assert "Estágio" in corpo and "Júnior" in corpo and "Remoto" in corpo
    assert 'href="https://exemplo.test/A"' in corpo                                    # link original
    assert at.text_input[0].key == "dv_busca" and "3 vagas-alvo" not in corpo


def test_vagas_pagina_filtro_vazio_explica_o_padrao(monkeypatch):
    at = rodar("vagas", **padrao(dv_busca="inexistente-xyz"))
    assert "Nenhuma vaga com esses filtros" in html(at) and "remotas" in html(at)


def test_vagas_pagina_todas_mostra_relacionadas():
    at = rodar("vagas", **padrao(dv_todas=True))
    assert "Desenvolvedor Python Júnior" in titulos(at) and "Relacionada" in html(at)


def test_vagas_pagina_pagina_em_blocos(monkeypatch):
    monkeypatch.setattr(pagina_vagas, "POR_BLOCO", 2)
    at = rodar("vagas", **padrao())
    assert len(titulos(at)) == 2 and any("Mostrar mais" in b.label for b in at.button)


def test_vagas_pagina_aviso_de_alerta_de_email_so_titulo():
    at = rodar("vagas", **padrao(dv_modal=["hibrido"]))
    assert "só com o título" in html(at)


def test_vagas_nao_gerencia_vaga_laravel_e_so_usa_gold_dados():
    from vagas.painel.paginas import vagas as laravel
    codigo = open(pagina_vagas.__file__, encoding="utf-8").read()
    assert not hasattr(pagina_vagas, "db") and "from vagas import db" not in codigo and "gold.vagas" not in codigo
    assert set(laravel.CHAVES.values()).isdisjoint(pagina_vagas.PADRAO)          # chaves de sessão separadas


# =========================================================================== detalhes
def test_detalhes_nota_mostra_parcelas_motivos_alertas_confianca_e_elegibilidade():
    at = AppTest.from_function(_executar_detalhe, args=("_aba_nota", "adzuna:B"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    corpo = html(at)
    assert "Confiança alta" in corpo and "Com alerta" in corpo and "7/7 sinais de confiança" in corpo
    titulos_md = [m.value for m in at.markdown]
    assert "**Pontos positivos**" in titulos_md and "**Lacunas e pontos de atenção**" in titulos_md
    assert "**Alertas** (não alteram a nota)" in titulos_md and "**O que reduz a confiança**" not in titulos_md        # B tem confiança alta
    assert "Nível júnior" in corpo and "Lacuna obrigatória: Glue" in corpo and "Exige graduação em curso" in corpo
    tabela = at.dataframe[0].value
    assert list(tabela.columns) == ["Critério", "Pontos", "Máximo", "Detalhe"] and "Área do cargo" in set(tabela["Critério"])


def test_detalhes_requisitos_separam_mencionada_de_obrigatoria_desejavel_e_atividade():
    at = AppTest.from_function(_executar_detalhe, args=("_aba_requisitos", "github:A"), default_timeout=60).run()
    assert not at.exception
    corpo = html(at)
    secoes = re.findall(r"<b>|\*\*", corpo)
    textos = [m.value for m in at.markdown]
    assert "**Requisitos obrigatórios**" in textos and "**Requisitos desejáveis**" in textos
    assert "**Citadas apenas nas atividades (não são requisitos)**" in textos and "**Tecnologias mencionadas na vaga**" in textos
    assert "Tecnologia **mencionada** não é requisito" in " ".join(c.value for c in at.caption)
    assert "Spark" in corpo and "dbt" in corpo and "ETL / importação de dados" in corpo


def test_detalhes_em_estudo_nao_e_ponto_positivo_e_sim_lacuna():
    def exibir():
        from vagas.painel import acoes_dados as ad_
        from tests.dados_painel_simulado import linha as l_
        v = l_("github:Q", "Engenheiro de Dados Júnior")
        v["motivos"] = ["✅ Nível júnior", "➕ Em estudo: Airflow, dbt", "⚠️ Lacuna obrigatória: Glue"]
        ad_._aba_nota(v)
    at = AppTest.from_function(exibir, default_timeout=60).run()
    corpo = html(at)
    assert "Em estudo: Airflow, dbt (sem experiência prática)" in corpo and "Lacuna obrigatória: Glue" in corpo
    assert corpo.index("Nível júnior") < corpo.index("Em estudo: Airflow, dbt (sem experiência prática)")


# =========================================================================== candidaturas
def test_candidaturas_kpis_e_listas():
    at = rodar("candidaturas")
    assert not at.exception
    k = kpis(at)
    assert k["Candidaturas"] == "1" and k["Entrevistas"] == "0" and k["Propostas"] == "0"
    corpo = html(at)
    assert "Interessei, mas ainda não me candidatei" in corpo and "Estágio em Engenharia de Dados" in corpo       # B está em interesse
    assert "Gerenciar uma vaga" in corpo and len(at.get("data_editor")) == 1


def test_candidaturas_gerenciar_oferece_vagas_marcadas_e_alvo():
    at = rodar("candidaturas")
    opcoes = list(at.selectbox(key="dd-gerenciar").options)
    assert len(opcoes) == 6                                      # A, B, C, D, G e H (descartada, para poder restaurar)
    assert not any("Desenvolvedor Python Júnior" in o for o in opcoes)      # relacionada sem marcação fica fora


def test_candidaturas_sem_candidatura_mostra_orientacao(monkeypatch):
    monkeypatch.setattr(cd, "carregar_vagas", lambda: cd.preparar_vagas_dados([linha("github:Z", "Engenheiro de Dados Júnior")]))
    monkeypatch.setattr(cd, "historico", lambda: historico_simulado().iloc[0:0])
    assert "Nenhuma candidatura registrada" in html(rodar("candidaturas"))


def test_candidaturas_usam_so_o_banco_da_trilha_de_dados():
    codigo = open(candidaturas.__file__, encoding="utf-8").read() + open(ad.__file__, encoding="utf-8").read()
    assert "from vagas import db" not in codigo and "db.definir" not in codigo.replace("dados_db.definir", "")
    assert "dados_db.definir_status" in codigo and "dados_db.definir_nota" in codigo


# =========================================================================== relatórios
def test_relatorios_funil_com_conversao():
    f = relatorios.funil_com_conversao(df_gold(), historico_simulado()).set_index("etapa")
    assert f["vagas"].to_dict() == {"Interessei": 2, "Me candidatei": 1, "Entrevista": 0, "Proposta": 0}
    assert f.loc["Me candidatei", "conversao"] == 0.5 and f.loc["Entrevista", "conversao"] == 0.0 and pd.isna(f.loc["Proposta", "conversao"])


def test_relatorios_taxas_de_conversao_candidatura_entrevista():
    from vagas import relatorios as r
    s = r.resumo_candidaturas(df_gold(), historico_simulado())
    assert (s["candidaturas"], s["entrevistas"], s["taxa_entrevista"], s["taxa_resposta"]) == (1, 0, 0.0, 0.0)


def test_relatorios_compatibilidade_remota_so_remoto_e_compativel():
    d = relatorios.compatibilidade_remota(cd.alvo_ativas(df_gold())).set_index("categoria")
    assert d["vagas"].to_dict() == {"Remoto": 3, "Híbrido": 1, "Não informado": 1}
    assert d["compativel"].to_dict() == {"Remoto": True, "Híbrido": False, "Não informado": False}


def test_relatorios_categoria_por_senioridade():
    t = relatorios.categoria_por_senioridade(df_gold())
    assert int(t["vagas"].sum()) == 8 and set(t["categoria"]) == set(cd.CATEGORIAS.values())
    assert t[(t["categoria"] == "Relacionada") & (t["nivel"] == "Júnior")]["vagas"].iloc[0] == 1


def test_relatorios_pagina_abas_e_conteudo():
    at = rodar("relatorios")
    assert not at.exception and len(at.tabs) == 4
    corpo = html(at)
    for esperado in ("Funil de candidaturas", "Motivos de descarte", "Evolução das vagas coletadas",
                     "Distribuição das notas", "Compatibilidade remota", "Vagas por fonte", "Categoria e senioridade",
                     "Empresas com mais oportunidades"):
        assert esperado in corpo, esperado
    assert "Candidatura → entrevista" in corpo
    tabelas = " ".join(str(d.value.to_dict()) for d in at.dataframe)
    assert "Empresa não me interessa" in tabelas and "Remoto" in tabelas                # motivos de descarte e compatibilidade remota


def test_relatorios_empresas_e_descartadas():
    from vagas import relatorios as r
    emp = r.empresas(cd.alvo_ativas(df_gold())).set_index("empresa")
    assert set(emp.index) == {"Alfa", "Beta", "Gama", "Delta", "Eta"} and emp.loc["Beta", "sua_situacao"] == "interessa"
    desc = r.descartadas(df_gold())
    assert list(desc["id"]) == ["github:H"] and r.motivos_descarte(desc).iloc[0].to_dict() == {"motivo": "Empresa não me interessa", "vagas": 1}


def test_relatorios_so_usa_dados_da_trilha():
    codigo = open(relatorios.__file__, encoding="utf-8").read()
    assert "from vagas import db" not in codigo and "gold.vagas" not in codigo and "dados_db.definir_status" in codigo


# =========================================================================== sugestões de currículo
def test_sugestoes_pagina_com_vaga_marcada_primeiro_e_textos_para_copiar():
    at = rodar("sugestoes")
    assert not at.exception and len(at.tabs) == 6
    codigos = [c.value for c in at.get("code")]
    assert codigos and "pós-graduação em andamento" in codigos[0] and "Engenheiro de Dados" not in codigos[0]
    corpo = html(at)
    assert "O que a vaga pede e o que você comprova" in corpo and "Estágio em Engenharia de Dados" in corpo       # B (interesse) vem primeiro


def test_sugestoes_pagina_abre_a_vaga_escolhida_em_outra_pagina():
    at = rodar("sugestoes", vaga_sugestao_dados="github:G")
    assert "[Remoto] Dev ETL Júnior" in html(at) and at.selectbox(key="dd-sug-vaga").value == "github:G"


def test_sugestoes_pagina_mostra_lacunas_estudos_e_separacao():
    at = rodar("sugestoes", vaga_sugestao_dados="github:A")
    textos = " ".join(m.value for m in at.markdown) + " " + html(at) + " " + " ".join(c.value for c in at.get("code"))
    assert "Projetos pessoais" in textos and "não são experiência produtiva" in " ".join(c.value for c in at.caption)
    assert "Catalog Data Pipeline" in textos and "Laboratório Databricks" in textos and "Radar de Vagas" in textos


def test_sugestoes_pagina_sem_perfil_explica(monkeypatch):
    monkeypatch.setattr(cd, "curriculo_combinado", lambda: None)
    assert "Perfil da trilha não encontrado" in html(rodar("sugestoes"))


def test_sugestoes_nao_usa_ia_nem_api_paga():
    codigo = open(sugestoes.__file__, encoding="utf-8").read() + open(sugestoes.sugestoes.__file__, encoding="utf-8").read()
    for proibido in ("anthropic", "openai", "requests", "claude"):
        assert proibido not in codigo.lower().replace("openai/deepseek", ""), proibido


# =========================================================================== configurações (somente leitura)
def test_configuracoes_mostra_termos_fontes_execucoes_e_perfil():
    at = rodar("configuracoes")
    assert not at.exception
    corpo = html(at)
    for esperado in ("Termos de busca", "engenheiro de dados júnior", "backend-br/vagas", "Fontes", "Quantidades e erros",
                     "Modalidade e perfil", "só remoto 100% é compatível", "Integrações", "Agendamento"):
        assert esperado in corpo, esperado
    assert "Experiência profissional" in corpo and "Projeto pessoal" in corpo and "Laboratório" in corpo
    assert "RuntimeError: API fora do ar" in " ".join(str(w.value) for w in at.error) + " " + str(at.dataframe[0].value.to_dict()) + corpo


def test_configuracoes_e_somente_leitura_sem_botoes_de_acao():
    at = rodar("configuracoes")
    assert len(at.button) == 0 and len(at.get("download_button")) == 0
    codigo = open(configuracoes.__file__, encoding="utf-8").read()
    for proibido in ("subprocess", "Register-ScheduledTask", "pipeline.rodar", "criar_esquema", "st.button"):
        assert proibido not in codigo, proibido


def test_configuracoes_agendamento_nao_registrado_e_registrado(monkeypatch):
    assert "não registrada" in html(rodar("configuracoes")) and "agendar.ps1 -Dados" in html(rodar("configuracoes"))
    monkeypatch.setattr(cd, "agendamento", lambda: {"horario": "08:20", "gatilhos": 2, "resultado": 0, "ultima": None, "proxima": None, "estado": "Ready"})
    assert "Automática: todo dia às 08:20" in html(rodar("configuracoes"))


def test_configuracoes_chaves_nunca_aparecem(monkeypatch):
    from vagas.config import config as c
    corpo = html(rodar("configuracoes"))
    for segredo in (c.adzuna_app_key, c.github_token, c.db_senha):
        assert not segredo or segredo not in corpo


# =========================================================================== banco ainda sem as tabelas dados_*
@pytest.mark.parametrize("nome", ["visao_geral", "vagas", "candidaturas", "relatorios", "sugestoes"])
def test_trilha_nao_inicializada_mostra_mensagem_amigavel(monkeypatch, nome):
    monkeypatch.setattr(cd, "inicializada", lambda: False)
    monkeypatch.setattr(cd, "carregar_vagas", lambda: (_ for _ in ()).throw(AssertionError("não deveria consultar as vagas")))
    at = rodar(nome)
    assert not at.exception
    corpo = html(at)
    assert "A trilha de Engenharia de Dados ainda não foi inicializada" in corpo
    assert "python -m vagas.trilhas.dados.pipeline" in corpo and "não cria o schema nem coleta sozinho" in corpo


def test_configuracoes_com_trilha_nao_inicializada_ainda_mostra_o_que_sera_coletado(monkeypatch):
    monkeypatch.setattr(cd, "inicializada", lambda: False)
    monkeypatch.setattr(cd, "execucoes", lambda: (_ for _ in ()).throw(AssertionError("não deveria consultar")))
    at = rodar("configuracoes")
    assert not at.exception
    assert any("ainda não foi inicializada" in i.value for i in at.info) and "Termos de busca" in html(at) and "Nenhuma execução registrada" in html(at)


def test_comum_dados_trata_tabela_ausente_como_vazia(monkeypatch):
    """Sem as tabelas dados_*, os carregadores REAIS devolvem vazio e `inicializada` devolve False (nunca levantam erro)."""
    from contextlib import contextmanager

    class SemTabela:
        def execute(self, *a, **k):
            raise psycopg.errors.UndefinedTable("relation does not exist")

    @contextmanager
    def conectar():
        yield SemTabela()
    monkeypatch.setattr(dados_db, "conectar", conectar)
    monkeypatch.setattr(dados_db, "carregar_historico", lambda: (_ for _ in ()).throw(psycopg.errors.UndefinedTable("x")))
    monkeypatch.setattr(dados_db, "carregar_execucoes", lambda: (_ for _ in ()).throw(psycopg.errors.UndefinedTable("x")))
    for f in REAIS.values():
        f.clear()
    try:
        assert REAIS["carregar_vagas"]().empty and REAIS["execucoes"]().empty and REAIS["ultimas_execucoes"]().empty
        assert REAIS["historico"]().empty and REAIS["inicializada"]() is False
    finally:
        for f in REAIS.values():
            f.clear()


def test_inicializada_devolve_false_quando_o_banco_falha(monkeypatch):
    def quebra():
        raise psycopg.OperationalError("sem conexão")
    monkeypatch.setattr(dados_db, "conectar", quebra)
    REAIS["inicializada"].clear()
    try:
        assert REAIS["inicializada"]() is False
    finally:
        REAIS["inicializada"].clear()


