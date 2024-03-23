"""数据模型定义。"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeAlias

import httpx
from pydantic import BaseModel

from .utils import run_subprocess


class BaseData(ABC, BaseModel):
    """数据基类。"""

    name: str
    time: int
    is_official: bool

    @abstractmethod
    def validate_data(self) -> None:
        """验证数据。"""

    @abstractmethod
    def to_file_path(self) -> Path:
        """获取文件路径。"""

    def update_data(self) -> None:
        """更新数据。"""
        with self.to_file_path().open(encoding="utf-8") as f:
            json_data: list[dict[str, str | int]] = json.load(f)
        for item in json_data:
            if item["name"] == self.name:
                item.clear()
                item.update(self.model_dump(mode="json"))
                break
        else:
            json_data.append(self.model_dump(mode="json"))
        with self.to_file_path().open("w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)


class _PluginAdapterData(BaseData):
    """插件或适配器数据。"""

    __value__ = ""

    pypi_name: str
    module_name: str

    def validate_data(self) -> None:
        """验证数据。"""
        httpx.get(
            f"https://pypi.org/pypi/{self.pypi_name}/json",
            timeout=5,
        ).raise_for_status()

        run_subprocess(f"pdm add {self.pypi_name}")
        run_subprocess(f"pdm run src/test.py {self.__value__} {self.module_name}")


class PluginData(_PluginAdapterData):
    """插件数据。"""

    __value__ = "plugin"

    def to_file_path(self) -> Path:
        """获取文件路径。"""
        return Path("plugins.json")


class AdapterData(_PluginAdapterData):
    """适配器数据。"""

    __value__ = "adapter"

    def to_file_path(self) -> Path:
        """获取文件路径。"""
        return Path("adapters.json")


class BotData(BaseData):
    """机器人数据。"""

    __value__ = "bot"

    description: str
    author: str
    homepage: str
    tags: str

    def validate_data(self) -> None:
        """验证数据。"""

    def to_file_path(self) -> Path:
        """获取文件路径。"""
        return Path("bots.json")


Data: TypeAlias = PluginData | AdapterData | BotData
