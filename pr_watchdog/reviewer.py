import logging
from typing import List, Dict, Any, Optional
from github import Github, GithubException
from config.settings import settings, RepoConfig
from llm.gemini_solver import GeminiSolver
from llm.grok_communicator import GrokCommunicator
from core.git_manager import GitManager

logger = logging.getLogger("OSAgent.PRWatchdog")

class PRReviewWatchdog:
    """
    Monitors all open Pull Requests created by the user across target repositories.
    Detects reviews, comments, and change requests from maintainers/mentors.
    Automatically triggers Gemini to re-patch the code and Grok to reply politely!
    """

    def __init__(
        self,
        github_client: Optional[Github] = None,
        git_mgr: Optional[GitManager] = None,
        gemini: Optional[GeminiSolver] = None,
        grok: Optional[GrokCommunicator] = None
    ):
        self.gh = github_client
        self.git_mgr = git_mgr or GitManager()
        self.gemini = gemini or GeminiSolver()
        self.grok = grok or GrokCommunicator()
        self.username = settings.GITHUB_USERNAME

    def scan_and_handle_reviews(self, repo_configs: List[RepoConfig]) -> List[Dict[str, Any]]:
        """
        Scans for user's open PRs in tracked repos and handles feedback.
        """
        results = []

        if not self.gh or settings.GITHUB_TOKEN.startswith("your_github_token") or settings.DRY_RUN:
            logger.info("PR Watchdog: Running in simulated check mode (DRY_RUN or placeholder token).")
            return [{
                "repo": "pallets/flask",
                "pr_number": 101,
                "status": "Simulated check: No active review changes pending."
            }]

        for repo_cfg in repo_configs:
            if not repo_cfg.enabled:
                continue

            repo_name = repo_cfg.repo
            try:
                gh_repo = self.gh.get_repo(repo_name)
                # Get open PRs authored by our user
                pulls = gh_repo.get_pulls(state="open")
                for pr in pulls:
                    if pr.user.login != self.username:
                        continue

                    logger.info(f"Checking reviews on PR #{pr.number} in '{repo_name}'...")
                    handled = self._process_single_pr(gh_repo, pr)
                    if handled:
                        results.append(handled)
            except Exception as e:
                logger.error(f"Error checking PRs for {repo_name}: {e}")

        return results

    def _process_single_pr(self, gh_repo, pr) -> Optional[Dict[str, Any]]:
        # Fetch PR comments and reviews
        comments = list(pr.get_issue_comments())
        reviews = list(pr.get_reviews())

        last_comment_by_maintainer = None
        for c in reversed(comments):
            if c.user.login != self.username:
                last_comment_by_maintainer = c
                break

        # Check if latest review is CHANGES_REQUESTED
        latest_review = reviews[-1] if reviews else None
        needs_action = False
        feedback_text = ""

        if latest_review and latest_review.state == "CHANGES_REQUESTED" and latest_review.user.login != self.username:
            needs_action = True
            feedback_text = f"Review State: CHANGES_REQUESTED.\nNotes: {latest_review.body}"
        elif last_comment_by_maintainer:
            # Check if we haven't replied to the last comment
            if comments[-1].user.login != self.username:
                needs_action = True
                feedback_text = f"Maintainer Comment from @{last_comment_by_maintainer.user.login}: {last_comment_by_maintainer.body}"

        if not needs_action:
            return None

        logger.info(f"Active feedback detected on PR #{pr.number}: {feedback_text[:100]}...")

        # 1. Sync local repo and branch
        branch_name = pr.head.ref
        repo_obj, local_dir = self.git_mgr.clone_or_sync_repo(gh_repo.full_name)
        if not repo_obj:
            return {"pr_number": pr.number, "status": "Failed to clone repo locally"}

        # 2. Extract code context and ask Gemini to adjust
        keywords = feedback_text.split()[:5]
        code_context = self.git_mgr.find_relevant_files(self.git_mgr._get_local_repo_dir(gh_repo.full_name), keywords)
        
        solution = self.gemini.solve_issue(
            issue_title=f"Address PR #{pr.number} feedback",
            issue_body=feedback_text,
            code_context=code_context
        )

        # 3. Apply changes locally & commit
        if solution.get("modified_files"):
            self.git_mgr.apply_file_changes(self.git_mgr._get_local_repo_dir(gh_repo.full_name), solution["modified_files"])
            test_ok, test_log = self.git_mgr.run_tests_and_syntax_check(self.git_mgr._get_local_repo_dir(gh_repo.full_name))

            commit_msg = f"Address review feedback on PR #{pr.number}"
            self.git_mgr.commit_and_push(repo_obj, branch_name, commit_msg)

        # 4. Use Grok to craft a courteous reply
        reply_comment = self.grok.generate_review_reply(
            mentor_comment=feedback_text,
            fix_explanation=solution.get("solution_summary", "Updated code per feedback.")
        )

        if not settings.DRY_RUN:
            pr.create_issue_comment(reply_comment)
            logger.info(f"Posted review reply on PR #{pr.number}")
        else:
            logger.info(f"[DRY RUN] Would post reply to PR #{pr.number}:\n{reply_comment}")

        return {
            "pr_number": pr.number,
            "repo": gh_repo.full_name,
            "feedback": feedback_text,
            "solution": solution.get("solution_summary"),
            "reply": reply_comment
        }
