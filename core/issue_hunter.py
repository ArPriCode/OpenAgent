import logging
from typing import List, Dict, Any, Optional
from github import Github, GithubException
from config.settings import settings, RepoConfig

logger = logging.getLogger("OSAgent.IssueHunter")

class IssueHunter:
    """
    Crawls tracked open-source repositories to discover open, unassigned,
    beginner/GSoC-friendly issues.
    """

    def __init__(self, github_token: Optional[str] = None):
        self.token = github_token or settings.GITHUB_TOKEN
        self.gh = None
        if self.token and self.token != "your_github_token_here":
            try:
                self.gh = Github(self.token)
            except Exception as e:
                logger.warning(f"Could not initialize PyGithub: {e}")

    def fetch_candidate_issues(self, repo_configs: List[RepoConfig], max_per_repo: int = 3) -> List[Dict[str, Any]]:
        candidates = []

        for repo_cfg in repo_configs:
            if not repo_cfg.enabled:
                continue

            repo_name = repo_cfg.repo
            labels = repo_cfg.labels or ["good first issue", "help wanted"]

            logger.info(f"Scanning '{repo_name}' for labels: {labels}...")

            if not self.gh or settings.DRY_RUN:
                mock_issue = {
                    "repo": repo_name,
                    "number": 42,
                    "title": f"Fix typo in CLI argument parsing for {repo_name.split('/')[-1]}",
                    "body": "When running `--timeout` with non-integer values, the error message has a typo and should raise ValueError.",
                    "labels": ["good first issue", "bug"],
                    "assignee": None,
                    "html_url": f"https://github.com/{repo_name}/issues/42",
                    "comments_count": 0,
                    "is_mock": True
                }
                candidates.append(mock_issue)
                continue

            try:
                gh_repo = self.gh.get_repo(repo_name)
                # Fetch open issues
                for label in labels:
                    try:
                        issues = gh_repo.get_issues(state="open", labels=[label])
                        count = 0
                        for issue in issues:
                            if count >= max_per_repo:
                                break
                            
                            # Filter out pull requests
                            if issue.pull_request:
                                continue

                            # Check if already assigned
                            if issue.assignee or (issue.assignees and len(issue.assignees) > 0):
                                continue

                            candidate = {
                                "repo": repo_name,
                                "number": issue.number,
                                "title": issue.title,
                                "body": issue.body or "",
                                "labels": [lbl.name for lbl in issue.labels],
                                "assignee": None,
                                "html_url": issue.html_url,
                                "comments_count": issue.comments,
                                "is_mock": False
                            }
                            if not any(c["repo"] == repo_name and c["number"] == issue.number for c in candidates):
                                candidates.append(candidate)
                                count += 1
                    except Exception as ge:
                        logger.warning(f"Label '{label}' failed on '{repo_name}': {ge}")
            except Exception as e:
                logger.warning(f"Could not fetch remote issues for '{repo_name}' ({e}). Falling back to simulation candidate.")
                mock_issue = {
                    "repo": repo_name,
                    "number": 42,
                    "title": f"Fix argument validation in {repo_name.split('/')[-1]}",
                    "body": "Ensure non-empty input validation to prevent unhandled runtime error.",
                    "labels": ["good first issue", "bug"],
                    "assignee": None,
                    "html_url": f"https://github.com/{repo_name}/issues/42",
                    "comments_count": 0,
                    "is_mock": True
                }
                candidates.append(mock_issue)

        logger.info(f"Discovered {len(candidates)} actionable candidate issues across repos.")
        return candidates
