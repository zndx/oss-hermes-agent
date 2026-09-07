"""Agent-rtc queue names and host GPU lease — no Kubernetes client."""
from __future__ import annotations

from hsengine.engine import yk_sentinel as yk


def test_agent_rtc_queue_uses_the_requested_leaf():
    assert yk.QUEUE == "root.internal.inference.agent-rtc"
    assert yk.RESOURCE_CLASS == "internal.inference.agent-rtc"
    assert yk.WORKLOAD_ID == "hermes-agent-rtc"
    assert yk.CEREBRAS_QUEUE == "root.external.token-metered"
    assert yk.GPU_TOKENS == 1


def test_parse_gpu_rows_prefers_emptiest():
    csv = "0, 21334\n1, 21334\n5, 4\n4, 10809\n"
    assert yk.parse_gpu_rows(csv)[0] == 5
    assert yk.parse_gpu_rows(csv) == [5, 4, 0, 1]


def test_yk_sentinel_has_no_kubernetes_client():
    for name in (
        "apply_manifest",
        "apply_sentinel",
        "apply_cerebras_thinking",
        "wait_admitted",
        "delete_sentinel",
        "_kubectl",
        "application_yaml",
        "cerebras_thinking_yaml",
        "admit",
        "release",
    ):
        assert not hasattr(yk, name), name


def test_moshi_ld_path_includes_cuda():
    from hsengine.engine.moshi_supervisor import _ld_library_path

    path = _ld_library_path(None)
    assert "/usr/local/cuda/lib64" in path
    assert "nvidia-libs" in path
