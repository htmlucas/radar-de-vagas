from vagas.pontuacao.nota import calcular

PERFIL = {
    "dominio": ["Laravel", "PHP", "PostgreSQL", "AWS", "Filas"],
    "conhecimento": ["Vue", "React"],
    "cidades_viaveis": ["Betópolis", "Alfaville"],
}


def vaga(**kw):
    base = {"titulo": "Desenvolvedor Laravel", "nivel": "pleno", "modelo_trabalho": "remoto",
            "tecnologias": ["Laravel", "PHP", "PostgreSQL", "Filas"], "descricao": "", "localizacao": None}
    return base | kw


def test_stack_pouco_detalhada_nao_tira_nota_maxima():
    detalhada, _ = calcular(vaga(), PERFIL)
    curta, motivos = calcular(vaga(tecnologias=["Laravel", "PHP"]), PERFIL)
    assert curta < detalhada
    assert any("Descrição curta" in m for m in motivos)


def test_front_end_puro_perde_pontos():
    back, _ = calcular(vaga(), PERFIL)
    front, _ = calcular(vaga(titulo="Desenvolvedor Front-end"), PERFIL)
    assert front < back


def test_vaga_ideal_tira_nota_maxima():
    n, motivos = calcular(vaga(), PERFIL)
    assert n == 100
    assert any("domina" in m for m in motivos)


def test_tecnologia_desconhecida_reduz_a_nota():
    boa, _ = calcular(vaga(), PERFIL)
    pior, motivos = calcular(vaga(tecnologias=["Laravel", "PHP", "PostgreSQL", "Kubernetes"]), PERFIL)
    assert pior < boa
    assert any("Kubernetes" in m for m in motivos)


def test_presencial_na_regiao_vale_quase_como_remoto():
    longe, _ = calcular(vaga(modelo_trabalho="presencial", localizacao="Porto Alegre"), PERFIL)
    perto, motivos = calcular(vaga(modelo_trabalho="hibrido", localizacao="Betópolis, SP"), PERFIL)
    assert perto > longe
    assert any("Betópolis" in m for m in motivos)


def test_cargo_que_nao_e_de_desenvolvimento_cai():
    dev, _ = calcular(vaga(), PERFIL)
    suporte, _ = calcular(vaga(titulo="Analista de Suporte N1/N2"), PERFIL)
    devops, _ = calcular(vaga(titulo="Devops Pleno"), PERFIL)
    assert suporte < 60 and devops < 60 < dev


def test_senior_fica_abaixo_de_pleno():
    pleno, _ = calcular(vaga(), PERFIL)
    senior, _ = calcular(vaga(nivel="senior"), PERFIL)
    assert senior < pleno
