"""Agent-rtc queue names and host GPU lease — no Kubernetes client."""
from __future__ import annotations

from hsengine.engine import yk_sentinel as yk


def test_agent_rtc_queue_uses_the_requested_leaf():
    assert yk.QUEUE == "root.internal.inference.agent-rtc"
    assert yk.RESOURCE_CLASS == "internal.inference.agent-rtc"
    assert yk.WORKLOAD_ID == "hermes-agent-rtc"
    assert yk.CEREBRAS_QUEUE == "root.external.token-metered"
    assert yk.GPU_TOKENS == 1


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
