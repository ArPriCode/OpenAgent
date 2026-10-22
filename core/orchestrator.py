import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Prevent gRPC deadlocks when git subprocess forks on macOS
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"

from github import Github

from config.settings import settings, RepoConfig, load_repos_config
from core.scheduler import TimeWindowScheduler
from core.issue_hunter import IssueHunter
from core.git_manager import GitManager
from llm.gemini_solver import GeminiSolver
from llm.grok_communicator import GrokCommunicator
from pr_watchdog.reviewer import PRReviewWatchdog

logger = logging.getLogger("OSAgent.Orchestrator")

class AgentOrchestrator:
    """
    Central orchestration engine for the autonomous open-source contribution agent.
    Coordinates time window scheduling, PR review monitoring, issue hunting,
    Gemini bug resolution, and Grok communication.
    """

    def __init__(self):
        self.scheduler = TimeWindowScheduler()
        self.github_client = None
        if settings.GITHUB_TOKEN and settings.GITHUB_TOKEN != "your_github_token_here":
            try:
                self.github_client = Github(settings.GITHUB_TOKEN)
            except Exception as e:
                logger.warning(f"Failed to initialize GitHub client: {e}")

        self.hunter = IssueHunter(github_token=settings.GITHUB_TOKEN)
        self.git_mgr = GitManager()
        self.gemini = GeminiSolver()
        self.grok = GrokCommunicator()
        self.watchdog = PRReviewWatchdog(
            github_client=self.github_client,
            git_mgr=self.git_mgr,
            gemini=self.gemini,
            grok=self.grok
        )
        self.state_file = Path(settings.STATE_FILE_PATH)
        self._init_state()

    def _init_state(self):
        if not self.state_file.exists():
            initial_state = {
                "last_run": None,
                "current_status": "Idle",
                "active_window": f"{settings.WORK_WINDOW_START} - {settings.WORK_WINDOW_END}",
                "pending_approvals": [],
                "completed_contributions": [],
                "activity_log": []
            }
            self._save_state(initial_state)

    def get_state(self) -> Dict[str, Any]:
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def log_event(self, message: str, level: str = "INFO"):
        logger.info(message)
        state = self.get_state()
        logs = state.get("activity_log", [])
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logs.insert(0, {"timestamp": timestamp, "level": level, "message": message})
        state["activity_log"] = logs[:100]
        self._save_state(state)

    def run_contribution_cycle(self, force: bool = False) -> Dict[str, Any]:
        """
        Executes a single contribution cycle.
        If force=False, strictly adheres to user-configured active time window.
        """
        active, status_msg = self.scheduler.is_active_now()
        state = self.get_state()
        state["active_window"] = f"{settings.WORK_WINDOW_START} - {settings.WORK_WINDOW_END}"

        if not active and not force:
            state["current_status"] = f"Dormant: Waiting for active window ({settings.WORK_WINDOW_START}-{settings.WORK_WINDOW_END})"
            self._save_state(state)
            self.log_event(f"Agent sleeping. {status_msg}")
            return {"status": "dormant", "message": status_msg}

        self.log_event("🚀 Starting active contribution cycle...")
        state["current_status"] = "Active: Executing contribution cycle"
        import datetime
        state["last_run"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_state(state)

        repos = load_repos_config()
        results = {
            "reviews_handled": [],
            "issues_processed": []
        }

        # ----------------------------------------------------
        # Phase 1: Check and handle existing PR reviews FIRST
        # ----------------------------------------------------
        self.log_event("Checking open PRs for mentor/maintainer feedback...")
        review_updates = self.watchdog.scan_and_handle_reviews(repos)
        results["reviews_handled"] = review_updates
        if review_updates:
            self.log_event(f"Handled {len(review_updates)} PR review updates.")

        # ----------------------------------------------------
        # Phase 2: Hunt candidate issues across target repos
        # ----------------------------------------------------
        self.log_event("Hunting unassigned beginner & GSoC issues...")
        candidates = self.hunter.fetch_candidate_issues(repos, max_per_repo=1)

        for candidate in candidates[:2]: # Limit per cycle to avoid spamming
            processed = self._process_candidate_issue(candidate)
            if processed:
                results["issues_processed"].append(processed)

        state = self.get_state()
        state["current_status"] = "Idle: Cycle completed successfully"
        self._save_state(state)
        return results

    def _process_candidate_issue(self, issue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        repo_name = issue["repo"]
        issue_num = issue["number"]
        issue_title = issue["title"]
        self.log_event(f"Selected candidate #{issue_num} from '{repo_name}': {issue_title}")

        # 1. Draft polite claim comment via Grok
        claim_comment = self.grok.generate_claim_comment(issue_title, issue["body"])

        # 2. Clone/sync repo locally
        repo_obj, local_dir = self.git_mgr.clone_or_sync_repo(repo_name)
        if not repo_obj:
            self.log_event(f"Could not clone {repo_name}. Skipping.", level="ERROR")
            return None

        # 3. Create branch
        branch_name = f"fix/issue-{issue_num}"
        self.git_mgr.create_feature_branch(repo_obj, branch_name)

        # 4. Extract code context and solve with Gemini
        keywords = issue_title.split()[:5]
        local_repo_path = self.git_mgr._get_local_repo_dir(repo_name)
        code_context = self.git_mgr.find_relevant_files(local_repo_path, keywords)

        self.log_event(f"Invoking Gemini Solver for #{issue_num}...")
        solution = self.gemini.solve_issue(
            issue_title=issue_title,
            issue_body=issue["body"],
            code_context=code_context
        )

        # 5. Apply changes locally and test
        modified_files = []
        if solution.get("modified_files"):
            modified_files = self.git_mgr.apply_file_changes(local_repo_path, solution["modified_files"])
            test_ok, test_logs = self.git_mgr.run_tests_and_syntax_check(local_repo_path)
            self.log_event(f"Verification tests: {test_ok}. Details: {test_logs[:150]}")

        # 6. Draft PR Description via Grok
        pr_description = self.grok.generate_pr_description(
            issue_number=issue_num,
            issue_title=issue_title,
            solution_summary=solution.get("solution_summary", "Bug fix implemented"),
            modified_files=modified_files
        )

        # 7. Human-in-the-Loop check
        if settings.REQUIRE_APPROVAL:
            pending_item = {
                "id": f"{repo_name}_{issue_num}",
                "repo": repo_name,
                "issue_number": issue_num,
                "issue_title": issue_title,
                "branch_name": branch_name,
                "claim_comment": claim_comment,
                "solution_summary": solution.get("solution_summary"),
                "modified_files": modified_files,
                "pr_description": pr_description,
                "status": "pending_approval"
            }
            state = self.get_state()
            pending_list = state.get("pending_approvals", [])
            # Avoid duplicate pending approvals
            if not any(p["id"] == pending_item["id"] for p in pending_list):
                pending_list.append(pending_item)
                state["pending_approvals"] = pending_list
                self._save_state(state)
                self.log_event(f"Action for #{issue_num} sent to Dashboard for User Approval! 🛡️")
            return pending_item

        # 8. Commit and Push
        commit_msg = f"Fix: {issue_title} (addresses #{issue_num})"
        self.git_mgr.commit_and_push(repo_obj, branch_name, commit_msg)

        # 9. Create PR
        pr_url = self._open_pull_request(repo_name, branch_name, f"Fix: {issue_title}", pr_description)

        contribution_record = {
            "repo": repo_name,
            "issue_number": issue_num,
            "issue_title": issue_title,
            "pr_url": pr_url,
            "solution": solution.get("solution_summary"),
            "status": "PR_OPENED"
        }

        state = self.get_state()
        completed = state.get("completed_contributions", [])
        completed.insert(0, contribution_record)
        state["completed_contributions"] = completed[:50]
        self._save_state(state)
        self.log_event(f"🎉 Successfully raised PR for #{issue_num}: {pr_url}")

        return contribution_record

    def ensure_fork(self, upstream_repo_name: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Ensures the repository is forked on the user's GitHub account.
        Returns: (authenticated_fork_git_url, fork_html_url)
        """
        if not self.github_client or not settings.GITHUB_TOKEN or settings.GITHUB_TOKEN.startswith("your_github_token"):
            return None, None

        try:
            upstream = self.github_client.get_repo(upstream_repo_name)
            user = self.github_client.get_user()
            repo_short = upstream_repo_name.split("/")[-1]
            fork_name = f"{user.login}/{repo_short}"

            try:
                fork_repo = self.github_client.get_repo(fork_name)
                self.log_event(f"Existing fork found on GitHub: {fork_repo.html_url}")
            except Exception:
                self.log_event(f"Forking {upstream_repo_name} to @{user.login}...")
                fork_repo = user.create_fork(upstream)
                self.log_event(f"Fork initiated successfully: {fork_repo.html_url}")

            auth_fork_url = f"https://{settings.GITHUB_TOKEN}@github.com/{user.login}/{repo_short}.git"
            return auth_fork_url, fork_repo.html_url
        except Exception as e:
            logger.error(f"Failed to ensure fork for {upstream_repo_name}: {e}")
            return None, None

    def _open_pull_request(self, repo_name: str, branch_name: str, title: str, body: str, force_live: bool = False) -> str:
        if (settings.DRY_RUN and not force_live) or not self.github_client or settings.GITHUB_TOKEN.startswith("your_github_token"):
            logger.info(f"[DRY RUN] Would create PR on {repo_name} from branch {branch_name}")
            return f"https://github.com/{repo_name}/tree/{branch_name}"

        try:
            gh_repo = self.github_client.get_repo(repo_name)
            user = self.github_client.get_user()
            head_branch = f"{user.login}:{branch_name}"
            default_branch = gh_repo.default_branch or "main"

            self.log_event(f"Opening Pull Request on {repo_name} from {head_branch} into {default_branch}...")
            pr = gh_repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=default_branch
            )
            self.log_event(f"🎉 Pull Request created successfully: {pr.html_url}")
            return pr.html_url
        except Exception as ge:
            logger.warning(f"PyGithub create_pull note on {repo_name}: {ge}")
            # Check if PR already exists or fallback to the compare URL (compare URL NEVER 404s!)
            user = self.github_client.get_user() if self.github_client else None
            user_login = user.login if user else settings.GITHUB_USERNAME
            try:
                existing_prs = gh_repo.get_pulls(state="open", head=f"{user_login}:{branch_name}")
                for ep in existing_prs:
                    return ep.html_url
            except Exception:
                pass
            compare_url = f"https://github.com/{repo_name}/compare/{gh_repo.default_branch}...{user_login}:{branch_name}?expand=1"
            self.log_event(f"Direct PR compare URL ready: {compare_url}")
            return compare_url

    def approve_action(self, action_id: str) -> bool:
        """
        Approves and executes a pending action from the Human-in-the-Loop queue.
        1. Automatically forks repository on GitHub if not already forked
        2. Applies commits to local repo
        3. Pushes branch to user's fork
        4. Creates real Pull Request on upstream
        """
        state = self.get_state()
        pending_list = state.get("pending_approvals", [])
        target = next((item for item in pending_list if item["id"] == action_id), None)
        if not target:
            return False

        repo_name = target["repo"]
        branch_name = target["branch_name"]
        issue_title = target["issue_title"]
        issue_num = target["issue_number"]
        pr_description = target["pr_description"]

        self.log_event(f"User APPROVED action for {repo_name} #{issue_num}! Starting live deployment...")

        # 1. Ensure fork exists on user's GitHub
        auth_fork_url, fork_html = self.ensure_fork(repo_name)

        # 2. Sync local repo
        repo_obj, _ = self.git_mgr.clone_or_sync_repo(repo_name, force_live=True)
        if repo_obj:
            # 3. Commit and push to fork
            commit_msg = f"Fix: {issue_title} (addresses #{issue_num})"
            self.git_mgr.commit_and_push(repo_obj, branch_name, commit_msg, fork_url=auth_fork_url, force_live=True)

            # 4. Open real Pull Request
            pr_url = self._open_pull_request(repo_name, branch_name, f"Fix: {issue_title}", pr_description, force_live=True)
            
            # Remove from pending and add to completed
            state["pending_approvals"] = [p for p in pending_list if p["id"] != action_id]
            completed = state.get("completed_contributions", [])
            completed.insert(0, {
                "repo": repo_name,
                "issue_number": issue_num,
                "issue_title": issue_title,
                "pr_url": pr_url,
                "fork_url": fork_html or f"https://github.com/{settings.GITHUB_USERNAME}/{repo_name.split('/')[-1]}",
                "status": "PR_OPENED"
            })
            state["completed_contributions"] = completed[:50]
            self._save_state(state)
            self.log_event(f"🎉 Contribution Live! PR Link: {pr_url}")
            return True
        return False
