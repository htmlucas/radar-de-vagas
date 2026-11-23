"""Sugestões para adaptar o currículo a uma vaga, em texto e sem custo.

Tudo é calculado localmente, cruzando a vaga com o currículo base:
  - o que a vaga pede e você comprova (palavras-chave para destacar);
  - quais atividades de cada experiência colocar primeiro;
  - quais projetos mostrar;
  - o que a vaga pede e não aparece no seu currículo (lacunas);
  - um título e um rascunho de resumo, montados só com fatos do currículo base.

Você copia o texto e faz as alterações no seu próprio arquivo.
"""

import re

import yaml

from vagas.tratamento.normalizar import detectar_tecnologias, sem_acento

# Temas além de tecnologias. Padrões escritos sem acento (o texto é normalizado antes).
TEMAS = {
    "APIs REST": r"\bapis?\b|\brest(ful)?\b|endpoints?",
    "Filas e processamento assíncrono": r"\bfilas?\b|\bqueues?\b|assincron|\bjobs?\b|workers?|horizon|\bsqs\b",
    "Integrações com serviços externos": r"integra|webhooks?|terceiros",
    "Pagamentos": r"pagamentos?|\bpix\b|asaas|gateway|checkout|cobranca",
    "Dados e ETL": r"\betl\b|pipelines?|importacao|processamento de (dados|arquivos)|\bcsv\b|volume de dados",
    "Inteligência artificial": r"\bia\b|inteligencia artificial|openai|\bllms?\b|\bgpt\b|deepseek",
    "Banco de dados e modelagem": r"banco(s)? de dados|modelagem|migrations?|\bsql\b|quer(y|ies)|otimiza",
    "Tempo real (WebSockets)": r"websockets?|reverb|tempo real|real.?time|broadcast",
    "Painéis administrativos": r"\badmin|paineis|painel|dashboards?|backoffice",
    "Sistemas legados e migração": r"legad|legacy|migracao de|refator",
    "Testes automatizados": r"testes?|phpunit|\bpest\b|\btdd\b",
    "Code review e colaboração": r"code review|revisao de codigo|pull requests?",
    "Cloud": r"\baws\b|cloud|serverless|\bs3\b|lambda",
    "Docker e deploy": r"docker|ci/?cd|deploy|containers?",
}

MAX_ATIVIDADES_SUGERIDAS = 4

# Como cada tema entra numa frase do resumo ("Experiência com ...").
TEMAS_NA_FRASE = {
    "APIs REST": "APIs REST",
    "Filas e processamento assíncrono": "filas e processamento assíncrono",
    "Integrações com serviços externos": "integrações com serviços externos",
    "Pagamentos": "integrações de pagamento",
    "Dados e ETL": "pipelines de dados",
    "Inteligência artificial": "uso de inteligência artificial",
    "Banco de dados e modelagem": "modelagem de bancos de dados",
    "Tempo real (WebSockets)": "funcionalidades em tempo real",
    "Painéis administrativos": "painéis administrativos",
    "Sistemas legados e migração": "sistemas legados e migrações",
    "Testes automatizados": "testes automatizados",
    "Code review e colaboração": "code review",
    "Cloud": "cloud",
    "Docker e deploy": "deploy com Docker",
}


def _temas(texto: str) -> set[str]:
    t = sem_acento(texto)
    return {nome for nome, padrao in TEMAS.items() if re.search(padrao, t)}


def _texto_base(base: dict) -> str:
    partes = [base.get("resumo", "")]
    for e in base.get("experiencias", []):
        partes += e.get("atividades", [])
    for p in base.get("projetos", []):
        partes.append(p.get("descricao", ""))
    for itens in (base.get("competencias") or {}).values():
        partes += itens
    return "\n".join(partes)


def analisar(vaga: dict, base: dict, descricao_completa: str | None = None) -> dict:
    """Cruza a vaga com o currículo base e devolve os dados das sugestões."""
    texto_vaga = "\n".join(filter(None, [vaga.get("titulo"), vaga.get("descricao"), descricao_completa]))
    techs_vaga = list(dict.fromkeys(list(vaga.get("tecnologias") or []) + detectar_tecnologias(texto_vaga)))
    temas_vaga = _temas(texto_vaga)

    techs_base = set(detectar_tecnologias(_texto_base(base)))
    comprovadas = [t for t in techs_vaga if t in techs_base]
    lacunas = [t for t in techs_vaga if t not in techs_base]
    temas_comuns = sorted(temas_vaga & _temas(_texto_base(base)))

    def relevancia(texto: str) -> tuple[int, list[str]]:
        techs = [t for t in detectar_tecnologias(texto) if t in techs_vaga]
        temas = [t for t in _temas(texto) if t in temas_vaga]
        # Para explicar o motivo, não repete o tema quando a tecnologia já diz o mesmo ("Docker" x "Docker e deploy").
        explicacao = techs + [t for t in temas if not any(tec in t for tec in techs)]
        return 2 * len(techs) + len(temas), explicacao

    experiencias = []
    for exp in base.get("experiencias", []):
        pontuadas = []
        for i, atividade in enumerate(exp.get("atividades", [])):
            pts, motivos = relevancia(atividade)
            pontuadas.append((pts, -i, atividade, motivos))  # empate: mantém a ordem original
        pontuadas.sort(reverse=True)
        destaque = [(a, m) for pts, _, a, m in pontuadas if pts > 0][:MAX_ATIVIDADES_SUGERIDAS]
        experiencias.append({
            "empresa": exp["empresa"], "cargo": exp["cargo"],
            "destaque": destaque,
            "relevancia": sum(p for p, *_ in pontuadas),
        })

    projetos = sorted(
        ({"nome": p["nome"], "pontos": relevancia(p.get("descricao", ""))[0],
          "motivos": relevancia(p.get("descricao", ""))[1]} for p in base.get("projetos", [])),
        key=lambda p: -p["pontos"],
    )

    return {
        "titulo": sugerir_titulo(vaga),
        "resumo": sugerir_resumo(base, comprovadas, temas_comuns),
        "comprovadas": comprovadas,
        "temas_comuns": temas_comuns,
        "lacunas": lacunas,
        "experiencias": experiencias,
        "projetos": [p for p in projetos if p["pontos"] > 0],
        "usou_descricao_completa": bool((descricao_completa or "").strip()),
    }


def sugerir_titulo(vaga: dict) -> str:
    t = sem_acento(vaga.get("titulo"))
    if re.search(r"full.?stack", t):
        return "Desenvolvedor Full Stack PHP/Laravel"
    if re.search(r"back.?end", t):
        return "Desenvolvedor Backend PHP/Laravel"
    return "Desenvolvedor PHP/Laravel"


def sugerir_resumo(base: dict, comprovadas: list[str], temas: list[str]) -> str:
    """Rascunho montado só com o que o currículo base comprova."""
    ano = re.search(r"desde (\d{4})", base.get("resumo", ""))
    inicio = f"Desenvolvedor de software com experiência profissional desde {ano.group(1)}" if ano \
        else "Desenvolvedor de software"
    frases_temas = [TEMAS_NA_FRASE.get(t, t) for t in temas[:4]]
    ja_citadas = " ".join(frases_temas)
    principais = [t for t in comprovadas if t not in ("PHP", "Laravel") and t not in ja_citadas][:5]
    frases = [f"{inicio}, especializado em PHP e Laravel."]
    if frases_temas:
        frases.append("Experiência com " + _lista(frases_temas) + ".")
    if principais:
        frases.append("Vivência com " + _lista(principais) + ".")
    return " ".join(frases)


def _lista(itens) -> str:
    itens = list(itens)
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def formatar(analise: dict) -> str:
    """Texto final (Markdown) para mostrar no painel e copiar."""
    linhas = [
        "##### Título sugerido",
        analise["titulo"],
        "",
        "##### Rascunho de resumo",
        analise["resumo"],
        "",
    ]
    if analise["comprovadas"] or analise["temas_comuns"]:
        linhas.append("##### O que a vaga pede e você comprova (use os mesmos termos)")
        if analise["comprovadas"]:
            linhas.append("- **Tecnologias:** " + ", ".join(analise["comprovadas"]))
        if analise["temas_comuns"]:
            linhas.append("- **Temas:** " + ", ".join(analise["temas_comuns"]))
        linhas.append("")

    linhas.append("##### Atividades para colocar no topo de cada experiência")
    algum = False
    for exp in sorted(analise["experiencias"], key=lambda e: -e["relevancia"]):
        if not exp["destaque"]:
            continue
        algum = True
        linhas.append(f"**{exp['cargo']} — {exp['empresa']}**")
        for atividade, motivos in exp["destaque"]:
            linhas.append(f"- {atividade}  _({', '.join(motivos)})_")
        linhas.append("")
    if not algum:
        linhas += ["Nenhuma atividade se destacou para esta vaga; mantenha a ordem atual.", ""]

    if analise["projetos"]:
        linhas.append("##### Projetos para destacar")
        for p in analise["projetos"]:
            linhas.append(f"- **{p['nome']}**  _({', '.join(p['motivos'])})_")
        linhas.append("")

    linhas.append("##### O que a vaga pede e não aparece no seu currículo")
    if analise["lacunas"]:
        linhas.append("- " + ", ".join(analise["lacunas"]))
        linhas.append("- Se você tiver alguma experiência com isso, vale incluir. "
                      "Se não tiver, prepare-se para falar sobre o tema na entrevista.")
    else:
        linhas.append("- Nada identificado.")

    if not analise["usou_descricao_completa"]:
        linhas += ["", "_Dica: cole a descrição completa da vaga acima para sugestões mais precisas._"]
    return "\n".join(linhas)


def prompt_para_chat(vaga: dict, base: dict, descricao_completa: str | None = None) -> str:
    """Texto pronto para colar numa conversa com um assistente de IA que você já usa.

    Não faz nenhuma chamada: só monta o texto. Os dados de contato ficam de fora.
    """
    curriculo = yaml.safe_dump(
        {k: v for k, v in base.items() if k not in ("contato", "pontuacao")},
        allow_unicode=True, sort_keys=False,
    )
    descricao = (descricao_completa or "").strip() or (vaga.get("descricao") or "").strip()
    return (
        "Adapte meu currículo para a vaga abaixo. Use somente fatos do meu currículo: "
        "pode reescrever, reordenar e enfatizar, mas não invente tecnologias, números ou experiências. "
        "No final, liste os requisitos da vaga que meu currículo não cobre.\n\n"
        f"=== VAGA ===\nCargo: {vaga.get('titulo')}\nEmpresa: {vaga.get('empresa') or 'não informada'}\n"
        f"Descrição:\n{descricao or '(sem descrição)'}\n\n"
        f"=== MEU CURRÍCULO ===\n{curriculo}"
    )
