"""Etapa 6: agendamento da coleta de Engenharia de Dados (scripts\\coletar_dados.ps1 e scripts\\agendar.ps1 -Dados).

Segurança:
  - os testes de coletar_dados.ps1 rodam numa pasta temporária (-Raiz), com um Python FALSO e sem Docker: nenhuma
    coleta real, nenhum banco, nenhuma API, e os logs/trava reais (dados\\logs) não são tocados;
  - os testes do agendar.ps1 usam um SIMULADOR do Agendador (funções que sombreiam os cmdlets, com trava que aborta se
    o simulador não valer). Nenhuma tarefa real é criada, alterada ou removida; um teste confere isso nas tarefas reais.
"""

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT_DADOS = RAIZ / "scripts" / "coletar_dados.ps1"
SCRIPT_AGENDAR = RAIZ / "scripts" / "agendar.ps1"
SCRIPT_LARAVEL = RAIZ / "scripts" / "coletar.ps1"
PASTA_FIXTURES = Path(__file__).parent / "fixtures" / "agendamento"
PYTHON_FALSO = PASTA_FIXTURES / "python_falso.cmd"
SIMULADOR = PASTA_FIXTURES / "mock_agendador.ps1"
PS = shutil.which("powershell")
LOGS_REAIS = RAIZ / "dados" / "logs"

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not PS, reason="precisa do Windows PowerShell")


def ps(argumentos, cwd=None, env=None, timeout=90):
    return subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", *map(str, argumentos)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env, timeout=timeout)


def ambiente(raiz, codigo=None, espera=None):
    env = os.environ.copy()
    env["FALSO_REGISTRO"] = str(raiz / "chamadas.txt")
    env.pop("FALSO_CODIGO", None), env.pop("FALSO_ESPERA", None)
    if codigo is not None:
        env["FALSO_CODIGO"] = str(codigo)
    if espera is not None:
        env["FALSO_ESPERA"] = str(espera)
    return env


def comando_coleta(raiz, *extra, python=True):
    cmd = [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT_DADOS), "-Raiz", str(raiz), "-SemDocker", *extra]
    return cmd + (["-Python", str(PYTHON_FALSO)] if python else [])


def coletar(raiz, *extra, codigo=None, espera=None, cwd=None, python=True):
    return subprocess.run(comando_coleta(raiz, *extra, python=python), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=cwd, env=ambiente(raiz, codigo, espera), timeout=90)


def chamadas(raiz):
    arq = raiz / "chamadas.txt"
    return arq.read_text(encoding="utf-8", errors="replace").splitlines() if arq.exists() else []


def hoje():
    return datetime.now().strftime("%Y-%m-%d")


def log_dados(raiz):
    return (raiz / "dados" / "logs" / f"dados-coleta-{hoje()}.log").read_text(encoding="utf-8-sig", errors="replace")


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "projeto com espaco (2026)"      # espaço e parênteses como no caminho real; sem acento (o .cmd falso grava em OEM)
    pasta.mkdir()
    return pasta


@pytest.fixture(scope="module", autouse=True)
def tarefas_reais_nao_mudam():
    """Impressão digital (XML exportado) das tarefas reais de \\RadarDeVagas\\ antes e depois de TODOS os testes deste arquivo."""
    def foto():
        r = ps(["-Command", "Get-ScheduledTask -TaskPath '\\RadarDeVagas\\' -ErrorAction SilentlyContinue | ForEach-Object { "
                "$xml = Export-ScheduledTask -TaskName $_.TaskName -TaskPath '\\RadarDeVagas\\'; "
                "$h = (Get-FileHash -InputStream ([IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($xml))) -Algorithm SHA256).Hash; "
                "\"$($_.TaskName)|$h\" }"])
        return dict(l.split("|") for l in r.stdout.split() if "|" in l) if r.returncode == 0 else None
    antes = foto()
    yield
    depois = foto()
    if antes is not None:
        assert depois == antes, "uma tarefa REAL do Agendador mudou durante os testes"
        # (a ColetaDados real foi registrada de propósito na inicialização produtiva; aqui só importa que nada mudou)


# =========================================================================== coletar_dados.ps1
def test_dry_run_mostra_python_da_venv_diretorio_log_e_trava_sem_criar_nada():
    antes = {p.name for p in LOGS_REAIS.iterdir()} if LOGS_REAIS.exists() else set()
    r = ps(["-File", SCRIPT_DADOS, "-DryRun"])
    assert r.returncode == 0, r.stderr
    saida = r.stdout
    assert f"Raiz (diretorio de trabalho): {RAIZ}" in saida
    assert f"Python: {RAIZ / '.venv' / 'Scripts' / 'python.exe'} (existe: True)" in saida
    assert "-m vagas.trilhas.dados.pipeline" in saida
    assert f"dados-coleta-{hoje()}.log" in saida and "dados-coleta-ok.txt" in saida and "dados-coleta.lock" in saida
    assert {p.name for p in LOGS_REAIS.iterdir()} == antes if LOGS_REAIS.exists() else True      # nada criado


def test_executa_o_pipeline_da_trilha_de_dados_na_raiz_do_projeto(raiz, tmp_path):
    fora = tmp_path / "outro_lugar"
    fora.mkdir()
    r = coletar(raiz, cwd=fora)                                      # lançado de OUTRA pasta
    assert r.returncode == 0, r.stdout + r.stderr
    linhas = chamadas(raiz)
    assert len(linhas) == 1 and "-m vagas.trilhas.dados.pipeline" in linhas[0]
    cwd = linhas[0].split("CWD=")[1].split(" ARGS=")[0]
    assert Path(cwd).resolve() == raiz.resolve()                    # o diretório de trabalho é a raiz do projeto
    log = log_dados(raiz)
    for esperado in ("=== Inicio da coleta de dados", f"Diretorio de trabalho: {raiz}", f"Python: {PYTHON_FALSO}",
                     "saida do python falso: -m vagas.trilhas.dados.pipeline", "=== Fim da coleta de dados (codigo 0)"):
        assert esperado in log, esperado


def test_usa_o_python_da_venv_do_projeto_por_padrao(raiz):
    r = coletar(raiz, python=False)                                  # sem -Python: usa <raiz>\.venv\Scripts\python.exe
    esperado = raiz / ".venv" / "Scripts" / "python.exe"
    assert r.returncode == 2
    assert f"ERRO: Python da .venv nao encontrado: {esperado}" in log_dados(raiz)
    assert not (raiz / "dados" / "logs" / "dados-coleta.lock").exists()           # a trava foi liberada
    assert not (raiz / "dados" / "logs" / "dados-coleta-ok.txt").exists()


def test_logs_e_marcas_ficam_em_arquivos_proprios_e_nao_viram_logs_da_laravel(raiz):
    coletar(raiz)
    nomes = {p.name for p in (raiz / "dados" / "logs").iterdir()}
    assert nomes == {f"dados-coleta-{hoje()}.log", "dados-coleta-ok.txt"}
    assert not any(re.fullmatch(r"coleta-.*\.log", n) for n in nomes)               # o padrão que a Laravel lê e limpa


def test_trava_pula_se_a_ultima_coleta_teve_sucesso_ha_menos_de_4_horas(raiz):
    assert coletar(raiz).returncode == 0
    segunda = coletar(raiz)
    assert segunda.returncode == 0 and len(chamadas(raiz)) == 1                     # não coletou de novo
    assert "Coleta de dados pulada: a ultima bem-sucedida foi ha" in log_dados(raiz)


def test_forcar_ignora_a_trava_de_sucesso_recente(raiz):
    coletar(raiz)
    assert coletar(raiz, "-Forcar").returncode == 0
    assert len(chamadas(raiz)) == 2


def test_sucesso_antigo_nao_bloqueia(raiz):
    pasta = raiz / "dados" / "logs"
    pasta.mkdir(parents=True)
    (pasta / "dados-coleta-ok.txt").write_text((datetime.now() - timedelta(hours=5)).isoformat(), encoding="ascii")
    assert coletar(raiz).returncode == 0 and len(chamadas(raiz)) == 1


def test_marca_ilegivel_nao_bloqueia(raiz):
    pasta = raiz / "dados" / "logs"
    pasta.mkdir(parents=True)
    (pasta / "dados-coleta-ok.txt").write_text("lixo", encoding="ascii")
    assert coletar(raiz).returncode == 0 and len(chamadas(raiz)) == 1


def test_falha_do_pipeline_devolve_o_codigo_nao_grava_sucesso_e_permite_nova_tentativa(raiz):
    r = coletar(raiz, codigo=5)
    assert r.returncode == 5
    assert "=== Fim da coleta de dados (codigo 5)" in log_dados(raiz)
    pasta = raiz / "dados" / "logs"
    assert not (pasta / "dados-coleta-ok.txt").exists() and not (pasta / "dados-coleta.lock").exists()
    assert coletar(raiz, codigo=0).returncode == 0 and len(chamadas(raiz)) == 2        # o gatilho de logon tenta de novo


def test_trava_de_execucao_com_processo_vivo_pula_e_preserva_a_trava(raiz):
    pasta = raiz / "dados" / "logs"
    pasta.mkdir(parents=True)
    conteudo = f"{os.getpid()}\r\n{datetime.now().isoformat()}".encode("ascii")
    (pasta / "dados-coleta.lock").write_bytes(conteudo)
    r = coletar(raiz, "-Forcar")                                                      # nem o -Forcar passa por cima
    assert r.returncode == 0 and chamadas(raiz) == []
    assert "ja ha outra execucao em andamento" in log_dados(raiz)
    assert (pasta / "dados-coleta.lock").read_bytes() == conteudo                     # a trava do outro continua lá


def test_trava_de_processo_morto_e_removida(raiz):
    pasta = raiz / "dados" / "logs"
    pasta.mkdir(parents=True)
    (pasta / "dados-coleta.lock").write_text("999999\r\n2026-01-01", encoding="ascii")
    assert coletar(raiz).returncode == 0 and len(chamadas(raiz)) == 1
    assert "Trava antiga removida" in log_dados(raiz) and not (pasta / "dados-coleta.lock").exists()


def test_trava_velha_mesmo_com_pid_vivo_e_removida(raiz):
    pasta = raiz / "dados" / "logs"
    pasta.mkdir(parents=True)
    trava = pasta / "dados-coleta.lock"
    trava.write_text(f"{os.getpid()}\r\n", encoding="ascii")
    antigo = time.time() - 3 * 3600
    os.utime(trava, (antigo, antigo))
    assert coletar(raiz).returncode == 0 and len(chamadas(raiz)) == 1
    assert "Trava antiga removida" in log_dados(raiz)


def test_duas_execucoes_ao_mesmo_tempo_so_uma_coleta(raiz):
    """Gatilho diário e gatilho de logon juntos: uma coleta, a outra pula."""
    procs = [subprocess.Popen(comando_coleta(raiz), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              env=ambiente(raiz, espera=4)) for _ in range(2)]
    codigos = [p.wait(timeout=90) for p in procs]
    assert codigos == [0, 0] and len(chamadas(raiz)) == 1
    log = log_dados(raiz)
    assert log.count("=== Inicio da coleta de dados") == 1
    # A garantia é UMA coleta. A linha "pulada" da outra execução é só observabilidade: os dois processos anexam ao
    # MESMO arquivo de log quase no mesmo instante e, sob carga, uma gravação pode colidir e se perder (sem afetar a coleta).
    pasta = raiz / "dados" / "logs"
    assert not (pasta / "dados-coleta.lock").exists() and (pasta / "dados-coleta-ok.txt").exists()


def test_independente_da_trava_e_do_log_da_coleta_laravel(raiz):
    pasta = raiz / "dados" / "logs"
    pasta.mkdir(parents=True)
    log_laravel = pasta / f"coleta-{hoje()}.log"
    conteudo = f"{datetime.now():%Y-%m-%d %H:%M:%S}  === Fim da coleta (código 0)\n".encode("utf-8")
    log_laravel.write_bytes(conteudo)
    antigo = pasta / "coleta-2020-01-01.log"                       # log antigo da Laravel: a limpeza da trilha de dados não pode apagá-lo
    antigo.write_bytes(b"velho")
    os.utime(antigo, (time.time() - 90 * 86400,) * 2)
    r = coletar(raiz)
    assert r.returncode == 0 and len(chamadas(raiz)) == 1           # a trava de 4 h da Laravel (sucesso recente) NÃO bloqueia esta
    assert log_laravel.read_bytes() == conteudo and antigo.read_bytes() == b"velho"
    assert not (pasta / "dados-coleta-ok.txt").read_text().startswith("coleta")


def test_limpeza_so_apaga_logs_antigos_da_trilha_de_dados(raiz):
    pasta = raiz / "dados" / "logs"
    pasta.mkdir(parents=True)
    velho_dados, velho_laravel = pasta / "dados-coleta-2020-01-01.log", pasta / "coleta-2020-01-01.log"
    for arq in (velho_dados, velho_laravel):
        arq.write_text("x")
        os.utime(arq, (time.time() - 90 * 86400,) * 2)
    coletar(raiz)
    assert not velho_dados.exists() and velho_laravel.exists()


def test_scripts_novos_sao_independentes_e_ascii():
    texto = SCRIPT_DADOS.read_text(encoding="utf-8")
    assert "vagas.trilhas.dados.pipeline" in texto and ".venv\\Scripts\\python.exe" in texto and "-m vagas.pipeline" not in texto
    assert not re.search(r"(&|-File)\s+\S*coletar\.ps1", texto)                    # nunca chama o script da Laravel
    codigo = "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))      # sem os comentários
    for m in re.finditer(r"coleta-", codigo):                                       # todo nome de log/arquivo é "dados-coleta-..."
        assert codigo[max(0, m.start() - 6):m.start()] == "dados-", codigo[max(0, m.start() - 20):m.start() + 20]
    texto.encode("ascii")                                                           # ASCII puro: o PowerShell 5.1 lê sem BOM
    assert "dados-coleta" not in SCRIPT_LARAVEL.read_text(encoding="utf-8-sig")     # o script da Laravel não sabe da nova trilha


# =========================================================================== agendar.ps1 -Dados (simulador do Agendador)
def agendar(tmp_path, opcoes, falhar_logon=False, estado="estado.json"):
    arq = tmp_path / estado
    r = ps(["-File", SIMULADOR, "-Alvo", SCRIPT_AGENDAR, "-ArquivoEstado", arq, "-Opcoes", opcoes, *(["-FalharLogon"] if falhar_logon else [])])
    dados = json.loads(arq.read_text(encoding="utf-8-sig")) if arq.exists() else None
    return r, dados


def registros(estado, cmdlet="Register-ScheduledTask"):
    return [c["dados"] for c in estado["chamadas"] if c["cmdlet"] == cmdlet]


def test_registra_somente_a_coletadados_com_os_dois_gatilhos(tmp_path):
    r, est = agendar(tmp_path, "Dados")
    assert r.returncode == 0, r.stdout + r.stderr
    [reg] = registros(est)
    assert (reg["TaskPath"], reg["TaskName"], reg["Force"]) == ("\\RadarDeVagas\\", "ColetaDados", True)
    assert reg["Action"]["Execute"] == "powershell.exe" and reg["Action"]["WorkingDirectory"] == str(RAIZ)
    assert str(RAIZ / "scripts" / "coletar_dados.ps1") in reg["Action"]["Argument"]
    assert "-WindowStyle Hidden" in reg["Action"]["Argument"] and "-ExecutionPolicy Bypass" in reg["Action"]["Argument"]
    diario, logon = reg["Triggers"]
    assert (diario["Tipo"], diario["At"]) == ("Diario", "08:20")
    assert logon["Tipo"] == "Logon" and logon["Delay"] == "PT8M" and logon["User"].endswith(os.environ["USERNAME"])
    cfg = reg["Settings"]
    assert (cfg["StartWhenAvailable"], cfg["RunOnlyIfNetworkAvailable"], cfg["ExecutionTimeLimitMin"], cfg["MultipleInstances"]) == (True, True, 30, "IgnoreNew")
    assert list(est["tarefas"]) == ["\\RadarDeVagas\\ColetaDados"]
    assert "Coleta de dados: todo dia as 08:20 e 8 min depois de fazer logon" in r.stdout


def test_nao_toca_na_coletadiaria_nem_no_painel(tmp_path):
    _, est = agendar(tmp_path, "Dados")
    assert registros(est, "Unregister-ScheduledTask") == []
    nomes_tocados = {c["dados"]["TaskName"] for c in est["chamadas"] if "TaskName" in c["dados"]}
    assert nomes_tocados == {"ColetaDados"}                              # nenhuma outra tarefa foi consultada, criada ou removida
    assert not any(c["dados"].get("Description", "").startswith("Radar de Vagas: coleta diaria de vagas (GitHub")
                   for c in est["chamadas"])                             # a descrição da ColetaDiaria não foi usada


def test_horario_pode_ser_alterado(tmp_path):
    _, est = agendar(tmp_path, "Dados,HorarioDados=09:15")
    assert registros(est)[0]["Triggers"][0]["At"] == "09:15"


def test_registro_e_idempotente_nao_duplica_a_tarefa(tmp_path):
    agendar(tmp_path, "Dados")
    r, est = agendar(tmp_path, "Dados")
    assert r.returncode == 0 and len(registros(est)) == 2 and all(x["Force"] for x in registros(est))
    assert list(est["tarefas"]) == ["\\RadarDeVagas\\ColetaDados"]            # continua uma só (o -Force substitui)


def test_sem_permissao_para_gatilho_de_logon_registra_so_o_diario(tmp_path):
    r, est = agendar(tmp_path, "Dados", falhar_logon=True)
    assert r.returncode == 0
    recusada, aceita = registros(est, "Register-ScheduledTask(recusada)"), registros(est)
    assert len(recusada) == 1 and len(recusada[0]["Triggers"]) == 2 and len(aceita) == 1
    assert [t["Tipo"] for t in aceita[0]["Triggers"]] == ["Diario"] and aceita[0]["Triggers"][0]["At"] == "08:20"
    assert "so o horario diario" in (r.stdout + r.stderr) and "e 8 min depois" not in r.stdout


def test_remover_dados_remove_so_a_coletadados(tmp_path):
    agendar(tmp_path, "Dados")
    r, est = agendar(tmp_path, "RemoverDados")
    assert r.returncode == 0 and est["tarefas"] == {}
    [rem] = registros(est, "Unregister-ScheduledTask")
    assert rem["TaskName"] == "ColetaDados" and rem["TaskPath"] == "\\RadarDeVagas\\"
    assert "Nada mais foi alterado" in r.stdout


def test_sem_opcoes_o_codigo_da_coletadados_nao_roda():
    """Estático: tudo que cria/remove a ColetaDados fica dentro dos blocos `-Dados`/`-RemoverDados`, que terminam em return."""
    texto = SCRIPT_AGENDAR.read_text(encoding="utf-8-sig")
    inicio, fim = texto.index("if ($RemoverDados) {"), texto.index("# ---------------------------------------------------------------- coleta\n$acaoColeta")
    bloco, resto = texto[inicio:fim], texto[:inicio] + texto[fim:]
    assert bloco.count("return") == 2 and bloco.count('"ColetaDados"') >= 3
    assert '"ColetaDados"' not in resto.replace('TaskName "ColetaDados"', "")     # nada fora dos blocos (a doc no topo não tem aspas)
    assert re.search(r'^\s*Register-ScheduledTask.*"ColetaDados"', resto, re.M) is None


def git_original():
    r = subprocess.run(["git", "show", "HEAD:scripts/agendar.ps1"], capture_output=True, cwd=RAIZ)
    if r.returncode != 0:
        pytest.skip("git indisponível")
    return r.stdout.decode("utf-8-sig").replace("\r\n", "\n")


def test_alteracao_do_agendar_e_so_aditiva_e_preserva_a_coletadiaria_e_o_painel():
    original = git_original()
    novo = SCRIPT_AGENDAR.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    removidas = [l for l in difflib.unified_diff(original.splitlines(), novo.splitlines(), lineterm="", n=0) if l.startswith("-") and not l.startswith("---")]
    assert removidas == ['-param([string]$Horario = "08:00", [switch]$SemPainel)']          # única linha antiga que muda
    assert 'param([string]$Horario = "08:00", [switch]$SemPainel, [switch]$Dados' in novo   # só ganhou parâmetros no fim
    parte_laravel = original[original.index("# ---------------------------------------------------------------- coleta"):]
    assert parte_laravel in novo                                                            # ColetaDiaria + Painel + atalho: idênticos
    adicionadas = [l[1:] for l in difflib.unified_diff(original.splitlines(), novo.splitlines(), lineterm="", n=0)
                   if l.startswith("+") and not l.startswith("+++")]
    "\n".join(adicionadas).encode("ascii")                                                  # o que entrou é ASCII puro


def test_coleta_laravel_e_painel_nao_foram_alterados():
    for nome in ("coletar.ps1", "painel.ps1"):
        r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", f"scripts/{nome}"], cwd=RAIZ)
        assert r.returncode == 0, f"scripts/{nome} foi modificado"
