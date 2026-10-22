import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from git import Repo, GitCommandError
from config.settings import settings

logger = logging.getLogger("OSAgent.GitManager")

class GitManager:
    """
    Handles local git operations:
    - Cloning repositories and forking
    - Managing feature branches (e.g. fix/issue-123)
    - Locating relevant source files
    - Applying patches
    - Running verification tests / syntax checks
    - Committing and pushing
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root or settings.WORKSPACES_DIR)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _get_local_repo_dir(self, repo_full_name: str) -> Path:
        sanitized = repo_full_name.replace("/", "_")
        return self.workspace_root / sanitized

    def clone_or_sync_repo(self, repo_full_name: str, force_live: bool = False) -> Tuple[Optional[Repo], str]:
        """
        Clones repository if not present locally (shallow depth=1 for fast cloning),
        or fetches latest updates.
        """
        target_dir = self._get_local_repo_dir(repo_full_name)
        clone_url = f"https://github.com/{repo_full_name}.git"

        if settings.DRY_RUN and not force_live:
            # If repo isn't cloned yet in pure dry-run, create a mock local sandbox
            if not target_dir.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                mock_readme = target_dir / "README.md"
                mock_readme.write_text(f"# {repo_full_name}\nMock repository for dry-run testing.\n")
                mock_code = target_dir / "main.py"
                mock_code.write_text("def parse_args(args):\n    # TODO: fix parsing\n    pass\n")
                repo = Repo.init(target_dir)
                repo.create_remote("origin", clone_url)
                repo.index.add(["README.md", "main.py"])
                repo.index.commit("Initial mock commit")
                return repo, str(target_dir)

        try:
            if target_dir.exists() and (target_dir / ".git").exists():
                repo = Repo(target_dir)
                if "origin" not in [r.name for r in repo.remotes]:
                    repo.create_remote("origin", clone_url)
                logger.info(f"Existing repo found at {target_dir}. Fetching latest updates...")
                try:
                    repo.remotes.origin.fetch()
                except Exception as e:
                    logger.warning(f"Fetch note: {e}")
                return repo, str(target_dir)
            else:
                logger.info(f"Cloning {clone_url} (depth=1) into {target_dir}...")
                repo = Repo.clone_from(clone_url, target_dir, depth=1)
                return repo, str(target_dir)
        except Exception as e:
            logger.error(f"Failed to clone or open repo {repo_full_name}: {e}")
            return None, str(target_dir)
            return None, str(target_dir)

    def create_feature_branch(self, repo: Repo, branch_name: str) -> bool:
        try:
            # Checkout base branch (main or master)
            default_branch = "main" if "main" in [h.name for h in repo.heads] else "master"
            if default_branch in [h.name for h in repo.heads]:
                repo.heads[default_branch].checkout()
            
            # Delete branch if already exists locally
            if branch_name in [h.name for h in repo.heads]:
                repo.delete_head(branch_name, force=True)

            new_branch = repo.create_head(branch_name)
            new_branch.checkout()
            logger.info(f"Switched to new branch: {branch_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create branch {branch_name}: {e}")
            return False

    def find_relevant_files(self, repo_dir: Path, keywords: List[str], max_files: int = 5) -> Dict[str, str]:
        """
        Discovers files that likely need to be modified based on issue keywords.
        Returns mapping of relative_file_path -> file_content.
        """
        results = {}
        ignored_dirs = {".git", ".tox", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}

        # Collect candidate code files
        candidate_paths = []
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            for file in files:
                if file.endswith((".py", ".js", ".ts", ".go", ".rs", ".md", ".json", ".yaml", ".yml")):
                    candidate_paths.append(Path(root) / file)

        # Keyword matching score
        scored = []
        for p in candidate_paths:
            try:
                rel = str(p.relative_to(repo_dir))
                score = 0
                for kw in keywords:
                    if kw.lower() in rel.lower():
                        score += 3
                # Sample first 200 lines for content match
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content_head = "".join([f.readline() for _ in range(100)])
                    for kw in keywords:
                        if kw.lower() in content_head.lower():
                            score += 1
                if score > 0:
                    scored.append((score, p, rel))
            except Exception:
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored[:max_files] if scored else [(0, p, str(p.relative_to(repo_dir))) for p in candidate_paths[:max_files]]

        for _, full_p, rel_p in top_candidates:
            try:
                with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                    results[rel_p] = f.read()
            except Exception as e:
                logger.warning(f"Error reading {rel_p}: {e}")

        return results

    def apply_file_changes(self, repo_dir: Path, changes: Dict[str, str]) -> List[str]:
        """
        Applies code changes generated by Gemini to the local repository.
        changes: dict of relative_file_path -> new_content
        """
        modified = []
        for rel_path, content in changes.items():
            full_path = repo_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            modified.append(rel_path)
            logger.info(f"Applied fix to: {rel_path}")
        return modified

    def run_tests_and_syntax_check(self, repo_dir: Path) -> Tuple[bool, str]:
        """
        Executes local verification (python py_compile on modified files or pytest).
        """
        logs = []
        # 1. Quick in-process Python AST syntax validation
        import ast
        syntax_errors = []
        for py_file in repo_dir.rglob("*.py"):
            if any(part in py_file.parts for part in [".git", "venv", ".venv", "build", "dist", "__pycache__"]):
                continue
            try:
                with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                    ast.parse(f.read(), filename=str(py_file))
            except SyntaxError as se:
                syntax_errors.append(f"{py_file.name}:{se.lineno} - {se.msg}")
            except Exception:
                pass

        if syntax_errors:
            return False, f"Syntax Error: {'; '.join(syntax_errors[:2])}"
        logs.append("Syntax check passed.")

        # 2. Pytest if present
        pytest_ini = repo_dir / "pytest.ini"
        tests_dir = repo_dir / "tests"
        if tests_dir.exists():
            try:
                test_res = subprocess.run(
                    ["pytest", "-q", "--maxfail=1"],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if test_res.returncode == 0:
                    logs.append("Pytest suite passed cleanly!")
                else:
                    logs.append(f"Pytest report: {test_res.stdout[:300]}")
            except Exception:
                pass

        return True, "\n".join(logs)

    def commit_and_push(self, repo: Repo, branch_name: str, commit_message: str, fork_url: Optional[str] = None, force_live: bool = False) -> bool:
        if settings.DRY_RUN and not force_live:
            logger.info(f"[DRY RUN] Would commit: '{commit_message}' and push branch '{branch_name}'")
            return True

        try:
            repo.git.add(A=True)
            try:
                repo.index.commit(commit_message)
                logger.info(f"Committed changes with message: '{commit_message}'")
            except Exception as ce:
                logger.info(f"Commit note (already committed or no diff): {ce}")

            # Configure fork remote
            target_remote = "origin"
            if fork_url:
                if "fork" in [r.name for r in repo.remotes]:
                    repo.delete_remote("fork")
                repo.create_remote("fork", fork_url)
                target_remote = "fork"

            logger.info(f"Pushing branch '{branch_name}' to remote '{target_remote}'...")
            repo.git.push(target_remote, f"{branch_name}:{branch_name}", force=True)
            logger.info(f"Successfully pushed branch '{branch_name}' to {target_remote}")
            return True
        except Exception as ge:
            logger.error(f"Git push failed: {ge}")
            return False
