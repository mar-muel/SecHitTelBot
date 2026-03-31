import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from narrator import GameNarrator
from controller import GameConfig, maybe_narrate


class TestGameNarrator:
    def test_record_message(self):
        n = GameNarrator()
        n.record_message("Alice", "I'm liberal, trust me")
        n.record_message("Bob", "Sure you are")
        assert len(n.messages) == 2
        assert len(n._messages_since_last_narration) == 2

    def test_record_message_max_100(self):
        n = GameNarrator()
        for i in range(120):
            n.record_message("Player", f"msg {i}")
        assert len(n.messages) == 100

    def test_build_history_empty(self):
        n = GameNarrator()
        assert n._build_history() == ""

    def test_build_history_with_narrations(self):
        n = GameNarrator()
        n.narrations = ["The parliament trembled.", "A dark policy emerged."]
        history = n._build_history()
        assert "[Narrator]: The parliament trembled." in history
        assert "[Narrator]: A dark policy emerged." in history
        assert "[... excluded user messages ...]" in history

    def test_build_recent_conversation_empty(self):
        n = GameNarrator()
        assert n._build_recent_conversation() == "(no recent conversation)"

    def test_build_recent_conversation(self):
        n = GameNarrator()
        n.record_message("Alice", "hello")
        n.record_message("Bob", "hi")
        conv = n._build_recent_conversation()
        assert "Alice: hello" in conv
        assert "Bob: hi" in conv

    def test_build_recent_conversation_caps_at_30(self):
        n = GameNarrator()
        for i in range(50):
            n.record_message("Player", f"msg {i}")
        conv = n._build_recent_conversation()
        assert "msg 0" not in conv
        assert "msg 49" in conv

    def test_messages_since_narration_resets(self):
        n = GameNarrator()
        n.record_message("Alice", "before")
        n.narrations.append("A narration happened.")
        n._messages_since_last_narration = []
        n.record_message("Bob", "after")
        assert len(n._messages_since_last_narration) == 1
        assert n._messages_since_last_narration[0] == ("Bob", "after")

    @pytest.mark.asyncio
    async def test_narrate_no_api_key(self):
        n = GameNarrator()
        with patch("narrator.ANTHROPIC_API_KEY", ""):
            result = await n.narrate("policy_enacted", {"president": "Alice"})
        assert result is None

    @pytest.mark.asyncio
    async def test_narrate_calls_api(self):
        n = GameNarrator()
        n.record_message("Alice", "trust me")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="The chamber erupted in chaos.")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("narrator.ANTHROPIC_API_KEY", "test-key"), \
             patch("narrator.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await n.narrate("policy_enacted", {
                "president": "Alice", "chancellor": "Bob", "policy": "fascist",
                "liberal_track": 1, "fascist_track": 2,
            })

        assert result == "The chamber erupted in chaos."
        assert len(n.narrations) == 1
        assert n._messages_since_last_narration == []

    @pytest.mark.asyncio
    async def test_narrate_api_failure_returns_none(self):
        n = GameNarrator()

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API down"))

        with patch("narrator.ANTHROPIC_API_KEY", "test-key"), \
             patch("narrator.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await n.narrate("policy_enacted", {"president": "Alice"})

        assert result is None
        assert len(n.narrations) == 0


class TestMaybeNarrate:
    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        bot = AsyncMock()
        session = MagicMock()
        session.config = GameConfig(ai_narration=False)
        await maybe_narrate(bot, session, "policy_enacted", {})
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_when_enabled(self):
        bot = AsyncMock()
        session = MagicMock()
        session.config = GameConfig(ai_narration=True)
        session.cid = -999
        session.narrator = AsyncMock()
        session.narrator.narrate = AsyncMock(return_value="Drama unfolds.")
        await maybe_narrate(bot, session, "policy_enacted", {})
        bot.send_message.assert_called_once_with(-999, "📖 Drama unfolds.")

    @pytest.mark.asyncio
    async def test_skips_when_narration_fails(self):
        bot = AsyncMock()
        session = MagicMock()
        session.config = GameConfig(ai_narration=True)
        session.narrator = AsyncMock()
        session.narrator.narrate = AsyncMock(return_value=None)
        await maybe_narrate(bot, session, "policy_enacted", {})
        bot.send_message.assert_not_called()


class TestGameConfig:
    def test_defaults(self):
        c = GameConfig()
        assert c.ai_narration is False

    def test_toggle(self):
        c = GameConfig()
        c.ai_narration = True
        assert c.ai_narration is True
