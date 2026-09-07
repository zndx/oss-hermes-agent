"""Outbound mix: combined agent speech preempts the clip soundtrack."""
from __future__ import annotations

import numpy as np

from hsengine.engine.webrtc_mix import SoundtrackGate, SpeechBoard, mix_pcm


def test_clip_plays_when_no_speech():
    clip = np.arange(8, dtype=np.int16)
    out = mix_pcm(clip, None)
    assert np.array_equal(out, clip)


def test_silent_speech_does_not_preempt_clip():
    clip = np.arange(8, dtype=np.int16) + 100
    out = mix_pcm(clip, np.zeros(8, dtype=np.float32))
    assert np.array_equal(out, clip)


def test_speech_replaces_clip_samples():
    clip = np.ones(8, dtype=np.int16) * 1000
    speech = np.ones(8, dtype=np.float32) * 0.5
    out = mix_pcm(clip, speech)
    assert not np.array_equal(out, clip)
    assert int(out[0]) > 10000


def test_speech_fills_stereo_clip_both_channels():
    clip = np.ones((2, 4), dtype=np.int16) * 200
    speech = np.array([0.25, 0.25, 0.25, 0.25], dtype=np.float32)
    out = mix_pcm(clip, speech)
    assert out.shape == (2, 4)
    assert int(out[0, 0]) == int(out[1, 0])
    assert int(out[0, 0]) != 200


def test_board_pull_none_when_empty():
    board = SpeechBoard()
    assert board.speaking() is False
    assert board.pull(16, 48000) is None


def test_board_serializes_sources_and_preempts():
    board = SpeechBoard()
    a = np.ones(4, dtype=np.float32) * 0.4
    b = np.ones(4, dtype=np.float32) * 0.8
    board.push(a, source="cerebras")
    board.push(b, source="other")
    assert board.speaking() is True
    first = board.pull(4, 48000)
    second = board.pull(4, 48000)
    assert first is not None and second is not None
    assert float(first.mean()) < float(second.mean())
    clip = np.zeros(4, dtype=np.int16)
    mixed = mix_pcm(clip, first)
    assert int(np.max(np.abs(mixed))) > 0
    assert board.pull(4, 48000) is None
    assert board.speaking() is False


def test_soundtrack_gate_dies_after_first_video_eof():
    gate = SoundtrackGate(has_video=True)
    assert gate.clip_live() is True
    gate.on_track_eof("audio")
    assert gate.clip_live() is True
    gate.on_track_eof("video")
    assert gate.clip_live() is False
    gate.on_track_eof("video")
    assert gate.clip_live() is False


def test_soundtrack_gate_audio_only_dies_on_audio_eof():
    gate = SoundtrackGate(has_video=False)
    gate.on_track_eof("audio")
    assert gate.clip_live() is False


def test_clip_is_silence_after_first_loop_unless_speech():
    clip = np.ones(8, dtype=np.int16) * 1000
    silent = np.zeros_like(clip)
    assert np.array_equal(mix_pcm(silent, None), silent)
    speech = np.ones(8, dtype=np.float32) * 0.5
    out = mix_pcm(silent, speech)
    assert int(out[0]) > 10000
