"""GitHub 上下文。

From: https://github.com/actions/toolkit/blob/main/packages/github/src/context.ts
"""

# ruff: noqa: E501, D101, D102, D107

import os
from pathlib import Path

from githubkit.versions.latest.webhooks import IssueCommentEvent, IssuesEvent
from pydantic import BaseModel, TypeAdapter


class RepoInfo(BaseModel):
    owner: str
    repo: str


class Context:
    def __init__(self) -> None:
        if path := os.environ.get("GITHUB_EVENT_PATH"):
            if Path(path).exists():
                with Path(path).open(encoding="utf-8") as f:
                    self.payload: IssuesEvent | IssueCommentEvent = TypeAdapter(
                        IssuesEvent | IssueCommentEvent
                    ).validate_json(
                        f.read(),
                    )  # type: ignore  # noqa: PGH003
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
        if github_repository := os.environ.get("GITHUB_REPOSITORY"):
            owner, repo = github_repository.split("/", 1)
            return RepoInfo(owner=owner, repo=repo)
        if self.payload.repository:
            return RepoInfo(
                owner=self.payload.repository.owner.login,
                repo=self.payload.repository.name,
            )
        raise RuntimeError(
            "context.repo requires a GITHUB_REPOSITORY environment variable like 'owner/repo'"
        )
