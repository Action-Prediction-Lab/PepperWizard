"""Tests for speech with a body-language mode: the robot client call, and the path chosen for each LLM reply."""
import threading
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


class GestureSwitchTalkTests(unittest.TestCase):
    OPENS_ON = "hello ^pCall(GestureSwitch.off()) there"
    OPENS_OFF = '^pCall(ALMotion.setBreathEnabled("Arms", true)) hello ^pCall(GestureSwitch.on()) there'

    def calls(self, robot):
        """The GestureSwitch and speech calls in the order the robot client made them."""
        return [c[0] for c in robot.client.method_calls if c[0] in ("GestureSwitch.off_now", "GestureSwitch.on", "ALAnimatedSpeech.say", "ALTextToSpeech.say")]

    def test_speaks_the_annotated_text_as_it_is_between_two_calls_to_on(self):
        """The instructions keep their carets, and a reply that opens with gestures has GestureSwitch.on() before and after it."""
        robot = make_robot_client()
        self.assertEqual(robot.gesture_switch_talk("contextual", "hello there", self.OPENS_ON, off_now=False), (True, True))
        robot.client.ALAnimatedSpeech.say.assert_called_once_with(self.OPENS_ON, {"bodyLanguageMode": "contextual"})
        self.assertEqual(self.calls(robot), ["GestureSwitch.on", "ALAnimatedSpeech.say", "GestureSwitch.on"])
        robot.logger.info.assert_called_once_with("Speech", {"text": self.OPENS_ON, "type": "animated", "mode": "contextual", "off_now": False})

    def test_off_now_takes_the_arms_before_the_reply_starts(self):
        robot = make_robot_client()
        robot.gesture_switch_talk("random", "hello there", self.OPENS_OFF, off_now=True)
        self.assertEqual(self.calls(robot), ["GestureSwitch.off_now", "ALAnimatedSpeech.say", "GestureSwitch.on"])

    def test_on_follows_even_when_off_now_raises(self):
        robot = make_robot_client()
        robot.client.GestureSwitch.off_now.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            robot.gesture_switch_talk("random", "hello there", self.OPENS_OFF, off_now=True)
        self.assertEqual(self.calls(robot), ["GestureSwitch.off_now", "GestureSwitch.on"])

    def test_a_failed_animated_call_falls_back_to_plain_speech_and_still_frees_the_arms(self):
        robot = make_robot_client()
        robot.client.ALAnimatedSpeech.say.side_effect = NaoqiProxyError("no such method")
        self.assertEqual(robot.gesture_switch_talk("contextual", "hello there", self.OPENS_OFF, off_now=True), (False, True))
        robot.client.ALTextToSpeech.say.assert_called_once_with("hello there")
        self.assertEqual(self.calls(robot)[-1], "GestureSwitch.on")
        robot.logger.warning.assert_any_call("SpeechFallback", {"mode": "contextual", "error": "no such method"})

    def test_an_unreachable_switch_is_logged_and_the_reply_is_still_spoken(self):
        robot = make_robot_client()
        robot.client.GestureSwitch.off_now.side_effect = NaoqiProxyError("no service GestureSwitch")
        robot.client.GestureSwitch.on.side_effect = NaoqiProxyError("no service GestureSwitch")
        self.assertEqual(robot.gesture_switch_talk("contextual", "hello there", self.OPENS_OFF, off_now=True), (True, False))
        robot.client.ALAnimatedSpeech.say.assert_called_once()
        robot.logger.warning.assert_any_call("GestureSwitchCallFailed", {"method": "off_now", "error": "no service GestureSwitch"})
        robot.logger.warning.assert_any_call("GestureSwitchCallFailed", {"method": "on", "error": "no service GestureSwitch"})

    def test_arms_that_could_not_be_taken_are_logged(self):
        robot = make_robot_client()
        robot.client.GestureSwitch.off_now.return_value = False
        self.assertEqual(robot.gesture_switch_talk("contextual", "hello there", self.OPENS_OFF, off_now=True), (True, False))
        robot.logger.warning.assert_any_call("GestureSwitchCallFailed", {"method": "off_now", "error": "GestureSwitch did not take the arms"})


class FakeLLM:
    """Returns one fixed reply carrying the given body_language and gesture_instructions values."""

    def __init__(self, body_language, gesture_instructions=None):
        self._result = ReplyResult("I am ^here", "abc123", None, body_language=body_language, gesture_instructions=gesture_instructions)

    def reply(self, user_text):
        return self._result


INSTRUCTIONS = {"endpoint": "tcp://localhost:5582", "timeout_s": 1.0}


class DispatchTests(unittest.TestCase):
    def dispatch(self, body_language, spoke_animated=True, gesture_instructions=None, switch_call_ok=True):
        """Run one LLM turn; return the fake robot client and the three speech fields of the logged LLMTurn."""
        robot, logger = MagicMock(), MagicMock()
        robot.body_language_talk.return_value = spoke_animated
        robot.gesture_switch_talk.return_value = (spoke_animated, switch_call_ok)
        _dispatch_to_llm("hello", source="typed", llm=FakeLLM(body_language, gesture_instructions), stt=MagicMock(), robot_client=robot, logger=logger)
        turn = [call[0][1] for call in logger.info.call_args_list if call[0][0] == "LLMTurn"][0]
        self.turn, self.logger = turn, logger
        return robot, (turn["body_language"], turn["speech_path"], turn["speech_fallback"])

    def test_without_the_key_the_reply_is_spoken_plainly(self):
        """A config with no body_language keeps ALTextToSpeech, as before the key existed."""
        robot, fields = self.dispatch(None)
        robot.talk.assert_called_once_with("I am ^here")
        robot.body_language_talk.assert_not_called()
        self.assertEqual(fields, (None, "plain", False))
        self.assertEqual((self.turn["gesture_instructions"], self.turn["off_now"], self.turn["gesture_switch_call_failed"]), (None, None, None))

    def test_with_the_key_the_reply_is_spoken_with_that_mode(self):
        """A config with body_language sends the reply through animated speech with that mode."""
        robot, fields = self.dispatch("disabled")
        robot.body_language_talk.assert_called_once_with("disabled", "I am ^here")
        robot.talk.assert_not_called()
        self.assertEqual(fields, ("disabled", "animated", False))

    def test_a_fallback_is_recorded_on_the_turn(self):
        """When the animated call fell back, the turn records the plain path and the fallback."""
        _, fields = self.dispatch("random", spoke_animated=False)
        self.assertEqual(fields, ("random", "plain", True))

    def test_with_gesture_instructions_the_reply_goes_to_the_experiment_without_carets_and_is_spoken_as_it_comes_back(self):
        answer = {"status": "ok", "text": '^pCall(ALMotion.setBreathEnabled("Arms", true)) I am ^pCall(GestureSwitch.on()) here', "off_now": True, "turn": 4, "duty": 0.2}
        with patch("pepper_wizard.cli.request_instructions", return_value=answer) as ask:
            robot, fields = self.dispatch("contextual", gesture_instructions=INSTRUCTIONS)
        ask.assert_called_once_with(INSTRUCTIONS, "I am here")
        robot.gesture_switch_talk.assert_called_once_with("contextual", "I am ^here", answer["text"], True)
        robot.body_language_talk.assert_not_called()
        self.assertEqual((self.turn["gesture_instructions"], self.turn["off_now"], self.turn["speech_fallback"], self.turn["gesture_switch_call_failed"]), ("ok", True, False, False))

    def test_a_failed_gesture_switch_call_before_the_reply_is_recorded_on_the_turn(self):
        answer = {"status": "ok", "text": '^pCall(ALMotion.setBreathEnabled("Arms", true)) I am ^pCall(GestureSwitch.on()) here', "off_now": True, "turn": 4, "duty": 0.2}
        with patch("pepper_wizard.cli.request_instructions", return_value=answer):
            self.dispatch("contextual", gesture_instructions=INSTRUCTIONS, switch_call_ok=False)
        self.assertIs(self.turn["gesture_switch_call_failed"], True)

    def test_instructions_whose_reply_fell_back_to_plain_speech_record_the_fallback(self):
        answer = {"status": "ok", "text": "I am ^pCall(GestureSwitch.off()) here", "off_now": False, "turn": 4, "duty": 0.2}
        robot, logger = MagicMock(), MagicMock()
        robot.gesture_switch_talk.return_value = (False, True)
        with patch("pepper_wizard.cli.request_instructions", return_value=answer):
            _dispatch_to_llm("hello", source="typed", llm=FakeLLM("contextual", INSTRUCTIONS), stt=MagicMock(), robot_client=robot, logger=logger)
        turn = [call[0][1] for call in logger.info.call_args_list if call[0][0] == "LLMTurn"][0]
        self.assertEqual((turn["gesture_instructions"], turn["speech_fallback"]), ("ok", True))

    def test_without_an_answer_the_reply_is_spoken_without_instructions_and_the_turn_says_so(self):
        """Without an answer Pepper speaks the reply without its carets and with no instructions, between the same GestureSwitch calls."""
        from pepper_wizard.gesture_instructions import GestureInstructionsUnavailable
        with patch("pepper_wizard.cli.request_instructions", side_effect=GestureInstructionsUnavailable("no answer within 1.0 s")):
            robot, fields = self.dispatch("contextual", gesture_instructions=INSTRUCTIONS)
        robot.gesture_switch_talk.assert_called_once_with("contextual", "I am ^here", "I am here", False)
        robot.body_language_talk.assert_not_called()
        self.assertEqual((self.turn["gesture_instructions"], self.turn["off_now"]), ("unavailable", None))
        self.logger.warning.assert_any_call("GestureInstructionsUnavailable", {"error": "no answer within 1.0 s"})

    def test_plain_speech_asks_for_no_instructions(self):
        """Without body_language the dispatch speaks the reply through ALTextToSpeech and asks for no instructions."""
        with patch("pepper_wizard.cli.request_instructions") as ask:
            robot, _ = self.dispatch(None, gesture_instructions=INSTRUCTIONS)
        ask.assert_not_called()
        robot.talk.assert_called_once_with("I am ^here")

    def test_a_second_reply_asks_for_its_instructions_only_after_the_first_reply_is_logged(self):
        """Two replies dispatched at once each ask, speak and log their LLMTurn before the other asks."""
        order, speaking, release = [], threading.Event(), threading.Event()

        def ask(config, text):
            order.append("ask")
            return {"status": "ok", "text": text, "off_now": False}

        def talk(*args):
            order.append("speak")
            speaking.set()
            release.wait(2.0)
            return True, True
        robot, logger = MagicMock(), MagicMock()
        robot.gesture_switch_talk.side_effect = talk
        logger.info.side_effect = lambda event, data: order.append("logged") if event == "LLMTurn" else None

        def dispatch():
            _dispatch_to_llm("hello", source="typed", llm=FakeLLM("contextual", INSTRUCTIONS), stt=MagicMock(), robot_client=robot, logger=logger)
        with patch("pepper_wizard.cli.request_instructions", side_effect=ask):
            first = threading.Thread(target=dispatch, daemon=True)
            first.start()
            self.assertTrue(speaking.wait(2.0))
            second = threading.Thread(target=dispatch, daemon=True)
            second.start()
            second.join(0.1)
            release.set()
            first.join(2.0)
            second.join(2.0)
        self.assertEqual(order, ["ask", "speak", "logged", "ask", "speak", "logged"])


if __name__ == "__main__":
    unittest.main()
