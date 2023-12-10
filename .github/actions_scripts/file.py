"""修改 JSON 文件。

1. 获取对应 JSON 文件并解析。
2. 查询是否有同名插件，若存在则覆盖，并更新时间。
3. 否则添加至最后一行，并附上更新时间。
4. 保存至文件。
"""
import json
import os
import time
from pathlib import Path
from typing import Any

from utils import set_action_outputs

type_info = os.environ["TYPE"]
info = {
    "module_name": os.environ["MODULE_NAME"],
    "pypi_name": os.environ["PYPI_NAME"],
    "name": os.environ["NAME"],
    "description": os.environ["DESCRIPTION"],
    "author": os.environ["AUTHOR"],
    "license": os.environ["LICENSE"],
    "homepage": os.environ["HOMEPAGE"],
    "tags": (
        os.environ["TAGS"]
        .removeprefix("[")
        .removesuffix("]")
        .replace("'", "")
        .replace('"', "")
        .split(",")
    ),
    "is_official": False,
    "time": int(time.time()),
}


def get_json() -> list[dict[str, Any]]:
    """获取对应 JSON 文件并解析。"""
    with Path(type_info + "s.json").open(encoding="utf-8") as f:
        return json.load(f)


def add_info(json_data: list[dict[str, Any]]) -> bool:
    """查询是否有同名插件，若存在则覆盖，并更新时间。"""
    for i in json_data:
        if i["name"] == info["name"]:
            i.update(info)
            return True
    json_data.append(info)
    return False


def save_json(json_data: list[dict[str, Any]]) -> None:
    """保存至文件."""
    with Path(type_info + "s.json").open(mode="w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    json_data = get_json()
    if add_info(json_data):
        set_action_outputs(
            {
                "result": "success",
                "output": "插件信息更新成功",
                "file_json": json.dumps(info),
            }
        )
    else:
        set_action_outputs(
            {
                "result": "success",
                "output": "插件信息添加成功",
                "file_json": json.dumps(info),
            }
        )
    save_json(json_data)
