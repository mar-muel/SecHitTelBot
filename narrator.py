"""AI-powered game narrator using Claude API."""

import logging
import os
from collections import deque

import anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

NARRATION_PROMPT = (
    "You are the narrator of a Secret Hitler board game. "
    "Write short, dramatic narrations of game events. "
    "Use a political thriller tone — think House of Cards meets a 1930s parliament. "
    "Keep it to 1-3 sentences, under 400 characters. Do not use emojis. "
    "Do not explain rules or game mechanics. "
    "Just narrate what happened in a dramatic, varied way. "
    "You will be given the recent group conversation between players. "
    "Weave in references to what players said — their accusations, alliances, "
    "promises, and betrayals — to make the narration feel personal and connected "
    "to the actual social dynamics at the table."
)

CONVERSATION_PROMPT = (
    "You are the narrator of a Secret Hitler board game. "
    "A player is addressing you directly in the group chat. "
    "Stay in character as a dramatic political thriller narrator. "
    "Keep your response to 1-3 sentences, under 400 characters. Do not use emojis. "
    "You do NOT know anyone's secret role. Do not reveal hidden game information. "
    "You may comment on the political drama, suspicions, and social dynamics. "
    "Be witty, mysterious, and theatrical."
)


class GameNarrator:
    """Tracks conversation and generates AI narrations for a single game."""

    def __init__(self):
        self.messages: deque[tuple[str, str]] = deque(maxlen=100)
        self.narrations: list[str] = []
        self._messages_since_last_narration: list[tuple[str, str]] = []

    def record_message(self, name: str, text: str):
        self.messages.append((name, text))
        self._messages_since_last_narration.append((name, text))

    def _build_history(self) -> str:
        """Build the narrative history: all AI narrations with [excluded user messages] gaps."""
        if not self.narrations:
            return ""
        parts = []
        for narration in self.narrations:
            parts.append(f"[Narrator]: {narration}")
            parts.append("[... excluded user messages ...]")
        return "\n".join(parts)

    def _build_recent_conversation(self) -> str:
        msgs = self._messages_since_last_narration[-30:]
        if not msgs:
            return "(no recent conversation)"
        return "\n".join(f"{name}: {text}" for name, text in msgs)

    def _build_prompt(self, event: str, context: dict) -> str:
        descriptions = {
            "policy_enacted": (
                f"President {context.get('president')} and Chancellor {context.get('chancellor')} "
                f"enacted a {context.get('policy')} policy. "
                f"Liberal track: {context.get('liberal_track')}/5, "
                f"Fascist track: {context.get('fascist_track')}/6."
            ),
            "vote_passed": (
                f"The vote passed. {context.get('president')} is President "
                f"and {context.get('chancellor')} is Chancellor."
            ),
            "vote_failed": (
                f"The vote failed. The people rejected President {context.get('president')} "
                f"and Chancellor {context.get('chancellor')}. "
                f"Failed elections: {context.get('failed_votes')}/3."
            ),
            "execution": (
                f"President {context.get('president')} executed {context.get('target')}. "
                f"{'They were Hitler!' if context.get('was_hitler') else 'They were not Hitler.'}"
            ),
            "anarchy": (
                f"Three elections failed in a row. Anarchy! "
                f"A {context.get('policy')} policy was enacted from the top of the pile."
            ),
            "game_over": f"Game over! {context.get('result')}",
            "veto_accepted": (
                f"Chancellor {context.get('chancellor')} proposed a veto "
                f"and President {context.get('president')} accepted it. No policy enacted."
            ),
            "game_start": (
                f"A new game of Secret Hitler begins with {context.get('num_players')} players: "
                f"{context.get('players')}. Tension fills the room."
            ),
            "veto_refused": (
                f"Chancellor {context.get('chancellor')} proposed a veto "
                f"but President {context.get('president')} refused it."
            ),
        }

        description = descriptions.get(event, event)
        history = self._build_history()
        conversation = self._build_recent_conversation()

        parts = []
        if history:
            parts.append(f"Your previous narrations:\n{history}")
        parts.append(f"Recent group conversation:\n{conversation}")
        parts.append(f"Event to narrate:\n{description}")
        return "\n\n".join(parts)

    async def narrate(self, event: str, context: dict) -> str | None:
        if not ANTHROPIC_API_KEY:
            return None

        prompt = self._build_prompt(event, context)

        try:
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                system=NARRATION_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()  # type: ignore[union-attr]
            if text.startswith("[Narrator]:"):
                text = text[len("[Narrator]:"):].strip()
            self.narrations.append(text)
            self._messages_since_last_narration = []
            logger.info(f"Narration for {event}: {text}")
            return text
        except Exception as e:
            logger.warning(f"Narrator failed for {event}: {e}")
            return None

    async def respond(self, player_name: str, message: str) -> str | None:
        """Respond to a player who addressed the narrator directly."""
        if not ANTHROPIC_API_KEY:
            return None

        history = self._build_history()
        conversation = self._build_recent_conversation()

        parts = []
        if history:
            parts.append(f"Your previous narrations:\n{history}")
        parts.append(f"Recent group conversation:\n{conversation}")
        parts.append(f"{player_name} says to you: {message}")

        prompt = "\n\n".join(parts)

        try:
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                system=CONVERSATION_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()  # type: ignore[union-attr]
            if text.startswith("[Narrator]:"):
                text = text[len("[Narrator]:"):].strip()
            logger.info(f"Narrator response to {player_name}: {text}")
            return text
        except Exception as e:
            logger.warning(f"Narrator respond failed: {e}")
            return None
