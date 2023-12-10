"""信息解析。

1. 解析标题的 type，如果不符合就报错。
2. 提取 name、module_name、pypi_name，如果不符合就报错。
3. pypi_name 在 pip 网站中检查，不存在则报错。
"""
import os
import re

from utils import PyPi, set_action_outputs

TITLE = os.environ["TITLE"]
PYPI_NAME = os.environ["PYPI_NAME"]


def parse_title(title: str) -> tuple[str, str]:
    """解析标题。"""
    pattern = r"\[(plugin|adapter|bot)\]:\s*(.+)"
    match = re.match(pattern, title)
    if match:
        return (match.group(1), match.group(2))
    msg = "标题格式错误"
    raise ValueError(msg)


if __name__ == "__main__":
    try:
        PyPi(PYPI_NAME).check_pypi()
        (type_, name) = parse_title(TITLE)
        set_action_outputs(
            {
                "result": "success",
                "output": "",
                "type": type_,
                "name": name,
            }
        )
    except Exception as e:
        set_action_outputs({"result": "error", "output": str(e)})
