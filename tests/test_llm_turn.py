"""Tests for the LLMTurn record written after each LLM reply."""
import unittest
from unittest.mock import MagicMock

from pepper_wizard.cli import _dispatch_to_llm
from pepper_wizard.llm.client import ReplyResult


class LLMTurnTests(unittest.TestCase):
    def test_the_turn_records_the_model_identity(self):
        """The LLMTurn record carries the id of the model that answered."""
        llm, logger = MagicMock(), MagicMock()
        llm.reply.return_value = ReplyResult("I am here", "abc123", None, model_identity="claude-haiku-4-5-20251001")
        _dispatch_to_llm("hello", source="typed", llm=llm, stt=MagicMock(), robot_client=MagicMock(), logger=logger)
        turn = [call[0][1] for call in logger.info.call_args_list if call[0][0] == "LLMTurn"][0]
        self.assertEqual(turn["model_identity"], "claude-haiku-4-5-20251001")


if __name__ == "__main__":
    unittest.main()
