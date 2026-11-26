"""Confere que a trilha PHP/Laravel continua exatamente igual (rede de segurança das mudanças).

    python scripts/conferir_laravel.py --referencia               # grava o estado atual como referência
    python scripts/conferir_laravel.py --comparar                 # compara o estado atual com a referência
    python scripts/conferir_laravel.py --comparar --descartavel   # inclui a parte (c)

Três partes (a saída fica em dados/conferencia/, fora do Git):

  (a) BANCO REAL, SOMENTE LEITURA. A sessão é aberta com default_transaction_read_only=on, então o
      próprio Postgres recusa qualquer escrita. Só executa SELECT. Calcula uma impressão digital de
      cada tabela/visão da trilha Laravel (sem as colunas que mudam a cada coleta). Se você usou o
      painel ou rodou uma coleta entre as duas medições, diferenças aqui podem ser legítimas.
      O histórico de status é conferido como "só cresce": nenhuma linha antiga pode mudar.

  (b) BRONZE EM MEMÓRIA. Reprocessa os arquivos de dados/bronze (a lista é congelada na referência)
      com o código atual: coletores, normalização, deduplicação e nota. Não usa banco nenhum.

  (c) BANCO DESCARTÁVEL (opcional). Cria o banco `vagas_conferencia`, restaura nele o backup mais
      recente de dados/backups, aplica schema.sql, grava o bronze reprocessado e pontua. Compara as
      impressões digitais. O banco original NUNCA é alterado: o script recusa qualquer nome de
      banco de destino que não seja `vagas_conferencia*` ou que seja o do .env.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from vagas import db  # noqa: E402
from vagas.coleta import adzuna, github  # noqa: E402
from vagas.coleta.emails import extrair_vagas  # noqa: E402
from vagas.coleta.gmail import juntar  # noqa: E402
from vagas.config import config  # noqa: E402
from vagas.curriculo.base import CurriculoNaoEncontrado  # noqa: E402
from vagas.curriculo.base import carregar as carregar_curriculo  # noqa: E402
from vagas.pontuacao.nota import calcular  # noqa: E402

PASTA_SAIDA = config.pasta_dados / "conferencia"
PASTA_BACKUPS = config.pasta_dados / "backups"
REFERENCIA = PASTA_SAIDA / "referencia.json"
CONTAINER = "vagas-laravel-db"
BANCO_DESCARTAVEL = "vagas_conferencia"
VOLATEIS = {"ultima_coleta", "calculado_em"}   # mudam a cada coleta, mesmo sem mudança real
TABELAS = ["silver.vagas", "silver.vaga_status", "silver.vaga_status_historico", "silver.vaga_pontuacao",
           "gold.vagas", "gold.vagas_alvo"]
CHAVE = {"silver.vagas": "id", "silver.vaga_status": "vaga_id", "silver.vaga_status_historico": "id",
         "silver.vaga_pontuacao": "vaga_id", "gold.vagas": "id", "gold.vagas_alvo": "id"}


# --------------------------------------------------------------------------- impressões digitais
def _hash(objeto) -> str:
    return hashlib.sha256(json.dumps(objeto, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _linhas_estaveis(conn, tabela: str) -> list[dict]:
    linhas = conn.execute(f"select * from {tabela}").fetchall()  # só SELECT
    limpas = [{k: v for k, v in l.items() if k not in VOLATEIS} for l in linhas]
    return sorted(limpas, key=lambda l: str(l[CHAVE[tabela]]))


def impressoes(conn) -> dict:
    saida = {}
    for tabela in TABELAS:
        linhas = _linhas_estaveis(conn, tabela)
        saida[tabela] = {"linhas": len(linhas), "hash": _hash(linhas)}
        if tabela == "silver.vaga_status_historico":
            saida[tabela]["por_linha"] = {str(l["id"]): _hash(l) for l in linhas}
    return saida


def contagem_execucoes(conn) -> dict:
    return {l["fonte"]: l["n"] for l in conn.execute(
        "select fonte, count(*) as n from silver.execucoes group by 1 order by 1").fetchall()}


# --------------------------------------------------------------------------- (a) banco real, só leitura
def parte_a() -> dict:
    with psycopg.connect(config.conninfo, row_factory=dict_row,
                         options="-c default_transaction_read_only=on") as conn:
        if conn.execute("show transaction_read_only").fetchone()["transaction_read_only"] != "on":
            raise SystemExit("ABORTADO: a sessão não está em modo somente leitura.")
        return {"tabelas": impressoes(conn), "execucoes": contagem_execucoes(conn)}


# --------------------------------------------------------------------------- (b) bronze em memória
class _Resposta:
    def __init__(self, dados):
        self._dados, self.links = dados, {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._dados


class _Sessao:
    def __init__(self, github_issues=None, adzuna_resultados=None):
        self.headers = {}
        self._github, self._adzuna = github_issues, adzuna_resultados

    def get(self, url, params=None, timeout=None):
        if self._github is not None:
            repo = url.split("/repos/")[1].removesuffix("/issues")
            return _Resposta(self._github.get(repo, []))
        pagina = int(url.rstrip("/").rsplit("/", 1)[1])
        return _Resposta({"results": self._adzuna if pagina == 1 else []})


@contextmanager
def _simulado(modulo, **atributos):
    original = {k: getattr(modulo, k) for k in atributos}
    for k, v in atributos.items():
        setattr(modulo, k, v)
    try:
        yield
    finally:
        for k, v in original.items():
            setattr(modulo, k, v)


def _arquivos_bronze() -> dict[str, list[str]]:
    base = config.pasta_dados / "bronze"
    return {fonte: sorted(str(p.relative_to(config.pasta_dados)).replace("\\", "/")
                          for p in (base / fonte).glob("*/*.json"))
            for fonte in ("github", "adzuna", "gmail")}


def reprocessar_bronze(arquivos: dict[str, list[str]]) -> dict[str, dict]:
    """Aplica o código ATUAL da trilha Laravel aos arquivos do bronze. Os mais novos vencem."""
    vagas: dict[str, dict] = {}
    for rel in arquivos["github"]:
        brutos = json.loads((config.pasta_dados / rel).read_text(encoding="utf-8"))
        with _simulado(github, sessao_http=lambda b=brutos: _Sessao(github_issues=b),
                       salvar_bronze=lambda f, d: Path("simulado"), config=SimpleNamespace(github_token="")):
            for v in github.coletar()[0]:
                vagas[v["id"]] = v
    for rel in arquivos["adzuna"]:
        brutos = json.loads((config.pasta_dados / rel).read_text(encoding="utf-8"))
        with _simulado(adzuna, sessao_http=lambda b=brutos: _Sessao(adzuna_resultados=b.get("laravel", [])),
                       salvar_bronze=lambda f, d: Path("simulado"),
                       config=SimpleNamespace(adzuna_app_id="x", adzuna_app_key="y")):
            for v in adzuna.coletar()[0]:
                vagas[v["id"]] = v
    for rel in arquivos["gmail"]:
        emails = json.loads((config.pasta_dados / rel).read_text(encoding="utf-8"))
        extraidas: dict[str, dict] = {}
        for e in emails:
            for v in extrair_vagas(e["html"], remetente=e["remetente"], assunto=e["assunto"], data=e["data"]):
                juntar(extraidas, v)
        for id_, v in extraidas.items():
            # Mesma regra do upsert: vaga de e-mail mantém a data mais antiga já vista.
            antiga = vagas.get(id_)
            if antiga and antiga["publicada_em"] and v["publicada_em"] and str(antiga["publicada_em"]) < str(v["publicada_em"]):
                v = {**v, "publicada_em": antiga["publicada_em"]}
            vagas[id_] = v
    return vagas


def _perfil() -> dict:
    try:
        return carregar_curriculo().get("pontuacao", {})
    except CurriculoNaoEncontrado:
        return {}


def parte_b(arquivos: dict[str, list[str]]) -> tuple[dict, dict[str, dict]]:
    vagas = reprocessar_bronze(arquivos)
    perfil = _perfil()
    itens = []
    for id_ in sorted(vagas):
        nota, motivos = calcular(vagas[id_], perfil)
        itens.append({**vagas[id_], "nota": nota, "motivos": motivos})
    return {"arquivos": {f: len(a) for f, a in arquivos.items()}, "vagas": len(itens), "hash": _hash(itens)}, vagas


# --------------------------------------------------------------------------- (c) banco descartável
def _conninfo(dbname: str) -> str:
    return (f"host={config.db_host} port={config.db_porta} dbname={dbname} "
            f"user={config.db_usuario} password={config.db_senha}")


def _checar_destino(nome: str) -> None:
    if nome == config.db_nome or not nome.startswith(BANCO_DESCARTAVEL):
        raise SystemExit(f"ABORTADO: '{nome}' não é um banco descartável (o original é '{config.db_nome}').")


def _admin(sql: str) -> None:
    with psycopg.connect(_conninfo("postgres"), autocommit=True) as conn:
        conn.execute(sql)


def parte_c(vagas: dict[str, dict], backup: Path) -> dict:
    _checar_destino(BANCO_DESCARTAVEL)
    _admin(f'drop database if exists "{BANCO_DESCARTAVEL}"')
    _admin(f'create database "{BANCO_DESCARTAVEL}"')
    try:
        with backup.open("rb") as f:
            r = subprocess.run(["docker", "exec", "-i", CONTAINER, "pg_restore", "-U", config.db_usuario,
                                "-d", BANCO_DESCARTAVEL, "--no-owner"], stdin=f, capture_output=True)
        if r.returncode != 0:
            raise SystemExit(f"pg_restore falhou: {r.stderr.decode(errors='replace')[:500]}")
        with psycopg.connect(_conninfo(BANCO_DESCARTAVEL), row_factory=dict_row) as conn:
            antes = impressoes(conn)
            conn.execute((RAIZ / "sql" / "schema.sql").read_text(encoding="utf-8"))
            lista = [vagas[i] for i in sorted(vagas)]
            db.salvar_vagas(conn, lista)
            from vagas.pipeline import pontuar_tudo
            pontuar_tudo(conn)
            conn.commit()
            depois = impressoes(conn)
        return {"backup": backup.name, "antes": antes, "depois": depois}
    finally:
        _checar_destino(BANCO_DESCARTAVEL)
        _admin(f'drop database if exists "{BANCO_DESCARTAVEL}"')


# --------------------------------------------------------------------------- referência e comparação
def medir(descartavel: bool, arquivos: dict[str, list[str]] | None = None, backup: Path | None = None) -> dict:
    arquivos = arquivos or _arquivos_bronze()
    resultado = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "a": parte_a()}
    resultado["b"], vagas = parte_b(arquivos)
    resultado["b"]["lista"] = arquivos
    if descartavel:
        backups = sorted(PASTA_BACKUPS.glob("*.dump"))
        backup = backup or (backups[-1] if backups else None)
        if backup is None:
            raise SystemExit("Nenhum backup em dados/backups. Faça o pg_dump primeiro.")
        resultado["c"] = parte_c(vagas, backup)
    return resultado


def _comparar_tabelas(nome: str, ref: dict, atual: dict, avisos: list[str]) -> int:
    diferentes = 0
    for tabela in TABELAS:
        r, a = ref[tabela], atual[tabela]
        igual = r["hash"] == a["hash"]
        extra = ""
        if tabela == "silver.vaga_status_historico" and not igual:
            alteradas = [i for i, h in r["por_linha"].items() if a["por_linha"].get(i) != h]
            if not alteradas:
                igual, extra = True, f" (só cresceu: {r['linhas']} -> {a['linhas']} linhas; histórico antigo íntegro)"
            else:
                extra = f" ({len(alteradas)} linhas ANTIGAS mudaram ou sumiram!)"
        print(f"  {'OK       ' if igual else 'DIFERENTE'} {nome} {tabela}: {r['linhas']} -> {a['linhas']} linhas{extra}")
        diferentes += 0 if igual else 1
    return diferentes


def comparar(descartavel: bool) -> int:
    if not REFERENCIA.exists():
        raise SystemExit("Sem referência. Rode primeiro: python scripts/conferir_laravel.py --referencia")
    ref = json.loads(REFERENCIA.read_text(encoding="utf-8"))
    backup = PASTA_BACKUPS / ref["c"]["backup"] if "c" in ref else None
    atual = medir(descartavel and "c" in ref, ref["b"]["lista"], backup)
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    (PASTA_SAIDA / "ultima_comparacao.json").write_text(json.dumps(atual, indent=1, ensure_ascii=False), encoding="utf-8")
    problemas = 0

    print("(b) Bronze reprocessado em memória (código atual x referência):")
    igual_b = ref["b"]["hash"] == atual["b"]["hash"]
    print(f"  {'OK       ' if igual_b else 'DIFERENTE'} {atual['b']['vagas']} vagas, impressão {atual['b']['hash']}")
    problemas += 0 if igual_b else 1

    if "c" in atual:
        print(f"(c) Banco descartável restaurado de {atual['c']['backup']}:")
        problemas += _comparar_tabelas("depois da regravação,", ref["c"]["depois"], atual["c"]["depois"], [])
    elif descartavel:
        print("(c) A referência foi gravada sem --descartavel; regrave a referência com a opção.")

    print("(a) Banco real (somente leitura) x referência:")
    mudou_coleta = ref["a"]["execucoes"] != atual["a"]["execucoes"]
    diferentes_a = _comparar_tabelas("", ref["a"]["tabelas"], atual["a"]["tabelas"], [])
    if mudou_coleta:
        print("  ! Houve coleta desde a referência: diferenças em (a) são esperadas. "
              "Consulte (b) e (c), que usam entradas congeladas.")
    elif diferentes_a:
        print("  ! Sem coleta no intervalo: diferenças em (a) vêm de uso do painel (status) ou de mudança no banco.")
    print("\nRESULTADO:", "tudo igual à referência (partes b/c)" if not problemas else f"{problemas} diferença(s) em (b)/(c)")
    return 1 if problemas else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--referencia", action="store_true", help="grava o estado atual como referência")
    g.add_argument("--comparar", action="store_true", help="compara o estado atual com a referência")
    p.add_argument("--descartavel", action="store_true", help="inclui a parte (c), no banco descartável")
    args = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.referencia:
        resultado = medir(args.descartavel)
        PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
        REFERENCIA.write_text(json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8")
        print("Referência gravada em", REFERENCIA)
        for tabela, d in resultado["a"]["tabelas"].items():
            print(f"  (a) {tabela}: {d['linhas']} linhas, impressão {d['hash']}")
        print(f"  (b) bronze reprocessado: {resultado['b']['vagas']} vagas, impressão {resultado['b']['hash']}")
        if "c" in resultado:
            for tabela, d in resultado["c"]["depois"].items():
                print(f"  (c) {tabela}: {d['linhas']} linhas, impressão {d['hash']}")
        return 0
    return comparar(args.descartavel)


if __name__ == "__main__":
    sys.exit(main())
