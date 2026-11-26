"""Etapa 5: coletores da trilha de Engenharia de Dados (GitHub, Adzuna e Gmail), com rede simulada.

Nenhuma chamada real e nenhuma escrita em dados/bronze: o bronze é interceptado (ou vai para tmp_path).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.dados_simulados import (
    DATA_EMAIL, DJANGO, RedeSimulada, SessaoSimulada, emails_gmail, issue, issues_github, ler, resultado_adzuna,
    resultados_adzuna,
)
from vagas.coleta import adzuna, base, github, gmail
from vagas.coleta.base import FonteIgnorada
from vagas.coleta.emails import extrair_vagas
from vagas.tratamento.normalizar import montar_vaga
from vagas.trilhas.dados import coleta as c


# =========================================================================== GitHub
def test_github_classifica_cada_issue_e_so_usa_o_repositorio_da_trilha(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path)
    r = c.coletar_github()
    por_id = {v["id"]: v for v in r.vagas}
    assert set(por_id) == {"github:backend-br/vagas#101", "github:backend-br/vagas#102",
                           "github:backend-br/vagas#103", "github:backend-br/vagas#107"}
    assert r.brutas == 6 and r.falhas == []                       # 7 issues menos o aviso do repositório
    v101, v102, v103, v107 = (por_id[f"github:backend-br/vagas#{n}"] for n in (101, 102, 103, 107))
    assert (v101["categoria_cargo"], v101["nivel"], v101["modelo_trabalho"], v101["alvo"]) == ("engenharia_dados", "junior", "remoto", True)
    assert (v102["categoria_cargo"], v102["nivel"], v102["alvo"]) == ("engenharia_dados", None, True)
    assert (v103["categoria_cargo"], v103["nivel"], v103["alvo"]) == ("engenharia_dados", "senior", False)
    assert (v107["categoria_cargo"], v107["alvo"]) == ("relacionada", False)
    assert {u.split("/repos/")[1] for u, _ in rede.chamadas} == {"backend-br/vagas/issues"}     # só backend-br/vagas


def test_github_rotulos_viram_nivel_mas_nao_tecnologias(monkeypatch, tmp_path):
    RedeSimulada(monkeypatch, tmp_path, github={"backend-br/vagas": [
        issue(1, "[Remoto] Engenheiro de Dados", "Requisitos:\n- SQL", ["Júnior", "Python", "Spark", "Scala"])]})
    v = c.coletar_github().vagas[0]
    assert v["nivel"] == "junior" and v["tecnologias"] == ["SQL"]


def test_github_guarda_o_bronze_na_pasta_propria(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path)
    r = c.coletar_github()
    assert [f for f, _ in rede.bronze] == ["dados_github"] and r.arquivos == [str(tmp_path / "dados_github" / "simulado.json")]
    assert len(rede.bronze[0][1]["backend-br/vagas"]) == 7        # resposta bruta completa, para reprocessar


def test_github_remove_duplicadas_por_repositorio_e_numero(monkeypatch, tmp_path):
    iss = issues_github()
    RedeSimulada(monkeypatch, tmp_path, github={"backend-br/vagas": iss + [dict(iss[0]), dict(iss[0])]})
    r = c.coletar_github()
    ids = [v["id"] for v in r.vagas]
    assert len(ids) == len(set(ids)) == 4 and r.brutas == 8


def test_github_resposta_vazia(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path, github={"backend-br/vagas": []})
    r = c.coletar_github()
    assert (r.vagas, r.brutas, r.falhas) == ([], 0, []) and rede.bronze[0][1] == {"backend-br/vagas": []}


def test_github_item_malformado_nao_derruba_a_fonte(monkeypatch, tmp_path):
    ruins = [{"number": 900, "html_url": "u", "body": "sem título"},                              # sem 'title'
             issue(901, "[Remoto] Engenheiro de Dados Júnior", "Requisitos:\n- SQL", []) | {"labels": [{"sem_name": 1}]}]
    RedeSimulada(monkeypatch, tmp_path, github={"backend-br/vagas": ruins + issues_github()})
    r = c.coletar_github()
    assert len(r.falhas) == 2 and any("backend-br/vagas#900" in f for f in r.falhas) and any("#901" in f for f in r.falhas)
    assert len(r.vagas) == 4                                                                        # o resto foi processado


def test_github_envia_o_token_so_se_existir(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path)
    c.coletar_github()
    assert "Authorization" not in rede.sessao.headers
    monkeypatch.setattr(c, "config", SimpleNamespace(github_token="segredo", adzuna_app_id="", adzuna_app_key=""))
    c.coletar_github()
    assert rede.sessao.headers["Authorization"] == "Bearer segredo"


# =========================================================================== Adzuna
def test_adzuna_sem_chaves_e_ignorada(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path, chaves=False)
    with pytest.raises(FonteIgnorada):
        c.coletar_adzuna()
    assert rede.chamadas == [] and rede.bronze == []


def test_adzuna_buscas_sao_cargos_com_niveis_e_no_maximo_duas_paginas(monkeypatch, tmp_path):
    cheia = lambda termo, pagina: [resultado_adzuna(f"{termo}-{pagina}-{n}", "Vendedor") for n in range(adzuna.POR_PAGINA)]
    rede = RedeSimulada(monkeypatch, tmp_path, adzuna=cheia)
    r = c.coletar_adzuna()
    termos = [p["what"] for _, p in rede.chamadas]
    assert set(termos) == set(c.BUSCAS_ADZUNA) and len(c.BUSCAS_ADZUNA) == len(set(c.BUSCAS_ADZUNA)) == 15
    assert len(rede.chamadas) == 2 * len(c.BUSCAS_ADZUNA)                       # sempre pede 2 páginas se a 1ª vier cheia
    assert {int(u.rsplit("/", 1)[1]) for u, _ in rede.chamadas} == {1, 2}
    assert r.vagas == [] and r.brutas == 2 * adzuna.POR_PAGINA * len(c.BUSCAS_ADZUNA)   # nenhum "Vendedor" é da trilha


@pytest.mark.parametrize("termo", ["engenheiro de dados", "engenharia de dados", "data engineer", "analytics engineer",
                                   "desenvolvedor etl", "etl developer", "engenheiro de dados júnior", "data engineer estágio",
                                   "analytics engineer trainee"])
def test_adzuna_termos_de_cargo_e_variacoes_de_nivel(termo):
    assert termo in c.BUSCAS_ADZUNA


def test_adzuna_nao_busca_tecnologias_soltas():
    soltos = {"python", "sql", "spark", "airflow", "dbt", "aws", "laravel", "php"}
    assert not (soltos & {b.lower() for b in c.BUSCAS_ADZUNA})


def test_adzuna_envia_a_chave_e_os_parametros_da_infraestrutura_existente(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path)
    c.coletar_adzuna()
    url, params = rede.chamadas[0]
    assert url == adzuna.URL.format(pagina=1)
    assert (params["app_id"], params["app_key"], params["max_days_old"], params["sort_by"]) == ("id", "chave", adzuna.DIAS, "date")


def test_adzuna_classifica_remove_fora_da_trilha_e_duplicadas_entre_buscas(monkeypatch, tmp_path):
    def respostas(termo, pagina):
        return resultados_adzuna() if pagina == 1 and termo in ("engenheiro de dados", "data engineer", "etl developer") else []
    rede = RedeSimulada(monkeypatch, tmp_path, adzuna=respostas)
    r = c.coletar_adzuna()
    assert sorted(v["id"] for v in r.vagas) == ["adzuna:1", "adzuna:3"]          # o PHP/Laravel (id 2) fica fora
    assert r.brutas == 3                                                          # 3 anúncios distintos, mesmo vindos de 3 buscas
    assert {v["id"]: v["nivel"] for v in r.vagas} == {"adzuna:1": "junior", "adzuna:3": "estagio"}
    assert [f for f, _ in rede.bronze] == ["dados_adzuna"]
    assert set(rede.bronze[0][1]) == set(c.BUSCAS_ADZUNA)                         # bronze guarda a resposta de cada busca


def test_adzuna_resposta_vazia(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path, adzuna=lambda termo, pagina: [])
    r = c.coletar_adzuna()
    assert (r.vagas, r.brutas, r.falhas) == ([], 0, []) and len(rede.chamadas) == len(c.BUSCAS_ADZUNA)    # 1 página por busca


def test_adzuna_item_sem_id_e_uma_falha_isolada(monkeypatch, tmp_path):
    sem_id = {"title": "Engenheiro de Dados Júnior", "redirect_url": "u"}
    RedeSimulada(monkeypatch, tmp_path, adzuna=lambda t, p: [sem_id, *resultados_adzuna()] if (t, p) == ("data engineer", 1) else [])
    r = c.coletar_adzuna()
    assert len(r.falhas) == 1 and "KeyError" in r.falhas[0] and sorted(v["id"] for v in r.vagas) == ["adzuna:1", "adzuna:3"]


def test_adzuna_erro_de_http_propaga_para_o_pipeline_isolar(monkeypatch, tmp_path):
    class Quebrada(SessaoSimulada):
        def get(self, *a, **k):
            raise ConnectionError("sem rede")
    RedeSimulada(monkeypatch, tmp_path)
    monkeypatch.setattr(c, "sessao_http", lambda: Quebrada())
    with pytest.raises(ConnectionError):
        c.coletar_adzuna()


# =========================================================================== Gmail
def test_gmail_usa_a_consulta_propria_da_trilha_de_dados(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path)
    c.coletar_gmail()
    assert rede.consultas_gmail == [(gmail.DIAS, c.CONSULTA_GMAIL)]
    assert c.CONSULTA_GMAIL != gmail.CONSULTA and "data engineer" in c.CONSULTA_GMAIL and "laravel" not in c.CONSULTA_GMAIL.lower()


def test_gmail_extrai_so_vagas_da_trilha_de_alertas_sem_descricao(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path)
    r = c.coletar_gmail()
    por_id = {v["id"]: v for v in r.vagas}
    assert set(por_id) == {"linkedin:6000000001", "linkedin:6000000002", "glassdoor:8000000001"}   # o PHP/Laravel e a newsletter ficam fora
    assert r.brutas == 4 and r.falhas == []                                                      # 3 de dados + 1 de PHP; a newsletter não tem vaga
    assert all(v["so_titulo"] for v in r.vagas)                                                  # alertas: só título, sem descrição
    assert (por_id["linkedin:6000000001"]["categoria_cargo"], por_id["linkedin:6000000001"]["nivel"],
            por_id["linkedin:6000000001"]["modelo_trabalho"], por_id["linkedin:6000000001"]["alvo"]) == ("engenharia_dados", "junior", "remoto", True)
    assert por_id["linkedin:6000000002"]["nivel"] == "pleno" and por_id["linkedin:6000000002"]["alvo"] is False
    assert (por_id["glassdoor:8000000001"]["categoria_cargo"], por_id["glassdoor:8000000001"]["empresa"]) == ("analytics_engineer", "Empresa Delta")
    assert por_id["glassdoor:8000000001"]["publicada_em"].startswith("2026-11-19")                # 3 dias antes do e-mail
    assert [f for f, _ in rede.bronze] == ["dados_gmail"] and len(rede.bronze[0][1]) == 3


def test_gmail_mesma_vaga_em_varios_alertas_fica_com_a_data_mais_antiga(monkeypatch, tmp_path):
    mais_novo = {**emails_gmail()[0], "id": "m9", "data": "2026-11-24T08:00:00+00:00"}
    mais_antigo = {**emails_gmail()[0], "id": "m8", "data": "2026-11-20T08:00:00+00:00"}
    RedeSimulada(monkeypatch, tmp_path, emails=[mais_novo, emails_gmail()[0], mais_antigo])
    r = c.coletar_gmail()
    v = next(v for v in r.vagas if v["id"] == "linkedin:6000000001")
    assert len([x for x in r.vagas if x["id"] == "linkedin:6000000001"]) == 1 and v["publicada_em"].startswith("2026-11-20")


def test_gmail_sem_mensagens(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path, emails=[])
    r = c.coletar_gmail()
    assert (r.vagas, r.brutas, r.falhas) == ([], 0, []) and rede.bronze == [("dados_gmail", [])]


def test_gmail_nao_autorizado_e_fonte_ignorada(monkeypatch, tmp_path):
    rede = RedeSimulada(monkeypatch, tmp_path, emails=FonteIgnorada("Gmail não autorizado"))
    with pytest.raises(FonteIgnorada):
        c.coletar_gmail()
    assert rede.bronze == []


def test_gmail_nao_raspa_nenhuma_plataforma():
    codigo = Path(c.__file__).read_text(encoding="utf-8").lower()
    assert "linkedin.com" not in codigo and "indeed.com" not in codigo and "glassdoor.com" not in codigo


# =========================================================================== bronze de verdade (em pasta temporária)
def test_bronze_vai_para_pasta_propria_sem_tocar_no_bronze_real(monkeypatch, tmp_path):
    real = base.config.pasta_dados / "bronze"
    antes = {p.name for p in real.iterdir()} if real.exists() else set()
    RedeSimulada(monkeypatch, tmp_path)
    monkeypatch.setattr(c, "salvar_bronze", base.salvar_bronze)                     # a função REAL...
    monkeypatch.setattr(base, "config", SimpleNamespace(pasta_dados=tmp_path))     # ...gravando em tmp_path
    c.coletar_github(), c.coletar_adzuna(), c.coletar_gmail()
    assert {p.name for p in (tmp_path / "bronze").iterdir()} == {"dados_github", "dados_adzuna", "dados_gmail"}
    depois = {p.name for p in real.iterdir()} if real.exists() else set()
    assert depois == antes          # o bronze real não ganhou nem perdeu nenhuma pasta


# =========================================================================== o comportamento Laravel não muda
def test_consultas_e_buscas_laravel_continuam_as_mesmas():
    assert adzuna.BUSCAS == {"laravel": "Laravel"} and adzuna.MAX_PAGINAS == 4
    assert github.REPOSITORIOS == ["backend-br/vagas", "phpdevbr/vagas"]
    assert "(laravel OR php)" in gmail.CONSULTA and gmail.CONSULTA.startswith("(vaga OR vagas")
    assert gmail.FONTE == "gmail" and adzuna.FONTE == "adzuna" and github.FONTE == "github"


def test_extrair_vagas_padrao_continua_sendo_o_da_trilha_laravel():
    for arquivo in ("alerta_linkedin.html", "alerta_glassdoor.html", "alerta_indeed.html"):
        html = (Path(__file__).parent / "fixtures" / "laravel" / arquivo).read_text(encoding="utf-8")
        assert extrair_vagas(html, "x", "x", DATA_EMAIL) == extrair_vagas(html, "x", "x", DATA_EMAIL, montar=montar_vaga)
        assert len(extrair_vagas(html, "x", "x", DATA_EMAIL)) >= 1


def test_extrair_vagas_com_outra_montagem_descarta_o_que_ela_recusa():
    html = ler("alerta_dados_linkedin.html")
    assert extrair_vagas(html, "x", "x", DATA_EMAIL, montar=lambda **kw: None) == []
    chamadas = []
    parcial = extrair_vagas(html, "x", "x", DATA_EMAIL, montar=lambda **kw: chamadas.append(kw["id_externo"]) or (
        {"id": kw["id_externo"], "publicada_em": None} if kw["id_externo"].endswith("1") else None))
    assert sorted(chamadas) == ["6000000001", "6000000002", "6000000003"] and [v["id"] for v in parcial] == ["6000000001"]


def test_modulos_laravel_nao_foram_alterados_pela_trilha_de_dados():
    """Importar a trilha de dados não pode mudar as constantes dos coletores Laravel."""
    assert adzuna.BUSCAS == {"laravel": "Laravel"} and github.REPOSITORIOS == ["backend-br/vagas", "phpdevbr/vagas"]
