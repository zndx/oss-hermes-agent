"""YK agent-rtc sentinel stamps: 1 GPU token, never nvidia.com/gpu."""
from __future__ import annotations

from hsengine.engine.yk_sentinel import QUEUE, RESOURCE_CLASS, WORKLOAD_ID, application_yaml


def test_agent_rtc_queue_uses_the_requested_leaf():
    assert QUEUE == "root.internal.inference.agent-rtc"
    assert RESOURCE_CLASS == "internal.inference.agent-rtc"
    assert WORKLOAD_ID == "hermes-agent-rtc"


def test_sentinel_yaml_claims_one_federation_gpu_token():
    raw = application_yaml()
    assert "yunikorn.apache.org/queue: root.internal.inference.agent-rtc" in raw
    assert 'federation.zndx.org/gpu: "1"' in raw
    assert "nvidia.com/gpu" not in raw
    assert "federation.project: hermes" in raw
    assert f"name: {WORKLOAD_ID}" in raw
