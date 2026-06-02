"""Unit tests for backends.py: Protocol, WhisperBackend, ParakeetBackend, factory."""
import unittest
from unittest import mock

import numpy as np


class TestWhisperBackend(unittest.TestCase):
    @mock.patch("backends.WhisperModel")
    def test_constructs_whisper_model_with_args(self, FakeWhisperModel):
        from backends import WhisperBackend
        WhisperBackend(model_size="tiny.en", device="cpu", compute_type="int8")
        FakeWhisperModel.assert_called_once_with(
            "tiny.en", device="cpu", compute_type="int8"
        )

    @mock.patch("backends.WhisperModel")
    def test_transcribe_delegates_to_underlying_model(self, FakeWhisperModel):
        from backends import WhisperBackend
        fake_model = FakeWhisperModel.return_value
        class Seg:
            text = "hello"
        fake_model.transcribe.return_value = ([Seg()], "info")

        backend = WhisperBackend("tiny.en", device="cpu", compute_type="int8")
        audio = np.zeros(16000, dtype=np.float32)
        segments, info = backend.transcribe(audio, beam_size=3, language="en", vad_filter=True)

        fake_model.transcribe.assert_called_once_with(
            audio, beam_size=3, language="en", vad_filter=True,
        )
        self.assertEqual(list(segments)[0].text, "hello")
        self.assertEqual(info, "info")


class TestParakeetBackend(unittest.TestCase):
    def test_lazy_imports_nemo_inside_init(self):
        import sys
        from backends import ParakeetBackend
        # ParakeetBackend.__init__ imports nemo lazily; the module class import
        # alone must not have imported nemo.collections.asr.
        self.assertNotIn("nemo.collections.asr", sys.modules,
                         "nemo.collections.asr must not be imported until ParakeetBackend() is constructed")

    def test_constructs_and_transcribes_with_mocked_nemo(self):
        from backends import ParakeetBackend
        fake_nemo_module = mock.MagicMock()
        fake_asr_model_cls = fake_nemo_module.collections.asr.models.ASRModel
        fake_loaded = fake_asr_model_cls.from_pretrained.return_value
        fake_half = fake_loaded.half.return_value
        fake_on_device = fake_half.to.return_value
        fake_hyp = mock.MagicMock()
        fake_hyp.text = "hello pepper"
        fake_on_device.transcribe.return_value = [fake_hyp]

        with mock.patch.dict("sys.modules", {
            "nemo": fake_nemo_module,
            "nemo.collections": fake_nemo_module.collections,
            "nemo.collections.asr": fake_nemo_module.collections.asr,
            "nemo.collections.asr.models": fake_nemo_module.collections.asr.models,
        }):
            backend = ParakeetBackend(
                model_name="nvidia/parakeet-tdt-0.6b-v2", device="cuda",
            )
            audio = np.zeros(16000, dtype=np.float32)
            segments, info = backend.transcribe(audio)
            seg_list = list(segments)

        fake_asr_model_cls.from_pretrained.assert_called_once_with(
            "nvidia/parakeet-tdt-0.6b-v2", map_location="cpu",
        )
        fake_loaded.half.assert_called_once_with()
        fake_half.to.assert_called_once_with("cuda")
        fake_on_device.transcribe.assert_called_once()
        self.assertEqual(len(seg_list), 1)
        self.assertEqual(seg_list[0].text, "hello pepper")
        self.assertIsNone(info)


class TestMakeBackend(unittest.TestCase):
    @mock.patch("backends.WhisperModel")
    def test_whisper_branch_returns_whisper_backend(self, FakeWhisperModel):
        from backends import WhisperBackend, make_backend
        backend = make_backend({"engine": "whisper", "whisper_model": "base.en"})
        self.assertIsInstance(backend, WhisperBackend)
        FakeWhisperModel.assert_called_once_with(
            "base.en", device="cpu", compute_type="int8",
        )

    @mock.patch("torch.cuda.is_available", return_value=False)
    def test_parakeet_without_cuda_raises_loud_error(self, _is_avail):
        from backends import EngineLoadError, make_backend
        with self.assertRaises(EngineLoadError) as ctx:
            make_backend({"engine": "parakeet", "parakeet_model": "nvidia/parakeet-tdt-0.6b-v2"})
        msg = str(ctx.exception)
        # Loud-failure contract: the message must be actionable.
        self.assertIn("CUDA", msg)
        self.assertIn("torch.cuda.is_available()", msg)
        self.assertIn("STT_DOCKER_RUNTIME", msg)
        self.assertIn("STT_GPU_DEVICES", msg)
        self.assertIn("engine: whisper", msg)

    @mock.patch("torch.cuda.is_available", return_value=True)
    def test_parakeet_with_cuda_returns_parakeet_backend(self, _is_avail):
        from backends import ParakeetBackend, make_backend
        fake_nemo_module = mock.MagicMock()
        fake_asr_model_cls = fake_nemo_module.collections.asr.models.ASRModel
        with mock.patch.dict("sys.modules", {
            "nemo": fake_nemo_module,
            "nemo.collections": fake_nemo_module.collections,
            "nemo.collections.asr": fake_nemo_module.collections.asr,
            "nemo.collections.asr.models": fake_nemo_module.collections.asr.models,
        }):
            backend = make_backend({
                "engine": "parakeet",
                "parakeet_model": "nvidia/parakeet-tdt-0.6b-v2",
            })
        self.assertIsInstance(backend, ParakeetBackend)
        fake_asr_model_cls.from_pretrained.assert_called_once_with(
            "nvidia/parakeet-tdt-0.6b-v2", map_location="cpu",
        )

    def test_unknown_engine_raises(self):
        from backends import EngineLoadError, make_backend
        with self.assertRaises(EngineLoadError) as ctx:
            make_backend({"engine": "bogus"})
        self.assertIn("Unknown engine: 'bogus'", str(ctx.exception))
        self.assertIn("'whisper'", str(ctx.exception))
        self.assertIn("'parakeet'", str(ctx.exception))
