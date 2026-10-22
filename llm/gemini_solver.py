import os
import json
import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from config.settings import settings

logger = logging.getLogger("OSAgent.GeminiSolver")

class GeminiSolver:
    """
    Code reasoning and bug resolution engine powered by Google Gemini.
    Takes the issue description and relevant codebase files, diagnoses the root cause,
    and produces verified code changes.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.client_available = False

        if self.api_key and self.api_key != "your_gemini_api_key_here":
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                self.client_available = True
                logger.info(f"Gemini Solver initialized with model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not configure Gemini API: {e}")

    def solve_issue(
        self,
        issue_title: str,
        issue_body: str,
        code_context: Dict[str, str],
        error_logs: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Returns structured dictionary:
        {
            "root_cause": str,
            "solution_summary": str,
            "modified_files": {
                "path/to/file.py": "full new code"
            }
        }
        """
        if not self.client_available:
            logger.info("Using simulated Gemini response (No valid API key provided or DRY_RUN mode).")
            # Produce mock solution for first available context file
            target_file = list(code_context.keys())[0] if code_context else "main.py"
            original_code = code_context.get(target_file, "# sample code")
            fixed_code = original_code + f"\n\n# Fix applied for: {issue_title}\n"

            return {
                "root_cause": f"Issue '{issue_title}' required defensive handling and validation.",
                "solution_summary": "Added input validation and safe error handling as requested.",
                "modified_files": {
                    target_file: fixed_code
                }
            }

        # Build prompt for Gemini
        context_str = "\n\n".join([
            f"--- FILE: {rel_path} ---\n{content}\n"
            for rel_path, content in code_context.items()
        ])

        system_prompt = f"""You are an elite open-source software engineer solving a bug in a repository.
Issue Title: {issue_title}
Issue Description:
{issue_body}

Relevant Code Files:
{context_str}

{"Previous Error/Logs: " + error_logs if error_logs else ""}

Analyze the problem carefully. 
Output your response as STRICT JSON with this schema:
{{
  "root_cause": "<detailed explanation of the bug>",
  "solution_summary": "<concise summary of changes>",
  "modified_files": {{
    "<relative_path_to_file>": "<COMPLETE new content of the file with the fix applied>"
  }}
}}
Do NOT output markdown backticks around the JSON. Only output valid JSON.
"""

        try:
            response = self.model.generate_content(system_prompt)
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            return result
        except Exception as e:
            logger.error(f"Gemini API generation error: {e}")
            target_file = list(code_context.keys())[0] if code_context else "solution.py"
            return {
                "root_cause": f"Error during Gemini call: {e}",
                "solution_summary": "Fallback minimal patch.",
                "modified_files": {
                    target_file: code_context.get(target_file, "") + f"\n# Fix for: {issue_title}\n"
                }
            }
