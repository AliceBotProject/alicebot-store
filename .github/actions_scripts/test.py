"""验证脚本能否正常运行。"""
import os
import subprocess

from utils import PyPi, set_action_outputs

PYPI_NAME = os.environ["PYPI_NAME"]
MODULE_NAME = os.environ["MODULE_NAME"]
TYPE = os.environ["TYPE"]


def run_in_subprocess(command: str) -> None:
    """在子进程中运行命令。

    Args:
        command: 要运行的命令。

    Raises:
        ValueError: 命令运行失败。
    """
    try:
        # 要执行的 Python 脚本路径
        subprocess.run(
            command,
            timeout=10,
            check=True,
            shell=True,  # noqa: S602
            capture_output=True,
        )
    except subprocess.TimeoutExpired as e:
        msg = f"脚本执行超时: {e.stdout}"
        raise ValueError(msg) from e
    except subprocess.CalledProcessError as e:
        msg = f"脚本执行错误: {e.stdout}"
        raise ValueError(msg) from e


def check_module(module_name: str) -> bool:
    """检查 module name。"""
    if module_name == "null":
        return False
    if "-" in module_name:
        return False
    run_in_subprocess(f'python -c "import {module_name}"')
    return True


if __name__ == "__main__":
    if TYPE != "bot" and not check_module(MODULE_NAME):
        set_action_outputs({"result": "error", "output": "输入的 module_name 存在问题"})
    else:
        try:
            if TYPE != "bot":
                python_script_path = ".github/actions_scripts/plugin_test.py"
                run_in_subprocess(f"python {python_script_path} {MODULE_NAME} {TYPE}")
            data = PyPi(PYPI_NAME).get_info()
            data.update({"result": "success", "output": "获取 module 元信息成功"})
            set_action_outputs(data)
        except Exception as e:
            set_action_outputs({"result": "error", "output": str(e)})
