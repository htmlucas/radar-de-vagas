"""Testa a geração SEM chamar a API: o cliente do Claude é substituído por um falso."""

from types import SimpleNamespace

import pytest
from docx import Document

from vagas.curriculo import gerar
from vagas.curriculo.gerar import CurriculoAdaptado, montar_documento, verificar_invencoes

BASE = {
    "contato": {"nome": "Pessoa Teste", "titulo": "Dev", "cidade": "Alfaville – SP", "github": "github.com/x"},
    "resumo": "Dev PHP.",
    "experiencias": [
        {"id": "a", "empresa": "Empresa A", "cargo": "Dev Pleno", "periodo": "2024 – 2025",
         "atividades": ["Laravel com filas no SQS.", "APIs REST.", "PostgreSQL."]},
        {"id": "b", "empresa": "Empresa B", "cargo": "Dev Júnior", "periodo": "2022 – 2023",
         "atividades": ["Manutenção em PHP.", "MySQL."]},
    ],
    "projetos": [{"id": "p1", "nome": "Projeto 1", "link": "github.com/x/p1", "descricao": "Pipeline em Python."}],
    "formacao": [{"curso": "ADS", "instituicao": "Instituto Exemplo", "status": ""}],
    "certificacoes": ["AWS Cloud Practitioner"],
    "competencias": {"Backend": ["PHP", "Laravel"], "Cloud": ["AWS S3", "SQS"]},
}


def adaptado(**kw) -> CurriculoAdaptado:
    dados = {
        "titulo_profissional": "Desenvolvedor Backend Laravel",
        "resumo": "Desenvolvedor com Laravel e filas.",
        "experiencias": [{"id": "a", "atividades": ["Processamento assíncrono com filas no SQS.", "APIs REST."]},
                         {"id": "inventada", "atividades": ["Trabalhou na NASA."]}],
        "projetos": [{"id": "p1", "descricao": "Pipeline de dados."}, {"id": "nao-existe", "descricao": "x"}],
        "competencias_em_destaque": ["SQS"],
        "palavras_chave_atendidas": ["Laravel", "filas"],
        "lacunas": ["Kubernetes"],
        "observacoes": "Destaque filas.",
    }
    return CurriculoAdaptado.model_validate(dados | kw)


def test_montagem_usa_dados_fixos_do_base_e_ignora_ids_inventados():
    doc = montar_documento(BASE, adaptado())
    assert [e["empresa"] for e in doc["experiencias"]] == ["Empresa A", "Empresa B"]
    assert doc["experiencias"][0]["atividades"][0].startswith("Processamento")
    # Experiência que o modelo não mandou mantém as atividades originais
    assert doc["experiencias"][1]["atividades"] == BASE["experiencias"][1]["atividades"]
    assert "NASA" not in str(doc)
    assert [p["nome"] for p in doc["projetos"]] == ["Projeto 1"]
    assert list(doc["competencias"])[0] == "Cloud"  # área com competência pedida vem primeiro
    assert doc["contato"]["nome"] == "Pessoa Teste"


def test_detecta_tecnologia_inventada():
    doc = montar_documento(BASE, adaptado(resumo="Desenvolvedor com Laravel e Kubernetes."))
    assert verificar_invencoes(doc, BASE) == ["Kubernetes"]
    assert verificar_invencoes(montar_documento(BASE, adaptado()), BASE) == []


class _ClienteFalso:
    """Imita client.beta.messages.parse devolvendo um resultado pronto."""

    def __init__(self, saida, stop_reason="end_turn"):
        resposta = SimpleNamespace(
            parsed_output=saida, stop_reason=stop_reason, model="claude-opus-5-5",
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        )
        self.chamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: self.chamadas.append(kw) or resposta))


def test_fluxo_completo_gera_docx_pdf_e_analise(tmp_path, monkeypatch):
    monkeypatch.setattr(gerar, "PASTA_GERADOS", tmp_path)
    monkeypatch.setattr(gerar.curriculo_base, "carregar", lambda: BASE)
    cliente = _ClienteFalso(adaptado())
    vaga = {"id": "x:1", "titulo": "Dev Laravel Pleno", "empresa": "Acme", "descricao": "Laravel e SQS", "url": "u"}

    r = gerar.gerar(vaga, cliente=cliente)

    docx = Document(r["docx"])
    texto = "\n".join(p.text for p in docx.paragraphs)
    assert "Pessoa Teste" in texto and "Processamento assíncrono com filas no SQS." in texto
    assert open(r["pdf"], "rb").read(5) == b"%PDF-"
    assert r["lacunas"] == ["Kubernetes"]
    # Pedido enviado com o modelo, o fallback e o currículo no system (em cache)
    pedido = cliente.chamadas[0]
    assert pedido["model"] == "claude-opus-5-5" and pedido["fallbacks"] == "default"
    assert "cache_control" in pedido["system"][1]
    assert "Pessoa Teste" not in str(pedido["system"])  # contato não vai para o modelo


def test_recusa_vira_erro_amigavel(monkeypatch):
    monkeypatch.setattr(gerar.curriculo_base, "carregar", lambda: BASE)
    with pytest.raises(gerar.FalhaNaGeracao):
        gerar.gerar({"titulo": "x"}, cliente=_ClienteFalso(None, stop_reason="refusal"))
