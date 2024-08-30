"""验证 Issue 提交。"""

# /// script
# dependencies = ["markdown-it-py>=3.0.0", "githubkit>=0.11.2", "httpx>=0.27.0"]
# ///

import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import NoReturn, TypeAlias, cast

import httpx
from githubkit import ActionAuthStrategy, GitHub, Response
from githubkit.exception import RequestFailed
from githubkit.versions.latest.models import (
    IssueComment,
    Label,
    PullRequest,
    PullRequestSimple,
    Reaction,
)
from githubkit.versions.latest.webhooks import IssueCommentEvent, IssuesEvent
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from pydantic import BaseModel, TypeAdapter

TIME = int(time.time())

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

logger = logging.getLogger()


def run_subprocess(command: str, env: dict[str, str] | None = None) -> str:
    """在子进程中运行命令。"""
    logger.info("Run command: %s", command)
    return subprocess.run(  # noqa: S602
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=True,
        timeout=60,
        check=True,
        text=True,
        env=env,
    ).stdout


class RepoInfo(BaseModel):
    """GitHub 仓库信息。"""

    owner: str
    repo: str


class Context:
    """GitHub 上下文。

    From: https://github.com/actions/toolkit/blob/main/packages/github/src/context.ts
    """

    def __init__(self) -> None:
        """初始化。"""
        if path := os.environ.get("GITHUB_EVENT_PATH"):
            if Path(path).exists():
                with Path(path).open(encoding="utf-8") as f:
                    self.payload: IssuesEvent | IssueCommentEvent = TypeAdapter(
                        IssuesEvent | IssueCommentEvent
                    ).validate_json(f.read())
            else:
                raise RuntimeError(f"GITHUB_EVENT_PATH {path} does not exist")
        self.event_name = os.environ["GITHUB_EVENT_NAME"]
        self.sha = os.environ["GITHUB_SHA"]
        self.ref = os.environ["GITHUB_REF"]
        self.workflow = os.environ["GITHUB_WORKFLOW"]
        self.action = os.environ["GITHUB_ACTION"]
        self.actor = os.environ["GITHUB_ACTOR"]
        self.job = os.environ["GITHUB_JOB"]
        self.run_attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
        self.run_number = int(os.environ["GITHUB_RUN_NUMBER"])
        self.run_id = int(os.environ["GITHUB_RUN_ID"])
        self.api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        self.graphql_url = os.environ.get(
            "GITHUB_GRAPHQL_URL",
            "https://api.github.com/graphql",
        )

    @property
    def repo(self) -> RepoInfo:
        """GitHub 仓库信息。"""
        if github_repository := os.environ.get("GITHUB_REPOSITORY"):
            owner, repo = github_repository.split("/", 1)
            return RepoInfo(owner=owner, repo=repo)
        if self.payload.repository:
            return RepoInfo(
                owner=self.payload.repository.owner.login,
                repo=self.payload.repository.name,
            )
        raise RuntimeError(
            "context.repo requires a GITHUB_REPOSITORY environment variable "
            "like 'owner/repo'"
        )


class BaseData(ABC, BaseModel):
    """数据基类。"""

    name: str
    time: int
    is_official: bool

    @abstractmethod
    def validate_data(self) -> str:
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

    def validate_data(self) -> str:
        """验证数据。"""
        httpx.get(
            f"https://pypi.org/pypi/{self.pypi_name}/json",
            timeout=5,
        ).raise_for_status()

        return run_subprocess(
            f"uv run --with 'alicebot' --with '{self.pypi_name}' "
            f"test.py {self.__value__} {self.module_name}"
        )


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

    def validate_data(self) -> str:
        """验证数据。"""
        return ""

    def to_file_path(self) -> Path:
        """获取文件路径。"""
        return Path("bots.json")


Data: TypeAlias = PluginData | AdapterData | BotData


def parse_title(title: str) -> tuple[type[Data], str]:
    """解析标题。"""
    result = re.match(r"(.+):\s*(.+)", title)
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


class RunResult(Enum):
    """运行结果。"""

    PARSE_FAILED = "parse_failed"
    VALIDATION_FAILED = "validation_failed"
    UNEXPECTED_ERROR = "unexpected_error"
    VALIDATION_SUCCESS = "validation_success"

    def render_comment_template(self, **kwargs: object) -> str:
        """渲染模版。"""
        with Path(f"templates/{self.value}.md").open(encoding="utf-8") as f:
            return f.read().format(**kwargs)

    def to_label_name(self) -> str:
        """获取 Label 名称。"""
        return self.value.replace("_", "/")

    def is_failed(self) -> bool:
        """是否表示失败状态。"""
        return self != RunResult.VALIDATION_SUCCESS


class GitHubIssue:
    """GitHub Issue"""

    def __init__(self, owner: str, repo: str, number: int, title: str) -> None:
        """初始化。"""
        self.owner = owner
        self.repo = repo
        self.number = number
        self.title = title
        self.github = GitHub(ActionAuthStrategy())

    @property
    def branch_name(self) -> str:
        """创建分支的名称。"""
        return f"update-from-issue-{self.number}"

    @property
    def pull_request_body(self) -> str:
        """创建 Pull Request 的内容。"""
        return f"close #{self.number}"

    def add_labels(self, labels: list[str]) -> Response[list[Label]]:
        """添加 Labels。"""
        return self.github.rest.issues.add_labels(
            owner=self.owner,
            repo=self.repo,
            issue_number=self.number,
            data=labels,
        )

    def remove_label(self, name: str) -> Response[list[Label]]:
        """删除 Labels。"""
        return self.github.rest.issues.remove_label(
            owner=self.owner,
            repo=self.repo,
            issue_number=self.number,
            name=name,
        )

    def create_comment(self, body: str) -> Response[IssueComment]:
        """创建 Comment。"""
        return self.github.rest.issues.create_comment(
            owner=self.owner,
            repo=self.repo,
            issue_number=self.number,
            body=body,
        )

    def create_reaction_for_comment(self, comment_id: int) -> Response[Reaction]:
        """创建 Comment 的 Reaction。"""
        return self.github.rest.reactions.create_for_issue_comment(
            owner=self.owner,
            repo=self.repo,
            comment_id=comment_id,
            content="rocket",
        )

    def create_pull_request(self, base: str) -> Response[PullRequest]:
        """创建 Pull Request。"""
        return self.github.rest.pulls.create(
            owner=self.owner,
            repo=self.repo,
            head=self.branch_name,
            base=base,
            title=self.title,
            body=self.pull_request_body,
        )

    def list_pull_request(self) -> Response[list[PullRequestSimple]]:
        """搜索 Pull Request。"""
        return self.github.rest.pulls.list(
            owner=self.owner,
            repo=self.repo,
            state="open",
            head=self.branch_name,
        )

    def execute_result(self, result: RunResult, **kwargs: object) -> NoReturn:
        """执行脚本运行结果。"""
        logger.info("Run result: %s", result, extra=kwargs, exc_info=True)

        for res in RunResult:
            if res != result:
                with contextlib.suppress(RequestFailed):
                    self.remove_label(res.to_label_name())
        self.add_labels([result.to_label_name()])

        comment = result.render_comment_template(**kwargs)
        logger.info("Create comment: %s", comment)
        self.create_comment(comment)

        sys.exit(result.is_failed())


def main() -> NoReturn:
    """主函数。"""
    logger.info("Start handle issue")

    context = Context()
    issue = GitHubIssue(
        owner=context.repo.owner,
        repo=context.repo.repo,
        number=context.payload.issue.number,
        title=context.payload.issue.title,
    )

    # 验证事件类型
    if context.event_name == "issues":
        issue.create_comment("感谢你的提交。\n\n自动验证正在进行中。")
    elif context.event_name == "issue_comment":
        issue.create_reaction_for_comment(
            cast(IssueCommentEvent, context.payload).comment.id
        )

    # 解析 issue 内容
    try:
        logger.info("Start parse issue")
        data = parse_issue(context, TIME)
    except Exception as e:
        issue.execute_result(RunResult.PARSE_FAILED, exception=e)

    # 验证插件和适配器是否可以在 pypi 中找到，和是否可以正常加载
    try:
        logging.info("Start validation")
        validate_info = data.validate_data()
    except Exception as e:
        issue.execute_result(RunResult.VALIDATION_FAILED, exception=e)

    # 更新数据
    try:
        # 更新数据
        logging.info("Start update data")
        data.update_data()
    except Exception as e:
        issue.execute_result(RunResult.UNEXPECTED_ERROR, exception=e)

    # 创建 PR
    try:
        logging.info("Create pull request")
        if issue.list_pull_request().parsed_data:
            # 如果存在关联到本 issue 的未关闭 PR 则直接退出
            logger.warning("Unclosed pull request already exists")
            issue.create_comment(
                "存在未关闭的 Pull Request。\n\n请等待之前的 Pull Request 完成。"
            )
            sys.exit()
        run_subprocess(f'git config --global user.name "{context.actor}"')
        run_subprocess(
            f'git config --global user.email "{context.actor}@users.noreply.github.com"'
        )
        run_subprocess(f"git checkout -b {issue.branch_name}")
        run_subprocess("git add plugins.json adapters.json bots.json")
        run_subprocess('git commit -m "feat: update data"')
        run_subprocess(f"git push -f origin {issue.branch_name}")
        r = issue.create_pull_request(context.payload.repository.default_branch)
    except Exception as e:
        issue.execute_result(RunResult.UNEXPECTED_ERROR, exception=e)

    issue.execute_result(
        RunResult.VALIDATION_SUCCESS,
        pull_request_url=r.parsed_data.html_url,
        validate_info=validate_info,
    )


if __name__ == "__main__":
    main()
