"""Tests for speech with a body-language mode: the robot client call, and the path chosen for each LLM reply."""
import unittest
from unittest.mock import MagicMock, patch

from naoqi_proxy import NaoqiProxyError

from pepper_wizard.cli import _dispatch_to_llm
from pepper_wizard.llm.client import ReplyResult
from pepper_wizard.robot_client import RobotClient


def make_robot_client():
    """RobotClient over a mocked NAOqi proxy and a mocked logger."""
    with patch("pepper_wizard.robot_client.NaoqiClient"):
        robot = RobotClient("localhost", 5000)
    robot.logger = MagicMock()
    return robot


class BodyLanguageTalkTests(unittest.TestCase):
    def test_speaks_through_animated_speech_with_the_mode(self):
        """The reply goes to ALAnimatedSpeech.say with the mode and without its carets, which animated speech reads as instructions; the Speech event carries the mode."""
        robot = make_robot_client()
        self.assertTrue(robot.body_language_talk("random", "hello ^there"))
        robot.client.ALAnimatedSpeech.say.assert_called_once_with("hello there", {"bodyLanguageMode": "random"})
        robot.logger.info.assert_called_once_with("Speech", {"text": "hello there", "type": "animated", "mode": "random"})

    def test_a_failed_animated_call_falls_back_to_plain_speech(self):
        """On a proxy error the reply is spoken through ALTextToSpeech, the method returns False and the fallback is logged."""
        robot = make_robot_client()
        robot.client.ALAnimatedSpeech.say.side_effect = NaoqiProxyError("no such method")
        self.assertFalse(robot.body_language_talk("contextual", "hello"))
        robot.client.ALTextToSpeech.say.assert_called_once_with("hello")
        robot.logger.warning.assert_called_once_with("SpeechFallback", {"mode": "contextual", "error": "no such method"})


class FakeLLM:
    """Returns one fixed reply carrying the given body_language value."""

    def __init__(self, body_language):
        self._result = ReplyResult("I am here", "abc123", None, body_language=body_language)

    def reply(self, user_text):
        return self._result


class DispatchTests(unittest.TestCase):
    def dispatch(self, body_language, spoke_animated=True):
        """Run one LLM turn; return the fake robot client and the three speech fields of the logged LLMTurn."""
        robot, logger = MagicMock(), MagicMock()
        robot.body_language_talk.return_value = spoke_animated
        _dispatch_to_llm("hello", source="typed", llm=FakeLLM(body_language), stt=MagicMock(), robot_client=robot, logger=logger)
        turn = [call[0][1] for call in logger.info.call_args_list if call[0][0] == "LLMTurn"][0]
        return robot, (turn["body_language"], turn["speech_path"], turn["speech_fallback"])

    def test_without_the_key_the_reply_is_spoken_plainly(self):
        """A config with no body_language keeps ALTextToSpeech, as before the key existed."""
        robot, fields = self.dispatch(None)
        robot.talk.assert_called_once_with("I am here")
        robot.body_language_talk.assert_not_called()
        self.assertEqual(fields, (None, "plain", False))

    def test_with_the_key_the_reply_is_spoken_with_that_mode(self):
        """A config with body_language sends the reply through animated speech with that mode."""
        robot, fields = self.dispatch("disabled")
        robot.body_language_talk.assert_called_once_with("disabled", "I am here")
        robot.talk.assert_not_called()
        self.assertEqual(fields, ("disabled", "animated", False))

    def test_a_fallback_is_recorded_on_the_turn(self):
        """When the animated call fell back, the turn records the plain path and the fallback."""
        _, fields = self.dispatch("random", spoke_animated=False)
        self.assertEqual(fields, ("random", "plain", True))


if __name__ == "__main__":
    unittest.main()
