"""
Base agent class shared by all company agents.
Requires: pip install anthropic
Requires: ANTHROPIC_API_KEY environment variable
"""

import os
import sys
from datetime import datetime
from typing import Optional
import anthropic


class BaseAgent:
    """Multi-turn conversational agent backed by Claude."""

    MODEL = "claude-opus-4-8"
    MAX_TOKENS = 8096

    def __init__(self, name: str, role_tag: str, system_prompt: str):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            sys.exit("ERROR: ANTHROPIC_API_KEY environment variable not set.")

        self.name = name
        self.role_tag = role_tag
        self.system_prompt = system_prompt
        self.client = anthropic.Anthropic(api_key=api_key)
        self.history: list[dict] = []
        self._session_start = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def chat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        response = self.client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=self.system_prompt,
            messages=self.history,
        )
        reply = response.content[0].text
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        self.history = []

    # ------------------------------------------------------------------
    # REPL
    # ------------------------------------------------------------------

    def run(self, greeting: Optional[str] = None) -> None:
        width = 62
        print("\n" + "=" * width)
        print(f"  {self.name}  |  session {self._session_start}")
        print("=" * width)
        print("  Commands:  'exit' quit  |  'clear' reset conversation")
        print("=" * width + "\n")

        if greeting:
            print(f"[{self.role_tag}] {greeting}\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not user_input:
                continue
            if user_input.lower() == "exit":
                print("Session ended.")
                break
            if user_input.lower() == "clear":
                self.reset()
                print("Conversation cleared.\n")
                continue

            try:
                reply = self.chat(user_input)
            except anthropic.APIError as exc:
                print(f"[API error] {exc}\n")
                continue

            print(f"\n[{self.role_tag}] {reply}\n")
