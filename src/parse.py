"""解析 Issue。"""

import re

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from .context import Context
from .models import AdapterData, BotData, Data, PluginData


def parse_title(title: str) -> tuple[type[Data], str]:
    """解析标题。"""
    result = re.match(r"\[(.+)\]:\s*(.+)", title)
    if result is None:
        raise ValueError("标题格式错误")
    match result.group(1):
        case PluginData.__value__:
            return (PluginData, result.group(2))
        case AdapterData.__value__:
            return (AdapterData, result.group(2))
        case BotData.__value__:
            return (BotData, result.group(2))
        case _:
            raise ValueError("标题格式错误")


def get_text_node(node: SyntaxTreeNode) -> str:
    """获取文本节点。"""
    if node.type == "text":
        return node.content.strip()
    if node.children:
        return "".join(get_text_node(child) for child in node.children)
    return ""


def parse_body(body: str) -> dict[str, str]:
    """解析内容。"""
    md = MarkdownIt()
    tokens = md.parse(body)
    ast_nodes = SyntaxTreeNode(tokens).children
    result: dict[str, str] = {}
    current_heading: str | None = None
    for node in ast_nodes:
        if node.type == "heading":
            current_heading = get_text_node(node)
        if current_heading is not None and node.type == "paragraph":
            result[current_heading] = get_text_node(node)
    return result


def parse_issue(context: Context, time: int) -> Data:
    """解析 Issue。"""
    data_class, name = parse_title(context.payload.issue.title)
    issue_form = parse_body(context.payload.issue.body or "")
    return data_class(
        **issue_form,
        name=name,
        time=time,
        is_official=False,
    )
