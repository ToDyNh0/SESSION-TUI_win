"""Tudo o que depende do sistema operacional -- versao WINDOWS.

A versao Linux deste arquivo tem as mesmas funcoes com o mesmo contrato; o
resto do projeto e identico nas duas pastas.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .i18n import t

NOME = "windows"
APP = "SessionTUI"
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def pasta_perfil_padrao() -> Path:
    """%APPDATA%\\SessionTUI\\profile -- fora do OneDrive e da pasta do programa."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP / "profile"


def preparar_pasta_privada(pasta: Path) -> None:
    # a pasta do usuario no Windows ja herda ACL so dele; o account.json ainda
    # recebe a restricao propria em restringir_arquivo
    pasta.mkdir(parents=True, exist_ok=True)


def restringir_arquivo(caminho) -> bool:
    """Deixa o arquivo legivel so para o usuario atual (melhor esforco).

    No Windows o bit 600 do POSIX nao vale nada, entao usamos o icacls para
    tirar a heranca e dar acesso apenas a quem esta logado.
    """
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass
    usuario = os.environ.get("USERNAME")
    if not usuario:
        return False
    try:
        resultado = subprocess.run(
            ["icacls", str(caminho), "/inheritance:r", "/grant:r", f"{usuario}:F"],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=_SEM_JANELA,
        )
        return resultado.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def abrir_no_sistema(caminho) -> None:
    """Abre o arquivo (ou pasta) no programa padrao do Windows."""
    os.startfile(str(caminho))  # noqa: S606


def copiar_texto(texto: str) -> bool:
    """Copia para a area de transferencia com o clip.exe (UTF-16 com BOM)."""
    try:
        resultado = subprocess.run(
            ["clip"],
            input=texto.encode("utf-16"),
            capture_output=True,
            timeout=5,
            check=False,
            creationflags=_SEM_JANELA,
        )
        return resultado.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def desescapar_caminho(texto: str) -> str:
    """No Windows a barra invertida e separador de pasta: nada a desfazer."""
    return texto


def dica_area_de_transferencia(erro: str) -> str:
    return erro


def configurar_saida() -> None:
    """Nunca morrer por um emoji: caractere sem representacao vira '?'.

    Com a saida redirecionada (`> log.txt`) o Python antigo usa cp1252.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


# --- verificacao automatica do kill switch (Agendador de Tarefas) -----------


def _nome_tarefa(perfil) -> str:
    chave = str(Path(perfil).resolve()).lower().encode("utf-8")
    return f"{APP}-killswitch-{hashlib.sha1(chave).hexdigest()[:10]}"


def comando_verificacao(perfil) -> list[str]:
    """Programa + argumentos que rodam `killswitch check` sem abrir janela.

    Executavel (PyInstaller): o conhost --headless roda o .exe de console sem
    janela. Codigo-fonte: o pythonw.exe, que nao tem console.
    """
    perfil = str(Path(perfil).resolve())
    argumentos = ["killswitch", "check", "--profile", perfil]
    if getattr(sys, "frozen", False):
        conhost = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "conhost.exe"
        return [str(conhost), "--headless", sys.executable, *argumentos]
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    principal = Path(__file__).resolve().parent.parent / "main.py"
    return [str(pythonw if pythonw.exists() else python), str(principal), *argumentos]


def _xml_tarefa(comando: list[str]) -> str:
    inicio = datetime.now().replace(microsecond=0).isoformat()
    programa = escape(comando[0])
    argumentos = escape(subprocess.list2cmdline(comando[1:]))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Session TUI: kill switch check (erases the account after the configured time without access)</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1H</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>{inicio}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>
    <Hidden>true</Hidden>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{programa}</Command>
      <Arguments>{argumentos}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(*argumentos: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks", *argumentos],
        capture_output=True,
        encoding="oem",  # o schtasks responde na pagina de codigo do console (cp850...)
        errors="replace",
        timeout=30,
        check=False,
        creationflags=_SEM_JANELA,
    )


def instalar_agendamento(perfil) -> str:
    """Cria (ou recria) a tarefa que roda a verificacao de hora em hora.

    Usa XML em vez de `schtasks /TR`, que corta o comando em 261 caracteres e
    nao deixa rodar na bateria. Levanta RuntimeError se nao der certo.
    """
    nome = _nome_tarefa(perfil)
    descritor, arquivo = tempfile.mkstemp(suffix=".xml")
    os.close(descritor)
    try:
        Path(arquivo).write_text(_xml_tarefa(comando_verificacao(perfil)), encoding="utf-16")
        resultado = _schtasks("/Create", "/TN", nome, "/XML", arquivo, "/F")
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(t("could not create the scheduled task: {error}", error=exc)) from exc
    finally:
        Path(arquivo).unlink(missing_ok=True)
    if resultado.returncode != 0:
        detalhe = (resultado.stderr or resultado.stdout).strip()
        raise RuntimeError(t("could not create the scheduled task: {error}", error=detalhe))
    return t("Windows Task Scheduler, task '{name}', every hour", name=nome)


def remover_agendamento(perfil) -> bool:
    try:
        return _schtasks("/Delete", "/TN", _nome_tarefa(perfil), "/F").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def agendamento_instalado(perfil) -> bool:
    try:
        return _schtasks("/Query", "/TN", _nome_tarefa(perfil)).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
