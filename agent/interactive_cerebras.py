"""Cerebras overlay while AgentRTC is in force.

Implementation: ``signals-hsengine`` (``hsengine.overlay``). This module
re-exports so existing tests and the session-runtime entry point keep one
import path.
"""
from __future__ import annotations

from hsengine.overlay import overlay_runtime, session_wants_cerebras

__all__ = ["overlay_runtime", "session_wants_cerebras"]
