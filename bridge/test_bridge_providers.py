"""Bridge provider contract: defaults, validation, keyless local path, env wiring."""

import asyncio
import io
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import bridge_runner as bridge


def run_bridge(config):
    """Run bridge.run with the production network guard neutralized.

    network_guard.install() monkeypatches the global socket object; in a
    joint Windows suite that blocks loopback and breaks event-loop creation,
    so these tests mock it. Production guard code is untouched.
    """
    with patch("network_guard.install", lambda: None):
        return asyncio.run(bridge.run(config))


class ProviderValidationTests(unittest.TestCase):
    def config(self, **overrides):
        base = {
            "contract_version": 1,
            "layout_vision_enabled": True,
            "job_id": "job-123",
            "video_url": "https://example.com/video",
        }
        base.update(overrides)
        return base

    def test_legacy_defaults_are_openrouter(self):
        config = bridge.validate_config(self.config())
        self.assertEqual(config["transcription_provider"], "openrouter")
        self.assertEqual(config["planner_provider"], "openrouter")
        self.assertEqual(config["opencode_model"], bridge.OPENCODE_DEFAULT_MODEL)
        self.assertEqual(config["opencode_command"], bridge.OPENCODE_DEFAULT_COMMAND)

    def test_rejects_unknown_providers(self):
        with self.assertRaises(ValueError):
            bridge.validate_config(self.config(transcription_provider="deepgram"))
        with self.assertRaises(ValueError):
            bridge.validate_config(self.config(planner_provider="ollama"))

    def test_rejects_unsafe_opencode_command(self):
        for bad in (
            "opencode --model x",
            "opencode; rm -rf /",
            "opencode && evil",
            "opencode|evil",
            "my/opencode",
            "..\\opencode",
            "open code",
            "",
        ):
            with self.subTest(command=bad):
                with self.assertRaises(ValueError):
                    bridge.validate_config(self.config(opencode_command=bad))

    def test_accepts_simple_and_absolute_commands(self):
        for good in ("opencode", "opencode.exe", r"C:\tools\opencode.exe"):
            if os.path.isabs(good) or good in ("opencode", "opencode.exe"):
                with self.subTest(command=good):
                    config = bridge.validate_config(self.config(opencode_command=good))
                    self.assertEqual(config["opencode_command"], good)

    def test_rejects_bad_model_and_timeout(self):
        with self.assertRaises(ValueError):
            bridge.validate_config(self.config(opencode_model="has space"))
        with self.assertRaises(ValueError):
            bridge.validate_config(self.config(opencode_model=""))
        with self.assertRaises(ValueError):
            bridge.validate_config(self.config(opencode_timeout_seconds=5))
        config = bridge.validate_config(self.config(opencode_timeout_seconds=120))
        self.assertEqual(config["opencode_timeout_seconds"], 120)

    def test_rejects_cmd_metachars_in_model(self):
        # The resolved Windows launcher is a .cmd file: cmd.exe
        # metacharacters must never reach its argv.
        for bad in ("a&b", "a|b", 'a"b', "a'b", "%a%", "a!b", "a^b", "a;b", "a>b", "(a)", "`a`", "$a"):
            with self.subTest(model=bad):
                with self.assertRaises(ValueError):
                    bridge.validate_config(self.config(opencode_model=bad))
        config = bridge.validate_config(self.config(opencode_model="opencode/muse-spark-1.3-contributor-free"))
        self.assertEqual(config["opencode_model"], "opencode/muse-spark-1.3-contributor-free")


class ProviderEnvAndKeyTests(unittest.TestCase):
    def config(self, **overrides):
        return {
            "contract_version": 1, "layout_vision_enabled": False,
            "job_id": "job-123", "video_url": "https://example.com/video",
            "transcription_provider": "local", "planner_provider": "opencode",
            **overrides,
        }

    def _modules(self, api_key, seen):
        from dataclasses import make_dataclass

        Output = make_dataclass("Output", [("clips", list)])

        class Pipeline:
            def __init__(self, **kwargs):
                pass

            async def process_video(self, request):
                return types.SimpleNamespace(status="completed", output=Output([]), job_id="job-123")

        def get_settings():
            seen["env"] = (
                os.environ.get("TRANSCRIPTION_PROVIDER"),
                os.environ.get("PLANNER_PROVIDER"),
                os.environ.get("OPENCODE_MODEL"),
                os.environ.get("OPENCODE_COMMAND"),
            )
            return types.SimpleNamespace(openrouter_api_key=api_key)

        return {
            "clip_engine.config": types.SimpleNamespace(
                get_settings=get_settings, get_caption_preset=lambda name: None),
            "clip_engine.bridge_contract": types.SimpleNamespace(BRIDGE_CONTRACT_VERSION=1),
            "clip_engine.logging_safety": types.SimpleNamespace(install_safe_logging=lambda: None),
            "clip_engine.services.ai_clipping_pipeline": types.SimpleNamespace(
                AIClippingPipeline=Pipeline, ClippingJobRequest=lambda **kwargs: kwargs,
                JobStatus=types.SimpleNamespace(COMPLETED="completed")),
        }

    def test_keyless_local_path_starts_without_openrouter_key(self):
        from dataclasses import make_dataclass

        Output = make_dataclass("Output", [("clips", list)])

        class Pipeline:
            def __init__(self, **kwargs):
                pass

            async def process_video(self, request):
                return types.SimpleNamespace(status="completed", output=Output([]), job_id="job-123")

        modules = {
            "clip_engine.config": types.SimpleNamespace(
                get_settings=lambda: types.SimpleNamespace(openrouter_api_key=None),
                get_caption_preset=lambda name: None),
            "clip_engine.bridge_contract": types.SimpleNamespace(BRIDGE_CONTRACT_VERSION=1),
            "clip_engine.logging_safety": types.SimpleNamespace(install_safe_logging=lambda: None),
            "clip_engine.services.ai_clipping_pipeline": types.SimpleNamespace(
                AIClippingPipeline=Pipeline, ClippingJobRequest=lambda **kwargs: kwargs,
                JobStatus=types.SimpleNamespace(COMPLETED="completed")),
        }
        with patch.dict(sys.modules, modules), redirect_stdout(io.StringIO()):
            self.assertTrue(run_bridge(self.config()))

    def test_openrouter_legacy_still_requires_key(self):
        seen = {}
        modules = self._modules(None, seen)
        with patch.dict(sys.modules, modules), redirect_stdout(io.StringIO()) as output:
            self.assertFalse(run_bridge(self.config(
                transcription_provider="openrouter", planner_provider="openrouter",
                layout_vision_enabled=False,
            )))
        self.assertIn("OPENROUTER_API_KEY", output.getvalue())

    def test_vision_enabled_requires_key_even_when_local(self):
        seen = {}
        modules = self._modules(None, seen)
        with patch.dict(sys.modules, modules), redirect_stdout(io.StringIO()) as output:
            self.assertFalse(run_bridge(self.config(layout_vision_enabled=True)))
        self.assertIn("OPENROUTER_API_KEY", output.getvalue())

    def test_providers_reach_settings_before_load(self):
        seen = {}
        modules = self._modules(None, seen)
        with patch.dict(sys.modules, modules), redirect_stdout(io.StringIO()):
            run_bridge(self.config(
                opencode_model="opencode/muse-spark-1.3-contributor-free",
                opencode_command="opencode",
            ))
        self.assertEqual(seen["env"], (
            "local", "opencode",
            "opencode/muse-spark-1.3-contributor-free", "opencode",
        ))


class ProviderFailureMessageTests(unittest.TestCase):
    def test_fixed_messages_map(self):
        self.assertEqual(
            bridge.describe_failure("OpenCode CLI is not available")["message"],
            "OpenCode CLI is not available.",
        )
        self.assertEqual(
            bridge.describe_failure("OpenCode planning timed out")["message"],
            "OpenCode planning timed out.",
        )
        self.assertEqual(
            bridge.describe_failure("OpenCode returned an unusable planning response")["message"],
            "OpenCode returned an unusable planning response.",
        )
        self.assertEqual(
            bridge.describe_failure("Local planning needs a transcript")["message"],
            "Local planning needs a transcript and has no vision model.",
        )
        self.assertEqual(
            bridge.describe_failure("Local transcription needs faster-whisper")["message"],
            "Local transcription is not available.",
        )


if __name__ == "__main__":
    unittest.main()
