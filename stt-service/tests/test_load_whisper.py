"""Unit tests for _load_whisper device-resolver in main.py."""
import os
import unittest
from unittest import mock


class TestLoadWhisper(unittest.TestCase):
    """Exercises _load_whisper without actually loading a Whisper model — WhisperModel is patched."""

    @mock.patch("main.WhisperModel")
    def test_explicit_cpu_uses_cpu_int8(self, MockWhisper):
        from main import _load_whisper
        _load_whisper("tiny.en", device="cpu")
        MockWhisper.assert_called_once_with("tiny.en", device="cpu", compute_type="int8")

    @mock.patch("main.WhisperModel")
    def test_explicit_cpu_honours_custom_compute_type(self, MockWhisper):
        from main import _load_whisper
        _load_whisper("tiny.en", device="cpu", compute_type="float32")
        MockWhisper.assert_called_once_with("tiny.en", device="cpu", compute_type="float32")

    @mock.patch("main.WhisperModel")
    def test_explicit_cuda_uses_cuda_float16(self, MockWhisper):
        from main import _load_whisper
        _load_whisper("tiny.en", device="cuda")
        MockWhisper.assert_called_once_with("tiny.en", device="cuda", compute_type="float16")

    @mock.patch("main.WhisperModel")
    def test_explicit_cuda_reraises_runtime_error(self, MockWhisper):
        from main import _load_whisper
        MockWhisper.side_effect = RuntimeError("CUDA driver version is insufficient")
        with self.assertRaises(RuntimeError):
            _load_whisper("tiny.en", device="cuda")
        self.assertEqual(MockWhisper.call_count, 1)

    @mock.patch("main.WhisperModel")
    def test_auto_succeeds_on_cuda(self, MockWhisper):
        from main import _load_whisper
        _load_whisper("tiny.en", device="auto")
        MockWhisper.assert_called_once_with("tiny.en", device="cuda", compute_type="float16")

    @mock.patch("main.WhisperModel")
    def test_auto_falls_back_to_cpu_on_runtime_error(self, MockWhisper):
        from main import _load_whisper
        sentinel_cpu_model = mock.MagicMock(name="cpu_model")
        MockWhisper.side_effect = [RuntimeError("no GPU"), sentinel_cpu_model]
        result = _load_whisper("tiny.en", device="auto")
        self.assertIs(result, sentinel_cpu_model)
        self.assertEqual(MockWhisper.call_count, 2)
        first_call = MockWhisper.call_args_list[0]
        second_call = MockWhisper.call_args_list[1]
        self.assertEqual(first_call.kwargs, {"device": "cuda", "compute_type": "float16"})
        self.assertEqual(second_call.kwargs, {"device": "cpu", "compute_type": "int8"})

    @mock.patch("main.WhisperModel")
    def test_auto_falls_back_on_value_error(self, MockWhisper):
        """CTranslate2 raises ValueError for unsupported compute_type — fallback should still engage."""
        from main import _load_whisper
        MockWhisper.side_effect = [ValueError("unsupported"), mock.MagicMock()]
        _load_whisper("tiny.en", device="auto")
        self.assertEqual(MockWhisper.call_count, 2)

    @mock.patch("main.WhisperModel")
    def test_reads_env_when_args_omitted(self, MockWhisper):
        from main import _load_whisper
        with mock.patch.dict(os.environ, {"STT_DEVICE": "cpu", "STT_COMPUTE_TYPE": "int8"}, clear=False):
            _load_whisper("tiny.en")
        MockWhisper.assert_called_once_with("tiny.en", device="cpu", compute_type="int8")


class TestSTTServiceUsesLoadWhisper(unittest.TestCase):
    """Ensures STTService.__init__ routes model construction through _load_whisper."""

    @mock.patch("main._load_whisper")
    def test_init_calls_load_whisper_with_model_size(self, mock_loader):
        mock_loader.return_value = mock.MagicMock()
        # Import lazily to avoid triggering the real WhisperModel at module-import time
        # (the patch on main._load_whisper is already in effect before this line).
        from main import STTService
        svc = STTService(model_size="tiny.en", zmq_port=15572, sample_rate=16000)
        try:
            mock_loader.assert_called_once_with("tiny.en")
            self.assertIs(svc.model, mock_loader.return_value)
        finally:
            svc.socket.close(linger=0)
            svc.context.term()


if __name__ == "__main__":
    unittest.main()
