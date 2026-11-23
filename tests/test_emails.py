"""Testes da extração de vagas de e-mails, com HTML no formato dos alertas reais."""

from vagas.coleta.emails import extrair_vagas

# LinkedIn: o cartão inteiro é um link; dentro dele, título e "Empresa · Local" em linhas separadas.
ALERTA_LINKEDIN = """
<table>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4493218963/?trackingId=abc">
      <table><tr><td><p>Software Engineer - Laravel &amp; Agentic AI</p>
      <p>FullStack · Brasil (Remoto)</p><p>Candidatura simplificada</p></td></tr></table>
    </a>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4491158855/?trackingId=x">
      <p>Desenvolvedor Back-end Jr.</p><p>Smart NX · São Paulo, SP (Híbrido)</p>
    </a>
  </td></tr>
  <tr><td><a href="https://www.linkedin.com/comm/jobs/view/4400000000/">Vagas semelhantes à de Dev PHP</a></td></tr>
  <tr><td><a href="https://www.linkedin.com/comm/jobs/search?keywords=laravel">Ver todas as vagas</a></td></tr>
</table>
"""

# Glassdoor: empresa, nota (opcional), título, local, salário (opcional), "Candidatura rápida", idade.
ALERTA_GLASSDOOR = """
<a href="https://www.glassdoor.com.br/partner/jobListing.htm?jobListingId=1009876543210&src=email">
  <div>Multilog</div><div>3.9 ★</div><div>Desenvolvedor Full Stack Laravel</div>
  <div>Trabalho remoto</div><div>R$ 6 mil (estimativa da empresa)</div><div>Candidatura rápida</div><div>9 dia(s)</div>
</a>
<a href="https://www.glassdoor.com.br/partner/jobListing.htm?jobListingId=1009876543211">
  <div>LIGHTHOUSE SOLUÇÕES</div><div>Desenvolvedor Backend .NET PL/SR</div><div>Trabalho remoto</div><div>24h</div>
</a>
"""

# Indeed: link de rastreamento e cartão fora do link (regra genérica).
ALERTA_INDEED = """
<div>
  <a href="https://cts.indeed.com/v3/clk?url=https%3A%2F%2Fbr.indeed.com%2Frc%2Fclk%3Fjk%3D02e38cfbb781025c%26from%3Dja">
    Desenvolvedor Full Stack PHP/Python
  </a>
  <div>Wagner Pereira &amp; Advogados</div>
  <div>Betópolis, SP</div>
</div>
"""

DATA = "2026-11-22T08:00:00+00:00"


def test_linkedin_separa_titulo_empresa_e_local():
    vagas = {v["id_externo"]: v for v in extrair_vagas(ALERTA_LINKEDIN, "jobalerts-noreply@linkedin.com", "x", DATA)}
    assert set(vagas) == {"4493218963", "4491158855"}  # "Vagas semelhantes" e a busca ficam de fora
    v = vagas["4493218963"]
    assert v["fonte"] == "linkedin"
    assert v["titulo"] == "Software Engineer - Laravel & Agentic AI"
    assert v["empresa"] == "FullStack"
    assert v["localizacao"] == "Brasil (Remoto)"
    assert v["url"] == "https://www.linkedin.com/jobs/view/4493218963"
    assert v["modelo_trabalho"] == "remoto"
    assert v["cita_laravel"] is True
    assert vagas["4491158855"]["modelo_trabalho"] == "hibrido"
    assert vagas["4491158855"]["cita_laravel"] is False
    assert all(x["so_titulo"] for x in vagas.values())  # e-mail não traz a descrição


def test_assunto_do_email_nao_marca_laravel():
    # No LinkedIn o assunto é o título da 1ª vaga; não pode contaminar as outras.
    vagas = extrair_vagas(ALERTA_LINKEDIN, "jobalerts-noreply@linkedin.com", "Senior Laravel Developer na Bluelight")
    jr = next(v for v in vagas if v["id_externo"] == "4491158855")
    assert jr["cita_laravel"] is False


def test_glassdoor_le_empresa_ignora_nota_e_calcula_a_data():
    vagas = {v["id_externo"]: v for v in extrair_vagas(ALERTA_GLASSDOOR, "noreply@glassdoor.com", "x", DATA)}
    v = vagas["1009876543210"]
    assert v["fonte"] == "glassdoor"
    assert (v["titulo"], v["empresa"], v["localizacao"]) == ("Desenvolvedor Full Stack Laravel", "Multilog", "Trabalho remoto")
    assert v["publicada_em"].startswith("2026-11-13")  # 9 dias antes do e-mail
    assert v["cita_laravel"] is True and v["modelo_trabalho"] == "remoto"
    sem_nota = vagas["1009876543211"]
    assert sem_nota["empresa"] == "LIGHTHOUSE SOLUÇÕES" and sem_nota["publicada_em"].startswith("2026-11-22")


ALERTA_INDEED_COM_IDADE = """
<table>
  <tr><td><p>Novas vagas desde ontem</p></td></tr>
  <tr><td><table>
    <tr><td><a href="https://br.indeed.com/rc/clk?jk=aaaaaaaaaaaaaaaa">Dev PHP Pleno</a></td></tr>
    <tr><td>Empresa A</td></tr><tr><td>Remoto</td></tr>
    <tr><td><span>Há 3 dias</span></td></tr>
  </table></td></tr>
  <tr><td><table>
    <tr><td><a href="https://br.indeed.com/rc/clk?jk=bbbbbbbbbbbbbbbb">Dev Laravel Júnior</a></td></tr>
    <tr><td>Empresa B</td></tr><tr><td>Remoto</td></tr>
  </table></td></tr>
</table>
"""


def test_idade_dentro_do_cartao_vira_data_da_vaga():
    vagas = {v["id_externo"]: v for v in extrair_vagas(ALERTA_INDEED_COM_IDADE, "x", "x", DATA)}
    assert vagas["aaaaaaaaaaaaaaaa"]["publicada_em"].startswith("2026-11-19")  # 3 dias antes do e-mail
    # Sem idade no próprio cartão: não pega a da vizinha nem o "desde ontem" do cabeçalho
    assert vagas["bbbbbbbbbbbbbbbb"]["publicada_em"] == DATA


def test_idade_em_dias():
    from vagas.coleta.emails import idade_em_dias
    assert idade_em_dias("Há 3 dias") == 3
    assert idade_em_dias("há 2 semanas") == 14
    assert idade_em_dias("há 5 horas") == 0
    assert idade_em_dias("Publicada ontem") == 1
    assert idade_em_dias("há mais de 30 dias") == 30
    assert idade_em_dias("Novas vagas desde ontem") is None
    assert idade_em_dias("30 horas por semana") is None


def test_mesma_vaga_em_varios_emails_fica_com_a_data_mais_antiga():
    from vagas.coleta.gmail import juntar
    vagas = {}
    for data in ("2026-11-22T08:00:00+00:00", "2026-11-20T08:00:00+00:00", "2026-11-23T08:00:00+00:00"):
        juntar(vagas, {"id": "linkedin:1", "publicada_em": data})
    assert vagas["linkedin:1"]["publicada_em"] == "2026-11-20T08:00:00+00:00"


def test_indeed_com_link_de_rastreamento():
    vagas = extrair_vagas(ALERTA_INDEED, "alert@indeed.com", "Vagas de PHP")
    assert len(vagas) == 1
    v = vagas[0]
    assert v["fonte"] == "indeed"
    assert v["url"] == "https://br.indeed.com/viewjob?jk=02e38cfbb781025c"
    assert v["empresa"] == "Wagner Pereira & Advogados"
    assert v["so_titulo"] is True and "PHP" in v["tecnologias"]


def test_email_sem_vagas():
    assert extrair_vagas("<p>Newsletter</p><a href='https://exemplo.com'>site</a>") == []
    assert extrair_vagas("") == []
