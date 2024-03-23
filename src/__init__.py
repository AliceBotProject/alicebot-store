"""验证 Issue 提交。"""

import contextlib
import logging
import sys
import time
from enum import Enum
from pathlib import Path
from typing import NoReturn, cast

from githubkit import ActionAuthStrategy, GitHub, Response
from githubkit.exception import RequestFailed
from githubkit.versions.latest.models import (
    IssueComment,
    Label,
    PullRequest,
    Reaction,
    SearchIssuesGetResponse200,
)
from githubkit.versions.latest.webhooks import IssueCommentEvent

from .context import Context
from .parse import parse_issue
from .utils import run_subprocess

TIME = int(time.time())

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

logger = logging.getLogger()


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
            content="+1",
        )

    def _pull_request_body(self) -> str:
        return f"close #{self.number}"

    def create_pull_request(self, head: str, base: str) -> Response[PullRequest]:
        """创建 Pull Request。"""
        return self.github.rest.pulls.create(
            owner=self.owner,
            repo=self.repo,
            head=head,
            base=base,
            title=self.title,
            body=self._pull_request_body(),
        )

    def search_pull_request(self) -> Response[SearchIssuesGetResponse200]:
        """搜索 Pull Request。"""
        return self.github.rest.search.issues_and_pull_requests(
            q=f"{self._pull_request_body()} in:body "
            f"repo:{self.owner}/{self.repo} is:pull-request is:open"
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
        data.validate_data()
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
        if issue.search_pull_request().parsed_data.total_count > 0:
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
        branch_name = f"{issue.number}-{TIME}"
        run_subprocess(f"git checkout -b {branch_name}")
        run_subprocess("git add plugins.json adapters.json bots.json")
        run_subprocess('git commit -m "feat: update data"')
        run_subprocess(f"git push origin {branch_name}")
        r = issue.create_pull_request(
            head=branch_name,
            base=context.payload.repository.default_branch,
        )
    except Exception as e:
        issue.execute_result(RunResult.UNEXPECTED_ERROR, exception=e)

    issue.execute_result(
        RunResult.VALIDATION_SUCCESS,
        pull_request_url=r.parsed_data.html_url,
    )
