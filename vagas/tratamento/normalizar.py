"""Regras que transformam uma vaga bruta (bronze) numa linha padronizada (silver)."""

import re
import unicodedata
from datetime import datetime

# Tecnologias que interessam para o seu perfil. A chave é o nome exibido,
# o valor é a expressão procurada no texto já normalizado (minúsculo, sem acento).
TECNOLOGIAS = {
    "Laravel": r"laravel",
    "PHP": r"\bphp\b",
    "Livewire": r"livewire",
    "Filament": r"filament",
    "Inertia": r"inertia",
    "Symfony": r"symfony",
    "CodeIgniter": r"codeigniter",
    "Vue": r"\bvue",
    "React": r"\breact\b",
    "Next.js": r"\bnext\.?js\b",
    "Node.js": r"\bnode(\.?js)?\b",
    "TypeScript": r"typescript",
    "Python": r"python",
    "PostgreSQL": r"postgres",
    "MySQL": r"mysql",
    "Redis": r"\bredis\b",
    "Docker": r"docker",
    "Kubernetes": r"kubernetes|\bk8s\b",
    "AWS": r"\baws\b|amazon web services",
    "SQS": r"\bsqs\b",
    "Lambda": r"\blambda\b",
    "Terraform": r"terraform",
    "RabbitMQ": r"rabbitmq",
    "Kafka": r"kafka",
    "Filas": r"\bfilas?\b|\bqueues?\b|horizon",
    "Testes": r"phpunit|\bpest\b|testes automatizados|tdd",
    "Tailwind": r"tailwind",
}

# Ordem do menor para o maior: "Pleno/Sênior" vira pleno, porque a vaga aceita pleno.
_NIVEL_TITULO = [
    ("junior", r"\bjunior\b|\bjr\b|entry.level|early career"),
    ("pleno", r"\bpleno\b|\bpl\b(?!/)|\bmid(dle|-level)?\b|intermediario"),
    ("senior", r"\bsenior\b|\bsr\b|especialista|\blead\b|\bstaff\b|principal|arquitet"),
]
_NIVEL_ROTULO = {"junior": "junior", "pleno": "pleno", "senior": "senior", "especialista": "senior"}

_MODELO = [
    ("hibrido", r"\bhibrid[oa]\b|\bhybrid\b"),
    ("remoto", r"\bremot[oa]\b|\bremote\b|home.?office|100% remoto|anywhere"),
    ("presencial", r"\bpresencial\b|\bon.?site\b"),
]


def sem_acento(texto: str | None) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def detectar_nivel(titulo: str, rotulos: list[str] | None = None) -> str | None:
    """Usa primeiro o título; se ele não disser, usa os rótulos (labels) da fonte.

    A descrição não é usada de propósito: ela costuma citar outros níveis
    ("você vai trabalhar com devs sêniores"), o que gera muito falso positivo.
    """
    t = sem_acento(titulo)
    for nivel, padrao in _NIVEL_TITULO:
        if re.search(padrao, t):
            return nivel
    for r in rotulos or []:
        nivel = _NIVEL_ROTULO.get(sem_acento(r))
        if nivel:
            return nivel
    return None


def detectar_modelo(titulo: str, rotulos: list[str] | None = None, descricao: str | None = None) -> str | None:
    """Título e rótulos têm prioridade; a descrição é o último recurso."""
    for texto in (titulo, " ".join(rotulos or []), descricao):
        t = sem_acento(texto)
        for modelo, padrao in _MODELO:
            if re.search(padrao, t):
                return modelo
    return None


def detectar_tecnologias(*textos: str | None) -> list[str]:
    t = sem_acento(" ".join(x for x in textos if x))
    return [nome for nome, padrao in TECNOLOGIAS.items() if re.search(padrao, t)]


def chave_dedupe(titulo: str, empresa: str | None) -> str:
    """Mesma vaga publicada em fontes diferentes gera a mesma chave."""
    titulo = re.sub(r"^\s*\[[^\]]*\]\s*", "", titulo or "")  # tira "[Remoto]" do começo
    base = f"{titulo}|{empresa or ''}"
    return re.sub(r"[^a-z0-9|]", "", sem_acento(base))


def montar_vaga(
    *,
    fonte: str,
    id_externo: str,
    titulo: str,
    url: str,
    empresa: str | None = None,
    descricao: str | None = None,
    localizacao: str | None = None,
    publicada_em: datetime | str | None = None,
    rotulos: list[str] | None = None,
) -> dict:
    """Monta o dicionário no formato da tabela silver.vagas."""
    titulo = (titulo or "").strip()
    empresa = (empresa or "").strip() or None
    tecnologias = detectar_tecnologias(titulo, descricao, " ".join(rotulos or []))
    return {
        "id": f"{fonte}:{id_externo}",
        "fonte": fonte,
        "id_externo": str(id_externo),
        "titulo": titulo,
        "empresa": empresa,
        "descricao": descricao,
        "url": url,
        "localizacao": localizacao,
        "modelo_trabalho": detectar_modelo(titulo, rotulos, descricao),
        "nivel": detectar_nivel(titulo, rotulos),
        "tecnologias": tecnologias,
        "cita_laravel": "Laravel" in tecnologias,
        "chave_dedupe": chave_dedupe(titulo, empresa),
        "publicada_em": publicada_em,
    }
