"""Simulação de rede e dados sintéticos para os testes da coleta e do pipeline da trilha de dados.

Nenhuma chamada real: as respostas do GitHub, da Adzuna e do Gmail são substituídas por estas.
"""

from pathlib import Path
from types import SimpleNamespace

from vagas.coleta import gmail
from vagas.trilhas.dados import coleta as coleta_mod

FIXTURES = Path(__file__).parent / "fixtures" / "dados"
DATA_EMAIL = "2026-11-22T08:00:00+00:00"
DJANGO = ("Procuramos pessoa desenvolvedora backend com Python e Django para construir APIs REST.\n"
          "Requisitos:\n- Python\n- Django\n- SQL\n- Docker")


def ler(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


def issue(numero, titulo, corpo="", rotulos=(), **extra):
    return {"number": numero, "title": titulo, "html_url": f"https://exemplo.test/issues/{numero}", "body": corpo,
            "created_at": "2026-11-20T10:00:00Z", "labels": [{"name": r} for r in rotulos], **extra}


def issues_github() -> list[dict]:
    """7 issues: 4 entram na trilha (2 alvo), 2 ficam fora e 1 é o aviso do repositório."""
    return [
        issue(101, "[Remoto] Engenheiro de Dados Júnior - Empresa Exemplo", ler("backendbr_template_pt.md"), ["Júnior", "Python"]),
        issue(102, "[Cidade Exemplo] Data Engineer, Marketing na Empresa Exemplo", ler("google_html_en.html"), ["Python", "Go"]),
        issue(103, "[Remoto] Lead Data Platform Engineer (Acme)", "Requisitos:\n- SQL"),
        issue(104, "[Remoto] Desenvolvedor Backend Python Júnior - Acme", DJANGO),
        issue(105, "[Remoto] Cientista de Dados Júnior", "ETL, Spark e Airflow"),
        issue(106, "Regras para divulgação de vagas", "Leia antes de publicar."),
        issue(107, "[Remoto] Desenvolvedor Python Júnior - Beta", "Responsabilidades:\n- ETL com Spark e Airflow\nRequisitos:\n- Python"),
    ]


def resultado_adzuna(id_, titulo, descricao="", local="Brasil"):
    return {"id": id_, "title": titulo, "redirect_url": f"https://exemplo.test/adzuna/{id_}", "company": {"display_name": "Acme"},
            "description": descricao, "location": {"display_name": local}, "created": "2026-11-21T08:00:00Z"}


def resultados_adzuna() -> list[dict]:
    return [resultado_adzuna(1, "Engenheiro de Dados Júnior", "Vaga remota.\nRequisitos:\n- Python e SQL"),
            resultado_adzuna(2, "Desenvolvedor PHP Laravel", "Laravel e MySQL"),
            resultado_adzuna(3, "Estágio em Engenharia de Dados", "Estágio remoto.\nRequisitos:\n- Python")]


def emails_gmail() -> list[dict]:
    return [{"id": "m1", "remetente": "jobalerts-noreply@linkedin.com", "nome_remetente": "LinkedIn", "assunto": "Data Engineer",
             "data": DATA_EMAIL, "html": ler("alerta_dados_linkedin.html")},
            {"id": "m2", "remetente": "noreply@glassdoor.com", "nome_remetente": "Glassdoor", "assunto": "Vagas",
             "data": DATA_EMAIL, "html": ler("alerta_dados_glassdoor.html")},
            {"id": "m3", "remetente": "news@exemplo.test", "nome_remetente": "Newsletter", "assunto": "Novidades",
             "data": DATA_EMAIL, "html": "<p>Newsletter sem vagas</p><a href='https://exemplo.test'>site</a>"}]


class Resposta:
    def __init__(self, dados):
        self._dados, self.links = dados, {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._dados


class SessaoSimulada:
    """Responde no lugar de api.github.com e da API da Adzuna e anota cada chamada."""

    def __init__(self, github=None, adzuna=None, chamadas=None):
        self.headers = {}
        self.github = github if github is not None else {"backend-br/vagas": issues_github()}
        self.adzuna = adzuna if adzuna is not None else (lambda termo, pagina: resultados_adzuna() if (termo, pagina) == ("engenheiro de dados", 1) else [])
        self.chamadas = chamadas if chamadas is not None else []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, dict(params or {})))
        if "api.github.com" in url:
            repo = url.split("/repos/")[1].removesuffix("/issues")
            return Resposta(self.github[repo])
        pagina = int(url.rstrip("/").rsplit("/", 1)[1])
        return Resposta({"results": self.adzuna(params["what"], pagina)})


class RedeSimulada:
    """Instala as simulações de GitHub, Adzuna e Gmail nos coletores da trilha de dados."""

    def __init__(self, monkeypatch, tmp_path, *, github=None, adzuna=None, emails=None, chaves=True):
        self.chamadas, self.bronze, self.consultas_gmail = [], [], []
        self.sessao = SessaoSimulada(github, adzuna, self.chamadas)
        monkeypatch.setattr(coleta_mod, "sessao_http", lambda: self.sessao)
        monkeypatch.setattr(coleta_mod, "salvar_bronze", self._salvar_bronze(tmp_path))
        monkeypatch.setattr(coleta_mod, "config", SimpleNamespace(
            adzuna_app_id="id" if chaves else "", adzuna_app_key="chave" if chaves else "", github_token=""))
        self.emails = emails_gmail() if emails is None else emails
        monkeypatch.setattr(gmail, "ler_emails", self._ler_emails)

    def _salvar_bronze(self, tmp_path):
        def salvar(fonte, dados):
            self.bronze.append((fonte, dados))
            return tmp_path / fonte / "simulado.json"
        return salvar

    def _ler_emails(self, dias=gmail.DIAS, consulta=gmail.CONSULTA):
        self.consultas_gmail.append((dias, consulta))
        if isinstance(self.emails, Exception):
            raise self.emails
        return self.emails
