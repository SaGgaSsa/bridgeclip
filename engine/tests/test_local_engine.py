"""Offline tests for the local engine path: faster-whisper mapping and OpenCode CLI.

No network, no renders, no real models. faster-whisper and the opencode
binary are always mocked.
"""

import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from clip_engine.config import Settings
from clip_engine.services import opencode_planner as opencode_module
from clip_engine.services.ai_clipping_pipeline import AIClippingPipeline
from clip_engine.services.intelligence_planner import (
    ClipPlanResponse,
    IntelligencePlannerService,
    PlanningApiCosts,
)
from clip_engine.services.opencode_planner import (
    LOCAL_NO_TRANSCRIPT_MESSAGE,
    OPENCODE_INVALID_MESSAGE,
    OPENCODE_MISSING_MESSAGE,
    OPENCODE_TIMEOUT_MESSAGE,
    OpenCodePlannerError,
    build_opencode_args,
    build_opencode_prompt,
    extract_final_response,
)
from clip_engine.services.transcription_service import (
    TranscriptionApiCosts,
    TranscriptionProviderError,
    TranscriptionService,
    TranscriptSegment,
    TranscriptWord,
    TranscriptionResult,
)


def make_transcription_service(**overrides):
    service = TranscriptionService.__new__(TranscriptionService)
    service.settings = Settings(
        _env_file=None, openrouter_api_key=None, **overrides,
    )
    return service


def make_planner(**overrides):
    planner = IntelligencePlannerService.__new__(IntelligencePlannerService)
    planner.settings = Settings(
        _env_file=None, openrouter_api_key=None, **overrides,
    )
    planner._http_client = None
    return planner


def make_transcript(seconds=300):
    segments = []
    for start in range(0, seconds, 5):
        words = [
            TranscriptWord(word=f"word{start}", start_time_ms=start * 1000, end_time_ms=start * 1000 + 2000),
            TranscriptWord(word="end.", start_time_ms=start * 1000 + 2000, end_time_ms=start * 1000 + 4500),
        ]
        segments.append(TranscriptSegment(
            start_time_ms=start * 1000, end_time_ms=start * 1000 + 4500,
            text=f"word{start} end.", speaker_label=None, words=words,
        ))
    return TranscriptionResult(segments=segments, full_text="", duration_seconds=seconds)


def clip(start, end, scores=(8, 8, 8, 8, 8)):
    return {
        "start_time": start, "end_time": end, "summary": "Great Title Here",
        "scores": dict(zip(("hook", "standalone", "arc", "quotability", "ending"), scores)),
        "tags": ["tag"], "emphasis": ["word"],
    }


class TestLocalWordMapping:
    def test_maps_dict_and_object_words_to_ms(self):
        service = make_transcription_service(transcription_provider="local")
        words = service._map_local_words([
            {"word": " Hello ", "start": 0.2, "end": 0.5},
            SimpleNamespace(word="there.", start=0.5, end=1.2),
        ])
        assert [(w.word, w.start_time_ms, w.end_time_ms) for w in words] == [
            ("Hello", 200, 500), ("there.", 500, 1200),
        ]

    def test_skips_invalid_timings_without_inventing_words(self):
        service = make_transcription_service(transcription_provider="local")
        words = service._map_local_words([
            {"word": "ok", "start": 0.0, "end": 0.2},
            {"word": "bad-nan", "start": float("nan"), "end": 1.0},
            {"word": "bad-order", "start": 2.0, "end": 1.0},
            {"word": "bad-negative", "start": -1.0, "end": 0.5},
            {"word": "   ", "start": 0.5, "end": 0.6},
            {"word": "later", "start": 5.0, "end": 5.2},
            {"word": "backwards", "start": 1.0, "end": 1.2},
            {"word": 123, "start": 6.0, "end": 6.2},
        ])
        assert [w.word for w in words] == ["ok", "later"]

    def test_empty_audio_returns_empty_result(self):
        service = make_transcription_service(transcription_provider="local")
        result = service._build_local_result([], "en", 12.5, "small")
        assert result.segments == [] and result.full_text == ""
        assert result.provider == "local" and result.model == "small"
        assert result.language == "en"
        assert result.duration_seconds == 12.5
        assert result.api_costs.estimated_cost_usd == 0.0

    def test_builds_segments_without_diarization(self):
        service = make_transcription_service(transcription_provider="local")
        result = service._build_local_result(
            [{"text": "hello world.", "start": 1.0, "end": 2.0, "words": [
                {"word": "hello", "start": 1.0, "end": 1.5},
                {"word": "world.", "start": 1.5, "end": 2.0},
            ]}],
            "en", 2.0, "small",
        )
        assert len(result.segments) == 1
        assert result.segments[0].speaker_label is None
        assert result.segments[0].audio_events == []
        assert (result.segments[0].start_time_ms, result.segments[0].end_time_ms) == (1000, 2000)


class TestLocalTranscriptionPath:
    def test_local_path_needs_no_key_and_never_calls_openrouter(self, monkeypatch):
        service = make_transcription_service(transcription_provider="local")
        called = {}

        async def fake_local(audio_path, language):
            called["audio"] = audio_path
            return TranscriptionResult(segments=[], full_text="", provider="local", model="small")

        async def fail_openrouter(*args, **kwargs):
            raise AssertionError("OpenRouter must not be called on the local path")

        monkeypatch.setattr(service, "_transcribe_local", fake_local)
        monkeypatch.setattr(service, "_request_transcript", fail_openrouter)
        monkeypatch.setattr("os.path.isfile", lambda path: True)
        result = asyncio.run(service.transcribe_audio("/tmp/audio.wav"))
        assert result.provider == "local"
        assert called["audio"] == "/tmp/audio.wav"

    def test_missing_faster_whisper_has_fixed_message(self, monkeypatch):
        service = make_transcription_service(transcription_provider="local")
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        monkeypatch.setattr("os.path.isfile", lambda path: True)
        monkeypatch.setattr(
            service, "_audio_duration", staticmethod(lambda path: 5.0),
        )
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "faster_whisper" or name.startswith("faster_whisper."):
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(Exception) as exc:
            asyncio.run(service._transcribe_local("/tmp/audio.wav", None))
        assert getattr(exc.value, "reason", "") == "local_dependency_missing"

    def test_openrouter_legacy_still_requires_key(self, monkeypatch):
        service = make_transcription_service(transcription_provider="openrouter")
        monkeypatch.setattr("os.path.isfile", lambda path: True)
        with pytest.raises(TranscriptionProviderError):
            asyncio.run(service.transcribe_audio("/tmp/audio.wav"))


class TestOpenCodeArgs:
    def test_fixed_shape_without_auto_or_share(self):
        args = build_opencode_args("opencode", "opencode/muse-spark-1.3-contributor-free")
        assert args == [
            "opencode", "run", "--pure", "--agent", "build",
            "--format", "json", "--model", "opencode/muse-spark-1.3-contributor-free",
        ]
        assert "--auto" not in args and "--share" not in args

    def test_prompt_mentions_readonly_and_schema(self):
        prompt = build_opencode_prompt("SYS", "[0.0 - 1.0] hello.", 3, 15, 90)
        assert "read-only" in prompt.lower()
        assert "hello" in prompt
        assert "scores" in prompt


class TestExtractFinalResponse:
    def _event(self, content):
        return json.dumps({"type": "text", "part": {"text": content}})

    def test_valid_json_lines_returns_final_answer(self):
        body = json.dumps({"insights": "x", "clips": [clip(10, 40)]})
        stdout = self._event(json.dumps({"insights": "old", "clips": []})) + "\n" + self._event(body)
        assert json.loads(extract_final_response(stdout))["clips"][0]["start_time"] == 10

    def test_invalid_output_raises(self):
        with pytest.raises(OpenCodePlannerError):
            extract_final_response("just some chatter\nno json here\n")

    def test_empty_output_raises(self):
        with pytest.raises(OpenCodePlannerError):
            extract_final_response("   \n")

    def test_exit_zero_with_tool_error_raises(self):
        stdout = json.dumps({"type": "tool_error", "error": "permission denied"}) + "\n"
        with pytest.raises(OpenCodePlannerError):
            extract_final_response(stdout)


class TestRunOpencodePrompt:
    def test_missing_cli_has_install_hint(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        with pytest.raises(OpenCodePlannerError) as exc:
            asyncio.run(opencode_module.run_opencode_prompt("prompt"))
        assert str(exc.value) == OPENCODE_MISSING_MESSAGE

    def test_timeout_is_retryable(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: r"C:\tools\opencode.CMD")

        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="opencode", timeout=1)

        monkeypatch.setattr(opencode_module, "_run_opencode_sync", slow)
        with pytest.raises(OpenCodePlannerError) as exc:
            asyncio.run(opencode_module.run_opencode_prompt("prompt"))
        assert str(exc.value) == OPENCODE_TIMEOUT_MESSAGE
        assert exc.value.retryable

    def test_nonzero_exit_is_invalid(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: r"C:\tools\opencode.CMD")
        completed = SimpleNamespace(returncode=1, stdout=b"", stderr=b"boom")
        monkeypatch.setattr(opencode_module, "_run_opencode_sync", lambda *a, **k: completed)
        with pytest.raises(OpenCodePlannerError) as exc:
            asyncio.run(opencode_module.run_opencode_prompt("prompt"))
        assert str(exc.value) == OPENCODE_INVALID_MESSAGE

    def test_no_openrouter_key_leaks_to_child(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: r"C:\tools\opencode.CMD")
        seen = {}

        def fake_run(args, prompt_bytes, timeout, cwd, env):
            seen["env_has_key"] = "OPENROUTER_API_KEY" in env
            seen["config"] = env.get("OPENCODE_CONFIG")
            return SimpleNamespace(
                returncode=0,
                stdout=(json.dumps({"type": "text", "text": json.dumps({"insights": "x", "clips": []})}) + "\n").encode(),
                stderr=b"",
            )

        monkeypatch.setattr(opencode_module, "_run_opencode_sync", fake_run)
        monkeypatch.setenv("OPENROUTER_API_KEY", "secret-should-not-leak")
        monkeypatch.setenv("OPENCODE_CONFIG", "/permissive/config.json")
        asyncio.run(opencode_module.run_opencode_prompt("prompt"))
        assert seen["env_has_key"] is False
        # The inherited (possibly permissive) config is never reused.
        assert seen["config"] != "/permissive/config.json"
        assert seen["config"] and seen["config"].endswith("opencode-config.json")


class TestOpencodePlanning:
    def test_reuses_parse_finalize_for_bounds_overlap_snapping(self, monkeypatch):
        planner = make_planner(planner_provider="opencode")
        transcript = make_transcript(300)
        # Two overlapping clips and one far away: overlap must drop the weaker.
        answer = json.dumps({
            "insights": "Podcast",
            "clips": [
                clip(10, 40, (6, 6, 6, 6, 6)),
                clip(12, 42, (9, 9, 9, 9, 9)),
                clip(200, 230, (7, 7, 7, 7, 7)),
            ],
        })

        async def fake_run(prompt_text, **kwargs):
            assert "word10 end." in prompt_text
            return answer

        # _plan_via_opencode imports run_opencode_prompt from the
        # opencode_planner module, so patch it there.
        monkeypatch.setattr(opencode_module, "run_opencode_prompt", fake_run)
        result = asyncio.run(planner.plan_clips(
            transcript_result=transcript,
            video_metadata=SimpleNamespace(duration_seconds=300),
            max_clips=3, auto_clip_count=False,
            min_duration_seconds=15, max_duration_seconds=60,
        ))
        # Real overlap behavior: the 0.90 clip survives, the overlapping 0.60
        # clip is dropped, the distant 0.70 clip is kept. Upstream sentence
        # snapping moves the 12 s edge onto the word boundary at 10 s.
        assert result.api_costs.provider == "opencode"
        assert result.api_costs.model == planner.settings.opencode_model
        assert sorted(s.virality_score for s in result.segments) == [0.7, 0.9]
        by_score = sorted(result.segments, key=lambda s: s.virality_score, reverse=True)
        assert (by_score[0].start_time_ms, by_score[0].end_time_ms) == (10000, 44500)
        assert all(
            s.start_time_ms in {w.start_time_ms for seg in transcript.segments for w in seg.words}
            for s in result.segments
        )

    def test_no_transcript_fails_with_fixed_message(self):
        # Pipeline visual fallback passes sampled frames with an empty
        # transcript; OpenCode has no vision model, so it must fail fixed
        # instead of falling back to a paid provider.
        planner = make_planner(planner_provider="opencode")
        frames = [
            SimpleNamespace(timestamp_ms=i * 5000, file_path=f"f{i}.jpg", width=640, height=360)
            for i in range(4)
        ]
        with pytest.raises(Exception) as exc:
            asyncio.run(planner.plan_clips(
                transcript_result=TranscriptionResult(segments=[], full_text=""),
                video_metadata=SimpleNamespace(duration_seconds=60),
                max_clips=3, auto_clip_count=False,
                min_duration_seconds=15, max_duration_seconds=60,
                frames=frames,
            ))
        assert LOCAL_NO_TRANSCRIPT_MESSAGE in str(exc.value)

    def test_exact_model_is_used_without_substitution(self, monkeypatch):
        planner = make_planner(
            planner_provider="opencode",
            opencode_model="opencode/muse-spark-1.3-contributor-free",
        )
        seen = {}
        answer = json.dumps({"insights": "x", "clips": [clip(10, 40)]})

        async def fake_run(prompt_text, **kwargs):
            seen.update(kwargs)
            return answer

        monkeypatch.setattr(opencode_module, "run_opencode_prompt", fake_run)
        asyncio.run(planner.plan_clips(
            transcript_result=make_transcript(120),
            video_metadata=SimpleNamespace(duration_seconds=120),
            max_clips=1, auto_clip_count=False,
            min_duration_seconds=15, max_duration_seconds=60,
        ))
        assert seen["model"] == "opencode/muse-spark-1.3-contributor-free"

    def test_openrouter_legacy_option_still_calls_openrouter(self, monkeypatch):
        planner = make_planner(planner_provider="openrouter")
        planner.settings.openrouter_api_key = "test"
        called = {}

        async def fake_call(**kwargs):
            called["yes"] = True
            content = json.dumps({"insights": "x", "clips": [clip(10, 40)]})
            return (
                {"model": "m", "choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
                {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            )

        monkeypatch.setattr(planner, "_call_openrouter", fake_call)
        result = asyncio.run(planner.plan_clips(
            transcript_result=make_transcript(120),
            video_metadata=SimpleNamespace(duration_seconds=120),
            max_clips=1, auto_clip_count=False,
            min_duration_seconds=15, max_duration_seconds=60,
        ))
        assert called.get("yes") is True
        assert result.api_costs.provider == "openrouter"


class TestOpencodeHardening:
    """Coordinator-verified Windows risks: resolution, config, tool_use, stderr, model."""

    def test_resolves_bare_command_and_spawns_resolved_path(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: r"C:\tools\opencode.CMD" if name == "opencode" else None)
        seen = {}

        def fake_run(args, prompt_bytes, timeout, cwd, env):
            seen["argv0"] = args[0]
            seen["args"] = args
            return SimpleNamespace(
                returncode=0,
                stdout=(json.dumps({"type": "text", "text": json.dumps({"insights": "x", "clips": []})}) + "\n").encode(),
                stderr=b"",
            )

        monkeypatch.setattr(opencode_module, "_run_opencode_sync", fake_run)
        asyncio.run(opencode_module.run_opencode_prompt("prompt", command="opencode"))
        assert seen["argv0"] == r"C:\tools\opencode.CMD"
        assert seen["args"][:4] == [r"C:\tools\opencode.CMD", "run", "--pure", "--agent"]

    def test_sync_spawn_keeps_shell_off(self, monkeypatch):
        captured = {}

        def fake_popen(args, **kwargs):
            captured.update(kwargs)
            captured["args"] = args
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        monkeypatch.setattr(opencode_module.subprocess, "run", fake_popen)
        opencode_module._run_opencode_sync(["C:\\tools\\opencode.CMD"], b"x", 30, ".", env={})
        assert captured["shell"] is False

    def test_unresolvable_command_mocked(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        with pytest.raises(OpenCodePlannerError) as exc:
            asyncio.run(opencode_module.run_opencode_prompt("prompt", command="opencode"))
        assert str(exc.value) == OPENCODE_MISSING_MESSAGE

    def test_restrictive_config_is_ask_scoped(self, tmp_path, monkeypatch):
        # Reproduced finding: deny-all breaks the exact fork model with
        # FreeTierError 403 even tool-free, so the child config scopes
        # everything to ask (auto-rejected when non-interactive) with reads
        # allowed. No --auto/--share is ever passed (see TestOpenCodeArgs).
        from clip_engine.services.opencode_planner import (
            OPENCODE_RESTRICTIVE_CONFIG,
            build_child_env,
            write_restrictive_opencode_config,
        )

        path = write_restrictive_opencode_config(str(tmp_path))
        assert path.endswith("opencode-config.json")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert content == OPENCODE_RESTRICTIVE_CONFIG
        parsed = json.loads(content)
        assert parsed["permission"] == {"*": "ask", "read": "allow", "edit": "ask", "bash": "ask"}
        assert "deny" not in content
        monkeypatch.setenv("OPENCODE_CONFIG", "/permissive/config.json")
        monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
        env = build_child_env(path)
        assert env["OPENCODE_CONFIG"] == path
        assert "OPENROUTER_API_KEY" not in env

    def test_tool_use_error_rejected_with_exit_zero(self):
        bad = json.dumps({"type": "tool_use", "name": "edit", "state": {"status": "error"}})
        with pytest.raises(OpenCodePlannerError) as exc:
            extract_final_response(bad + "\n")
        assert str(exc.value) == OPENCODE_INVALID_MESSAGE

    def test_tool_use_rejected_or_denied_statuses_fail(self):
        # Non-interactive auto-rejections surface as rejected/denied states.
        for status in ("rejected", "denied", "Error"):
            bad = json.dumps({"type": "tool_use", "name": "bash", "state": {"status": status}})
            with pytest.raises(OpenCodePlannerError):
                extract_final_response(bad + "\n")

    def test_tool_use_error_rejected_even_with_valid_answer(self):
        good = json.dumps({"type": "text", "text": json.dumps({"insights": "x", "clips": []})})
        bad = json.dumps({"type": "tool_use", "name": "bash", "state": {"status": "error"}})
        with pytest.raises(OpenCodePlannerError):
            extract_final_response(good + "\n" + bad + "\n")

    def test_tool_use_success_does_not_block_answer(self):
        good = json.dumps({"type": "text", "text": json.dumps({"insights": "x", "clips": []})})
        ok_tool = json.dumps({"type": "tool_use", "name": "read", "state": {"status": "completed"}})
        parsed = json.loads(extract_final_response(ok_tool + "\n" + good + "\n"))
        assert parsed["clips"] == []

    def test_stderr_is_never_logged(self, monkeypatch, caplog):
        import logging

        monkeypatch.setattr("shutil.which", lambda name: r"C:\tools\opencode.CMD")
        completed = SimpleNamespace(returncode=1, stdout=b"", stderr=b"private-token-123 auth login")
        monkeypatch.setattr(opencode_module, "_run_opencode_sync", lambda *a, **k: completed)
        with caplog.at_level(logging.WARNING, logger="clip_engine.services.opencode_planner"):
            with pytest.raises(OpenCodePlannerError):
                asyncio.run(opencode_module.run_opencode_prompt("prompt"))
        assert "private-token-123" not in caplog.text

    def test_model_cmd_metachars_rejected(self):
        from clip_engine.config import is_safe_opencode_model

        assert is_safe_opencode_model("opencode/muse-spark-1.3-contributor-free")
        for bad in ("a&b", "a|b", 'a"b', "a'b", "%a%", "a!b", "a^b", "a;b", "a b", "a>b", "(a)", "`a`", "$a", "", "x" * 257):
            assert not is_safe_opencode_model(bad), bad
        with pytest.raises(OpenCodePlannerError):
            opencode_module.validate_opencode_settings("a&b", "opencode", 300)
        # Exact model passes through untouched (no substitution).
        opencode_module.validate_opencode_settings("opencode/muse-spark-1.3-contributor-free", "opencode", 300)


class TestOpencodeCostUnknown:
    """OpenCode planning cost is unknown: totals must be null, never $0."""

    def _pipeline(self):
        pipeline = AIClippingPipeline.__new__(AIClippingPipeline)
        pipeline.settings = Settings(_env_file=None)
        return pipeline

    def _local_transcription(self):
        return TranscriptionResult(
            segments=[], full_text="", provider="local", model="small",
            api_costs=TranscriptionApiCosts(
                provider="local", model="small",
                audio_duration_seconds=10.0, estimated_cost_usd=0.0,
            ),
        )

    def test_opencode_planning_cost_is_unknown(self, monkeypatch):
        planner = make_planner(planner_provider="opencode")
        answer = json.dumps({"insights": "x", "clips": [clip(10, 40)]})

        async def fake_run(prompt_text, **kwargs):
            return answer

        monkeypatch.setattr(opencode_module, "run_opencode_prompt", fake_run)
        result = asyncio.run(planner.plan_clips(
            transcript_result=make_transcript(120),
            video_metadata=SimpleNamespace(duration_seconds=120),
            max_clips=1, auto_clip_count=False,
            min_duration_seconds=15, max_duration_seconds=60,
        ))
        assert result.api_costs.provider == "opencode"
        assert result.api_costs.estimated_cost_usd is None

    def test_total_is_null_when_planning_unknown(self):
        pipeline = self._pipeline()
        plan = ClipPlanResponse(
            segments=[], total_clips=0,
            api_costs=PlanningApiCosts(provider="opencode", model="m", estimated_cost_usd=None, attempts=1),
        )
        costs = pipeline._build_api_costs(self._local_transcription(), plan, 0.0)
        # Known-free local transcription stays a numeric zero...
        assert costs["transcription"]["estimated_cost_usd"] == 0.0
        # ...while unknown CLI planning nulls the total instead of $0.
        assert costs["planning"]["estimated_cost_usd"] is None
        assert costs["total_estimated_cost_usd"] is None

    def test_total_stays_numeric_when_all_costs_known(self):
        pipeline = self._pipeline()
        transcription = TranscriptionResult(
            segments=[], full_text="", provider="openrouter", model="microsoft/mai-transcribe-2",
            api_costs=TranscriptionApiCosts(
                provider="openrouter", model="microsoft/mai-transcribe-2",
                audio_duration_seconds=10.0, estimated_cost_usd=0.01,
            ),
        )
        plan = ClipPlanResponse(
            segments=[], total_clips=0,
            api_costs=PlanningApiCosts(provider="openrouter", model="m", estimated_cost_usd=0.0123, attempts=1),
        )
        costs = pipeline._build_api_costs(transcription, plan, 0.001)
        assert costs["total_estimated_cost_usd"] == round(0.01 + 0.0123 + 0.001, 6)
        assert costs["layout_vision"]["estimated_cost_usd"] == 0.001

    def test_free_local_transcription_does_not_null_openrouter_total(self):
        pipeline = self._pipeline()
        plan = ClipPlanResponse(
            segments=[], total_clips=0,
            api_costs=PlanningApiCosts(provider="openrouter", model="m", estimated_cost_usd=0.0123, attempts=1),
        )
        costs = pipeline._build_api_costs(self._local_transcription(), plan, 0.0)
        assert costs["total_estimated_cost_usd"] == 0.0123
