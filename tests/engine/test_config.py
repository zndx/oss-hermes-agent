"""HOCON is the only config entry; lattice port is 50651."""
from __future__ import annotations

from hsengine.config import get_int, get_str, reset_config


def test_lattice_port_and_project_defaults():
    reset_config()
    assert get_int("hermes.engine.grpc.port") == 50651
    assert get_str("hermes.engine.grpc.host") == "0.0.0.0"
    assert get_int("hermes.dashboard.http.bind_port") == 9119


def test_federation_peers_default_to_gaius_then_aegir():
    reset_config()
    from hsengine.engine.federation import federation_peers

    assert federation_peers() == ["127.0.0.1:50051", "127.0.0.1:50151"]
