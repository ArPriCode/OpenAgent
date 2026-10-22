import logging
from typing import Optional, List
from openai import OpenAI
from config.settings import settings

logger = logging.getLogger("OSAgent.GrokCommunicator")

class GrokCommunicator:
    """
    Handles all human-like communication with open-source maintainers,
    community members, and mentors via Grok (xAI API).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.api_key = api_key or settings.GROK_API_KEY
        self.model_name = model_name or settings.GROK_MODEL
        self.base_url = base_url or settings.GROK_BASE_URL
        self.client_available = False

        if self.api_key and self.api_key != "your_grok_xai_api_key_here":
            # Auto-detect Groq vs xAI Grok
            if self.api_key.startswith("gsk_"):
                self.base_url = "https://api.groq.com/openai/v1"
                self.model_name = settings.GROK_MODEL if "gpt-oss" in settings.GROK_MODEL or "llama" in settings.GROK_MODEL else "openai/gpt-oss-120b"
                logger.info(f"Detected Groq Cloud key (gsk_). Configured Groq LPU endpoint with {self.model_name}.")
            try:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
                self.client_available = True
                logger.info(f"Communicator initialized with model: {self.model_name} on {self.base_url}")
            except Exception as e:
                logger.warning(f"Could not configure Communicator API: {e}")

    def generate_claim_comment(self, issue_title: str, issue_body: str) -> str:
        """
        Generates a polite, respectful message requesting to work on the issue.
        """
        if not self.client_available:
            return (
                f"Hi maintainers! 👋 I would love to work on this issue (`{issue_title}`). "
                f"I've reviewed the issue description and am preparing a fix locally. "
                f"Could you please assign this to me? Thanks!"
            )

        prompt = f"""You are a polite, helpful open-source contributor.
Draft a concise, warm, and professional GitHub comment asking the repository maintainers if you can work on this issue.
Rules:
- Keep it under 3 sentences.
- Never sound robotic or generic.
- Express genuine interest and state you've reviewed the problem.

Issue Title: {issue_title}
Issue Context: {issue_body[:300]}
"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Grok claim comment generation failed: {e}")
            return f"Hi! I'd like to contribute a fix for this issue ({issue_title}). Looking into it right now!"

    def generate_pr_description(
        self,
        issue_number: int,
        issue_title: str,
        solution_summary: str,
        modified_files: List[str]
    ) -> str:
        """
        Drafts a high-quality GitHub PR description following open-source best practices.
        """
        files_list = "\n".join([f"- `{f}`" for f in modified_files])
        if not self.client_available:
            return f"""## Description
Fixes #{issue_number}

### Summary of Changes
{solution_summary}

### Modified Files
{files_list}

### Testing
- Tested locally with syntax validation and unit tests.
- Code conforms to project conventions.
"""

        prompt = f"""You are a seasoned open-source developer creating a Pull Request.
Draft a clean, comprehensive GitHub PR description in GitHub Flavored Markdown.
Include:
1. Fixes #{issue_number} - {issue_title}
2. Problem Overview
3. Solution & Key Changes
4. Modified Files:
{files_list}
5. Verification & Tests passed

Solution details:
{solution_summary}
"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=400
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Grok PR description generation failed: {e}")
            return f"Fixes #{issue_number}\n\n### Changes\n{solution_summary}\n\nFiles modified:\n{files_list}"

    def generate_review_reply(self, mentor_comment: str, fix_explanation: str) -> str:
        """
        Generates a respectful, constructive reply to a maintainer or mentor's code review comment.
        """
        if not self.client_available:
            return (
                f"Thank you for the review and constructive feedback! 🙏\n\n"
                f"I have addressed your comment: {fix_explanation}. "
                f"The new commits have been pushed. Please take another look when you have a moment!"
            )

        prompt = f"""You are an open-source contributor replying to a repository maintainer or GSoC mentor's review comment on your Pull Request.
Be respectful, receptive, and appreciative of their time.
Briefly explain how you addressed their feedback and let them know the branch has been updated.

Mentor's Review Comment:
"{mentor_comment}"

How you resolved it:
"{fix_explanation}"
"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Grok review reply generation failed: {e}")
            return f"Thanks for the feedback! I've updated the code accordingly: {fix_explanation}. Let me know if anything else needs tuning."
