"""工具函数。"""

import logging
import subprocess

logger = logging.getLogger()


def run_subprocess(command: str, env: dict[str, str] | None = None) -> None:
    """在子进程中运行命令。"""
    logger.info("Run command: %s", command)
    subprocess.run(command, timeout=60, check=True, shell=True, env=env)  # noqa: S602
