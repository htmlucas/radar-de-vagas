"""Calibração da trilha de Engenharia de Dados sobre o bronze do GitHub (SOMENTE LEITURA).

    python scripts/calibrar_dados.py

- Lê dados/bronze/github/*/*.json e remove as repetições (cada coleta traz as mesmas issues):
  vaga única = "repositório#número" (vale a versão do arquivo mais novo).
- Aplica a classificação e a normalização da trilha de dados (vagas/trilhas/dados), em memória.
- Imprime um resumo e grava o relatório em dados/calibracao/ (fora do Git). Não usa banco nem rede
  e não altera nenhum arquivo do projeto.

Serve para calibrar as regras (cabeçalhos, categorias, requisitos) e será reaproveitado no --testar da etapa 5.
Uma amostra pequena e voltada a PHP não prova a precisão geral.
"""

import glob
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from vagas.coleta.github import _localizacao, extrair_empresa  # noqa: E402
from vagas.config import config  # noqa: E402
from vagas.tratamento.normalizar import sem_acento  # noqa: E402
from vagas.trilhas.dados import config as cfg  # noqa: E402
from vagas.trilhas.dados.normalizar import (  # noqa: E402
    _cabecalho, classificar_cargo, contar_sinais_fortes, html_para_linhas, montar_vaga_dados, separar_requisitos,
)

PASTA_SAIDA = config.pasta_dados / "calibracao"
PADRAO_BACKEND = re.compile(r"\b(php|laravel|symfony|wordpress|drupal|magento|codeigniter)\b", re.IGNORECASE)


def carregar_issues_unicas() -> tuple[dict[str, dict], int, int]:
    """(issues únicas por 'repo#número', quantidade de arquivos, total de registros somados)."""
    arquivos = sorted(glob.glob(str(config.pasta_dados / "bronze" / "github" / "*" / "*.json")))
    unicas: dict[str, dict] = {}
    registros = 0
    for arquivo in arquivos:
        for repo, issues in json.loads(Path(arquivo).read_text(encoding="utf-8")).items():
            for i in issues:
                registros += 1
                unicas[f"{repo}#{i['number']}"] = {**i, "_repo": repo}   # o arquivo mais novo vence
    return unicas, len(arquivos), registros


def analisar(chave: str, issue: dict) -> dict:
    titulo, corpo = issue["title"], issue.get("body") or ""
    rotulos = [r["name"] for r in issue.get("labels", [])]
    v = montar_vaga_dados(
        fonte="github", id_externo=chave, titulo=titulo, url=issue.get("html_url", ""),
        empresa=extrair_empresa(titulo), descricao=corpo, localizacao=_localizacao(titulo), rotulos=rotulos)
    r = separar_requisitos(corpo)
    c = classificar_cargo(titulo, r.texto_relevante)
    return {"chave": chave, "titulo": titulo, "categoria": c.categoria, "motivo": c.motivo,
            "sinais": list(c.sinais), "vaga": v, "requisitos": r, "backend_php": bool(PADRAO_BACKEND.search(titulo + " " + corpo[:1500]))}


def cabecalhos_nao_reconhecidos(issues: dict[str, dict]) -> Counter:
    """Linhas com cara de cabeçalho (Markdown, negrito ou terminadas em ':') que o parser NÃO reconhece."""
    contagem: Counter = Counter()
    for issue in issues.values():
        for linha in html_para_linhas(issue.get("body")):
            s = linha.strip()
            t = re.sub(r"[*_`]", "", sem_acento(s)).strip()
            t = re.sub(r"^[\W_]+", "", t).strip()
            parece = s.startswith("#") or re.fullmatch(r"\*\*[^*]+\*\*:?", s) or (t.endswith(":") and len(t) <= 60)
            if parece and 0 < len(t) <= cfg.MAX_CARACTERES_CABECALHO and _cabecalho(linha) is None:
                contagem[t.rstrip(":").strip()] += 1
    return contagem


def principal() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    issues, n_arquivos, registros = carregar_issues_unicas()
    analises = [analisar(k, i) for k, i in issues.items()]
    por_categoria = Counter(a["categoria"] or "fora" for a in analises)
    print(f"{n_arquivos} arquivos de coleta, {registros} registros somados -> {len(issues)} issues ÚNICAS")
    print("categorias:", dict(por_categoria))

    na_trilha = [a for a in analises if a["categoria"]]
    print(f"\n== Vagas que entram na trilha ({len(na_trilha)}) ==")
    for a in na_trilha:
        v, r = a["vaga"], a["requisitos"]
        print(f"- {a['chave']} | {a['titulo'][:90]}")
        print(f"    categoria={a['categoria']} ({a['motivo']}) nivel={v['nivel']} modalidade={v['modelo_trabalho']} alvo={v['alvo']}")
        print(f"    sinais={a['sinais'] or contar_sinais_fortes(a['titulo'], r.texto_relevante)}")
        print(f"    obrigatorios={r.obrigatorios}\n    desejaveis={r.desejaveis}\n    citados_em_atividades={r.citados_em_atividades}")
        print(f"    tecnologias={v['tecnologias']}")
        print(f"    cabecalhos: obrig={r.cabecalhos_obrigatorios} desej={r.cabecalhos_desejaveis} "
              f"ativ={r.cabecalhos_atividades} neutros={r.cabecalhos_neutros}")

    suspeitos = [a for a in na_trilha if a["backend_php"] and "dados" not in sem_acento(a["titulo"]) and "data" not in sem_acento(a["titulo"])]
    print(f"\n== Possíveis falsos positivos (backend/PHP puro classificado como dados): {len(suspeitos)} ==")
    for a in suspeitos:
        print("  ", a["chave"], a["titulo"][:90], a["motivo"])

    nao_reconhecidos = cabecalhos_nao_reconhecidos(issues)
    print(f"\n== Cabeçalhos não reconhecidos que sobraram ({sum(nao_reconhecidos.values())} linhas, {len(nao_reconhecidos)} distintos) ==")
    for t, n in nao_reconhecidos.most_common(60):
        print(f"{n:>4}  {t}")

    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    saida = PASTA_SAIDA / f"calibracao-{datetime.now():%Y%m%d-%H%M%S}.json"
    saida.write_text(json.dumps({
        "issues_unicas": len(issues), "arquivos": n_arquivos, "registros_somados": registros,
        "categorias": dict(por_categoria),
        "vagas": [{"chave": a["chave"], "titulo": a["titulo"], "categoria": a["categoria"], "motivo": a["motivo"],
                   "nivel": a["vaga"]["nivel"] if a["vaga"] else None, "alvo": a["vaga"]["alvo"] if a["vaga"] else False,
                   "obrigatorios": a["requisitos"].obrigatorios, "desejaveis": a["requisitos"].desejaveis,
                   "citados_em_atividades": a["requisitos"].citados_em_atividades} for a in na_trilha],
        "cabecalhos_nao_reconhecidos": dict(nao_reconhecidos.most_common()),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nRelatório gravado em", saida)
    return 0


if __name__ == "__main__":
    sys.exit(principal())
