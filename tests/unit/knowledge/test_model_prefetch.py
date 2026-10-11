"""Gate tests for the idle embedding-model prefetch.

The feature downloads 92 MB unattended, so every test here is an attempt to
prove it does *not* fire. The deployment it must survive silently is an
air-gapped intranet box.
"""

from __future__ import annotations

import pytest

from octop.infra.knowledge import prefetch as pf

GB = 1024**3


def _decide(**overrides):
    args = {
        "enabled": True,
        "state": "",
        "attempts": 0,
        "downloaded": False,
        "free_bytes": 20 * GB,
        "needed_bytes": 1 * GB,
        "download_busy": False,
    }
    args.update(overrides)
    return pf.decide_prefetch(**args)


class TestKillSwitch:
    def test_off_values_are_all_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for value in ("0", "false", "no", "off", "OFF"):
            monkeypatch.setenv(pf.PREFETCH_ENV, value)
            assert not pf.prefetch_enabled(), value

    def test_absent_means_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(pf.PREFETCH_ENV, raising=False)
        assert pf.prefetch_enabled()

    def test_disabled_never_runs(self) -> None:
        assert _decide(enabled=False) == pf.SKIP_DISABLED


class TestOneShot:
    def test_done_state_stops_future_boots(self) -> None:
        assert _decide(state=pf.DONE) == pf.SKIP_ALREADY_DONE

    def test_attempts_are_capped(self) -> None:
        assert _decide(attempts=pf.MAX_ATTEMPTS - 1) == pf.RUN
        assert _decide(attempts=pf.MAX_ATTEMPTS) == pf.SKIP_ATTEMPTS

    def test_a_present_model_is_recorded_not_refetched(self) -> None:
        assert _decide(downloaded=True) == pf.SKIP_PRESENT


class TestResourceGates:
    def test_existing_download_is_not_stomped(self) -> None:
        assert _decide(download_busy=True) == pf.SKIP_BUSY

    def test_disk_headroom_is_two_times(self) -> None:
        assert _decide(free_bytes=3 * GB, needed_bytes=1 * GB) == pf.RUN
        assert _decide(free_bytes=1 * GB, needed_bytes=1 * GB) == pf.SKIP_DISK
        assert _decide(free_bytes=int(1.5 * GB), needed_bytes=1 * GB) == pf.SKIP_DISK

    def test_unknown_size_does_not_block_on_disk(self) -> None:
        assert _decide(free_bytes=0, needed_bytes=0) == pf.RUN


class TestHappyPath:
    def test_everything_available_runs(self) -> None:
        assert _decide() == pf.RUN


class TestPrefetchEnabled:
    def test_default_model_is_the_recommended_smallest(self) -> None:
        from octop.infra.agents.providers.onnx_catalog import ONNX_PRESET_MODEL_IDS

        assert ONNX_PRESET_MODEL_IDS[0] == pf.DEFAULT_PREFETCH_MODEL

    def test_expected_bytes_is_positive(self) -> None:
        assert pf._expected_bytes(pf.DEFAULT_PREFETCH_MODEL) > 0

    def test_probes_every_source_before_giving_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Air-gapped is the normal case here, so "all failed" must be False."""
        seen: list[str] = []

        def _fail(url: str, timeout_s: float = 4.0) -> float:
            seen.append(url)
            raise OSError("no route to host")

        monkeypatch.setattr(pf, "probe_source", _fail)
        assert pf.sources_reachable(pf.DEFAULT_PREFETCH_MODEL) is False
        assert len(seen) >= 2, "should have tried more than one source"

    def test_first_reachable_source_is_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def _ok_for_second(url: str, timeout_s: float = 4.0) -> float:
            calls.append(url)
            if len(calls) < 2:
                raise OSError("down")
            return 0.4

        monkeypatch.setattr(pf, "probe_source", _ok_for_second)
        assert pf.sources_reachable(pf.DEFAULT_PREFETCH_MODEL) is True
