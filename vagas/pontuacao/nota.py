"""Nota de compatibilidade (0 a 100) entre uma vaga e o seu perfil.

É uma regra determinística, barata e explicável: roda para todas as vagas a
cada coleta. A análise fina (com IA) fica para a geração do currículo, que só
roda nas vagas que você escolher.

Composição:
    Stack ............ 60  (tecnologias da vaga que você domina ou conhece)
    Nível ............ 15  (pleno é o ideal para o seu tempo de experiência)
    Modelo/local ..... 15  (remoto, ou híbrido/presencial em cidade viável)
    Tipo de cargo .... 10  (vaga de desenvolvimento x DevOps, suporte, QA...)
"""

import re

from vagas.tratamento.normalizar import sem_acento

PESO_STACK, PESO_NIVEL, PESO_MODELO, PESO_CARGO = 60, 15, 15, 10
MIN_TECHS_CONFIAVEL = 4
FATOR_CARGO_OUTRO = 0.6

_NIVEL = {"pleno": 15, "junior": 11, None: 10, "senior": 3}

_CARGO_DEV = re.compile(
    r"desenvolvedor|developer|programador|engineer|engenheir[oa] de software|"
    r"full.?stack|back.?end|analista (de )?(sistemas|desenvolv)|\bdev\b"
)
_CARGO_OUTRO = re.compile(r"devops|suporte|support|\bqa\b|qualidade|infraestrutura|\bdados\b|data engineer|sre\b")


def calcular(vaga: dict, perfil: dict) -> tuple[int, list[str]]:
    """Devolve (nota, motivos). `perfil` é a seção `pontuacao` do currículo base."""
    motivos: list[str] = []

    # --- Stack
    dominio = set(perfil.get("dominio", []))
    conhece = set(perfil.get("conhecimento", []))
    techs = list(vaga.get("tecnologias") or [])
    if techs:
        fortes = [t for t in techs if t in dominio]
        medias = [t for t in techs if t in conhece]
        faltam = [t for t in techs if t not in dominio and t not in conhece]
        stack = PESO_STACK * (len(fortes) + 0.5 * len(medias)) / len(techs)
        if len(techs) < MIN_TECHS_CONFIAVEL:
            # Pouca evidência (ex.: trecho curto da Adzuna): não dá para cravar nota máxima.
            stack = min(stack, PESO_STACK * 0.75)
            motivos.append("❔ Descrição curta: stack pouco detalhada")
        if fortes:
            motivos.append("✅ Você domina: " + ", ".join(fortes))
        if medias:
            motivos.append("➕ Você conhece: " + ", ".join(medias))
        if faltam:
            motivos.append("⚠️ Pouca ou nenhuma experiência: " + ", ".join(faltam))
    else:
        stack = PESO_STACK * 0.5
        motivos.append("❔ A vaga não detalha a stack")

    # --- Nível
    nivel = vaga.get("nivel")
    pts_nivel = _NIVEL.get(nivel, 10)
    if nivel == "senior":
        motivos.append("⚠️ Vaga sênior")
    elif nivel is None:
        motivos.append("❔ Nível não informado")

    # --- Modelo de trabalho e local
    modelo = vaga.get("modelo_trabalho")
    texto_local = sem_acento(" ".join(filter(None, [vaga.get("localizacao"), vaga.get("titulo"), vaga.get("descricao")])))
    cidade = next((c for c in perfil.get("cidades_viaveis", []) if sem_acento(c) in texto_local), None)
    if modelo == "remoto":
        pts_modelo = 15
        motivos.append("🏠 Remoto")
    elif cidade:
        pts_modelo = 13
        motivos.append(f"📍 {modelo.capitalize() if modelo else 'Local'} em {cidade}")
    elif modelo == "hibrido":
        pts_modelo = 4
        motivos.append("🚗 Híbrido fora da sua região")
    elif modelo == "presencial":
        pts_modelo = 2
        motivos.append("🚗 Presencial fora da sua região")
    else:
        pts_modelo = 8
        motivos.append("❔ Modelo de trabalho não informado")

    # --- Tipo de cargo
    titulo = sem_acento(vaga.get("titulo"))
    fator = 1.0
    if _CARGO_OUTRO.search(titulo) and not re.search(r"desenvolvedor|developer|programador", titulo):
        # Stack parecida não salva um cargo de outra área (DevOps, suporte...): reduz a nota toda.
        pts_cargo, fator = 0, FATOR_CARGO_OUTRO
        motivos.append("⚠️ Cargo não é de desenvolvimento")
    elif re.search(r"front.?end", titulo) and not re.search(r"full.?stack|back.?end", titulo):
        pts_cargo = 5
        motivos.append("⚠️ Vaga focada em front-end")
    elif _CARGO_DEV.search(titulo):
        pts_cargo = 10
    else:
        pts_cargo = 5

    nota = round((stack + pts_nivel + pts_modelo + pts_cargo) * fator)
    return max(0, min(100, nota)), motivos
