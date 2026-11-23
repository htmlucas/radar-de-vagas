import pytest

from vagas.coleta.github import extrair_empresa


@pytest.mark.parametrize(
    "titulo, esperado",
    [
        ("[Remoto] Desenvolvedor PHP/Laravel (Pleno) na Empreender", "Empreender"),
        ("[Remoto] Back-end developer Net- (Strider)", "Strider"),
        ("[Remoto] Senior Full-stack Engineer - React.js, Nest.js, Kafka(Strider))", "Strider"),
        ("[Remoto] Desenvolvedor(a) Backend Pleno - White Label e Plataforma - Mimix AI", "Mimix AI"),
        ("[Remoto] Senior Backend Engineer PHP + SABRE/GDS na PlanitEasy (PJ, LATAM)", "PlanitEasy"),
        ("Hibrido São Paulo - Programador PHP Pleno - Tech For TI", "Tech For TI"),
        # Casos em que o melhor é admitir que não sabe:
        ("[Remoto] Full-stack Engineer (Net+React)", None),
        ("[Joinville/SC] Back-end ou Full Stack Developer (Node.js + React)", None),
        ("São Paulo - Desenvolvedor(a) Backend Júnior (PHP e o framework Laravel e banco de dados relacionais)", None),
        ("Analista de Desenvolvimento Sênior - (Presencial - Morumbi/SP)", None),
        ("[Híbrido] Engenheiro de IA (AI Stack) - Programa AI Stack - Rio de Janeiro - RJ", None),
    ],
)
def test_extrair_empresa(titulo, esperado):
    assert extrair_empresa(titulo) == esperado
