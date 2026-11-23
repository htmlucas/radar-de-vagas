"""Coletor dos alertas de vaga que chegam no seu Gmail (LinkedIn, Indeed, Gupy...).

Usa a API oficial do Gmail com permissão SOMENTE DE LEITURA (gmail.readonly):
o projeto não consegue apagar, enviar nem alterar e-mails.

Uso:
    python -m vagas.coleta.gmail --autorizar    # uma vez: abre o navegador para você autorizar
    python -m vagas.coleta.gmail --descobrir    # lista quem te manda e-mails de vaga
    python -m vagas.coleta.gmail --testar       # mostra as vagas que seriam extraídas (sem gravar)
"""

import argparse
import base64
import os
import time
from collections import Counter
from email.utils import parseaddr, parsedate_to_datetime

from vagas.coleta.base import FonteIgnorada, salvar_bronze
from vagas.coleta.emails import extrair_vagas
from vagas.config import RAIZ

FONTE = "gmail"
ESCOPOS = ["https://www.googleapis.com/auth/gmail.readonly"]
PASTA_CREDENCIAIS = RAIZ / "credenciais"
ARQ_CLIENTE = PASTA_CREDENCIAIS / "gmail_cliente.json"   # baixado do Google Cloud
ARQ_TOKEN = PASTA_CREDENCIAIS / "gmail_token.json"       # criado na autorização

DIAS = int(os.getenv("GMAIL_DIAS", "7"))
# Busca do Gmail (mesma sintaxe da caixa de pesquisa). Pode ser trocada no .env.
CONSULTA = os.getenv(
    "GMAIL_CONSULTA",
    "(vaga OR vagas OR job OR jobs OR emprego OR oportunidade OR oportunidades) (laravel OR php)",
)
MAX_EMAILS = 300
# A API tem limite por minuto. A biblioteca do Google espera e tenta de novo sozinha
# (inclusive no erro 403 "rateLimitExceeded"); aqui só definimos quantas vezes.
TENTATIVAS = 8
PAUSA_ENTRE_EMAILS = 0.15  # segundos


# --------------------------------------------------------------------------- autorização
def _credenciais(interativo: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(ARQ_TOKEN), ESCOPOS) if ARQ_TOKEN.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif interativo:
        if not ARQ_CLIENTE.exists():
            raise SystemExit(
                f"Arquivo do cliente OAuth não encontrado em {ARQ_CLIENTE}.\n"
                "Siga o passo a passo do README (seção Gmail) para baixá-lo do Google Cloud."
            )
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = InstalledAppFlow.from_client_secrets_file(str(ARQ_CLIENTE), ESCOPOS).run_local_server(port=0)
    else:
        raise FonteIgnorada("Gmail não autorizado. Rode: python -m vagas.coleta.gmail --autorizar")
    PASTA_CREDENCIAIS.mkdir(exist_ok=True)
    ARQ_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _servico(interativo: bool = False):
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=_credenciais(interativo), cache_discovery=False)


# --------------------------------------------------------------------------- leitura
def _listar_ids(servico, consulta: str, limite: int = MAX_EMAILS) -> list[str]:
    ids, token = [], None
    while len(ids) < limite:
        resp = servico.users().messages().list(
            userId="me", q=consulta, maxResults=min(100, limite - len(ids)), pageToken=token
        ).execute(num_retries=TENTATIVAS)
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            break
    return ids


def _cabecalhos(payload: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _html(payload: dict) -> str:
    """Procura a parte text/html (ou text/plain, se não houver) dentro do e-mail."""
    partes, encontrado = [payload], {}
    while partes:
        p = partes.pop()
        partes += p.get("parts", [])
        dados = p.get("body", {}).get("data")
        if dados and p.get("mimeType") in ("text/html", "text/plain"):
            encontrado.setdefault(p["mimeType"], base64.urlsafe_b64decode(dados + "==").decode("utf-8", "replace"))
    return encontrado.get("text/html") or encontrado.get("text/plain", "")


def _ler(servico, msg_id: str) -> dict:
    time.sleep(PAUSA_ENTRE_EMAILS)
    m = servico.users().messages().get(userId="me", id=msg_id, format="full").execute(num_retries=TENTATIVAS)
    cab = _cabecalhos(m["payload"])
    try:
        data = parsedate_to_datetime(cab.get("date")).isoformat()
    except (TypeError, ValueError):
        data = None
    return {
        "id": msg_id,
        "remetente": parseaddr(cab.get("from", ""))[1].lower(),
        "nome_remetente": parseaddr(cab.get("from", ""))[0],
        "assunto": cab.get("subject", ""),
        "data": data,
        "html": _html(m["payload"]),
    }


def ler_emails(dias: int = DIAS, consulta: str = CONSULTA) -> list[dict]:
    servico = _servico()
    return [_ler(servico, i) for i in _listar_ids(servico, f"newer_than:{dias}d {consulta}")]


# --------------------------------------------------------------------------- coleta
def coletar() -> tuple[list[dict], list[str]]:
    emails = ler_emails()
    arquivo = salvar_bronze(FONTE, emails)
    vagas: dict[str, dict] = {}
    for e in emails:
        for v in extrair_vagas(e["html"], remetente=e["remetente"], assunto=e["assunto"], data=e["data"]):
            juntar(vagas, v)
    return list(vagas.values()), [str(arquivo)]


def juntar(vagas: dict[str, dict], v: dict) -> None:
    """A mesma vaga pode vir em vários alertas. Fica a data mais antiga:
    é a mais próxima de quando a vaga foi publicada."""
    atual = vagas.get(v["id"])
    if atual is None or (v["publicada_em"] and (not atual["publicada_em"] or v["publicada_em"] < atual["publicada_em"])):
        vagas[v["id"]] = v


# --------------------------------------------------------------------------- linha de comando
def _descobrir(dias: int) -> None:
    servico = _servico()
    ids = _listar_ids(servico, f"newer_than:{dias}d {CONSULTA}")
    por_remetente: Counter = Counter()
    assuntos: dict[str, list[str]] = {}
    vagas_por_remetente: Counter = Counter()
    for i in ids:
        e = _ler(servico, i)
        por_remetente[e["remetente"]] += 1
        assuntos.setdefault(e["remetente"], []).append(e["assunto"])
        vagas_por_remetente[e["remetente"]] += len(extrair_vagas(e["html"], e["remetente"], e["assunto"], e["data"]))
    print(f"{len(ids)} e-mails nos últimos {dias} dias com a busca: {CONSULTA}\n")
    print(f"{'qtd':>4} {'vagas lidas':>11}  remetente")
    for remetente, n in por_remetente.most_common(30):
        print(f"{n:>4} {vagas_por_remetente[remetente]:>11}  {remetente}")
        for a in assuntos[remetente][:2]:
            print(f"{'':>18}↳ {a[:90]}")


def _testar(dias: int) -> None:
    vagas: dict[str, dict] = {}
    for e in ler_emails(dias):
        for v in extrair_vagas(e["html"], e["remetente"], e["assunto"], e["data"]):
            juntar(vagas, v)
    print(f"{len(vagas)} vagas extraídas (nada foi gravado)\n")
    for v in list(vagas.values())[:60]:
        print(f"[{v['fonte']}] {v['titulo'][:60]} | {v['empresa']} | {v['localizacao']} | laravel={v['cita_laravel']}")
        print(f"        {v['url']}")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--autorizar", action="store_true", help="autoriza o acesso de leitura ao Gmail")
    g.add_argument("--descobrir", action="store_true", help="lista remetentes de e-mails de vaga")
    g.add_argument("--testar", action="store_true", help="mostra as vagas extraídas, sem gravar no banco")
    p.add_argument("--dias", type=int, default=None)
    args = p.parse_args()
    try:
        if args.autorizar:
            _servico(interativo=True)
            print("Gmail autorizado (somente leitura). Token salvo em", ARQ_TOKEN)
        elif args.descobrir:
            _descobrir(args.dias or 14)
        else:
            _testar(args.dias or DIAS)
    except FonteIgnorada as e:
        raise SystemExit(str(e))
