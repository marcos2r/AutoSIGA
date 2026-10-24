"""
Edge do AutoSIGA aberto como programa à parte, para continuar aberto e logado depois do robô.

O robô não lança o Edge pelo Playwright (que o fecha junto com o AutoSIGA): abre o
`msedge.exe` com a porta de depuração e só se conecta a ele (CDP). Ao terminar, o robô
se desconecta e o Edge fica aberto para o usuário consultar o SIGA. Na próxima execução,
se esse Edge ainda estiver aberto, o robô se conecta a ele e reaproveita o login.

A porta é escolhida pelo próprio Edge (`--remote-debugging-port=0`), que a grava no arquivo
`DevToolsActivePort` da pasta do perfil, e só aceita conexões do próprio computador.
"""

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

ARQUIVO_PORTA = "DevToolsActivePort"
_ESPERA_PORTA_S = 20
_RELATIVO_EDGE = Path("Microsoft") / "Edge" / "Application" / "msedge.exe"
_ARGS_EDGE = [
    "--no-first-run",
    "--no-default-browser-check",
    "--start-maximized",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-gpu-compositing",
]


def localizar_edge() -> str | None:
    """Caminho do `msedge.exe` nas pastas de instalação do Windows, ou None se não houver."""
    for variavel in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(variavel)
        if base and (Path(base) / _RELATIVO_EDGE).is_file():
            return str(Path(base) / _RELATIVO_EDGE)
    return shutil.which("msedge")


def porta_ativa(user_data_dir: str) -> int | None:
    """Porta de depuração gravada pelo Edge no perfil, ou None se o arquivo não existe ou é inválido.

    O arquivo pode sobrar de um Edge que fechou de forma abrupta; quem chama confirma
    tentando conectar.
    """
    try:
        primeira = (Path(user_data_dir) / ARQUIVO_PORTA).read_text(encoding="utf-8").splitlines()[0]
        porta = int(primeira.strip())
    except (OSError, IndexError, ValueError):
        return None
    return porta if 0 < porta < 65536 else None


def abrir_edge(executavel: str, user_data_dir: str) -> None:
    """Abre o Edge desligado do AutoSIGA, para ele seguir aberto quando o AutoSIGA fechar."""
    # Sem o arquivo antigo, a espera só termina com a porta do Edge que está abrindo agora
    (Path(user_data_dir) / ARQUIVO_PORTA).unlink(missing_ok=True)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([executavel, "--remote-debugging-port=0", f"--user-data-dir={user_data_dir}", *_ARGS_EDGE],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)


def aguardar_porta(user_data_dir: str, limite_s: float = _ESPERA_PORTA_S) -> int:
    """Espera o Edge recém-aberto gravar a porta de depuração.

    Raises:
        RuntimeError: O Edge não gravou a porta no tempo limite (em geral, o mesmo perfil já
            está aberto num Edge sem a porta, e a janela nova foi entregue a ele).
    """
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        porta = porta_ativa(user_data_dir)
        if porta:
            return porta
        time.sleep(0.25)
    raise RuntimeError("O Edge do AutoSIGA não liberou a conexão para o robô. "
                       "Feche todas as janelas desse Edge e rode de novo.")


def conectar_edge(p: Any, user_data_dir: str) -> Any:
    """Conecta ao Edge do AutoSIGA que já está aberto ou, se não houver, abre um e conecta.

    Args:
        p: Instância do `sync_playwright()`.
        user_data_dir: Pasta do perfil do Edge do AutoSIGA (guarda o login).

    Returns:
        Browser do Playwright conectado por CDP; fechar o Playwright só desconecta.
    """
    porta = porta_ativa(user_data_dir)
    if porta:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}", timeout=5000)
            logging.info("Reaproveitando o Edge do AutoSIGA que já estava aberto.")
            return browser
        except Exception as e:
            # Sobra de um Edge que fechou sem apagar o arquivo: abre outro
            logging.info(f"Porta {porta} do Edge anterior não responde ({e}); abrindo um Edge novo.")
    executavel = localizar_edge()
    if not executavel:
        raise RuntimeError("Microsoft Edge não encontrado neste computador.")
    abrir_edge(executavel, user_data_dir)
    porta = aguardar_porta(user_data_dir)
    return p.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}", timeout=15000)
