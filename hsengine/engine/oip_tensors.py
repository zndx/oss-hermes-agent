"""LLM tensor profile for KServe OIP (zndx convention).

See components/signals-protocol/specification/protocol/oip_mandatory.md.
"""
from __future__ import annotations

from typing import Any

T_PROMPT = "prompt"
T_SYSTEM = "system_prompt"
T_COMPLETION = "completion"
T_REASONING = "reasoning"
T_TEXT_DELTA = "text_delta"
T_REASONING_DELTA = "reasoning_delta"
STATUS_CONSULTING = "Consulting Signals…"


def _bytes_contents(pb_mod: Any, text: str) -> Any:
    return pb_mod.InferTensorContents(bytes_contents=[(text or "").encode("utf-8")])


def extract_llm_inputs(request: Any) -> dict[str, Any]:
    """Pull prompt/system/params from a ModelInferRequest."""
    prompt = ""
    system_prompt = ""
    max_tokens = 4096
    temperature = 0.7
    capability = ""
    for tensor in request.inputs:
        name = tensor.name
        raw = b""
        if tensor.contents.bytes_contents:
            raw = tensor.contents.bytes_contents[0]
        text = raw.decode("utf-8") if raw else ""
        if name == T_PROMPT:
            prompt = text
        elif name == T_SYSTEM:
            system_prompt = text
    for key, value in request.parameters.items():
        which = value.WhichOneof("parameter_choice")
        if key == "max_tokens" and which == "int64_param":
            max_tokens = int(value.int64_param)
        elif key == "temperature" and which == "double_param":
            temperature = float(value.double_param)
        elif key == "temperature" and which == "string_param":
            try:
                temperature = float(value.string_param)
            except ValueError:
                pass
        elif key in ("capability", "model") and which == "string_param":
            if key == "capability":
                capability = value.string_param
    model_name = (request.model_name or "").strip()
    if not capability:
        capability = model_name or "agent"
    return {
        "prompt": prompt,
        "system_prompt": system_prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "capability": capability,
        "model_name": model_name or capability,
        "request_id": request.id or "",
    }


def build_infer_request(
    pb_mod: Any,
    *,
    model_name: str,
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    request_id: str = "",
    capability: str = "",
) -> Any:
    req = pb_mod.ModelInferRequest(
        model_name=model_name or "agent",
        id=request_id or "",
    )
    tin = req.inputs.add()
    tin.name = T_PROMPT
    tin.datatype = "BYTES"
    tin.shape.extend([1])
    tin.contents.CopyFrom(_bytes_contents(pb_mod, prompt))
    if system_prompt:
        sin = req.inputs.add()
        sin.name = T_SYSTEM
        sin.datatype = "BYTES"
        sin.shape.extend([1])
        sin.contents.CopyFrom(_bytes_contents(pb_mod, system_prompt))
    req.parameters["max_tokens"].int64_param = int(max_tokens)
    req.parameters["temperature"].double_param = float(temperature)
    if capability:
        req.parameters["capability"].string_param = capability
    return req


def build_infer_response(
    pb_mod: Any,
    *,
    model_name: str,
    request_id: str = "",
    completion: str = "",
    reasoning: str = "",
    text_delta: str = "",
    reasoning_delta: str = "",
    latency_ms: float = 0.0,
    finish_reason: str = "",
    peer: str = "",
) -> Any:
    resp = pb_mod.ModelInferResponse(
        model_name=model_name or "agent",
        model_version="v1",
        id=request_id or "",
    )
    if text_delta:
        out = resp.outputs.add()
        out.name = T_TEXT_DELTA
        out.datatype = "BYTES"
        out.shape.extend([1])
        out.contents.CopyFrom(_bytes_contents(pb_mod, text_delta))
    if reasoning_delta:
        out = resp.outputs.add()
        out.name = T_REASONING_DELTA
        out.datatype = "BYTES"
        out.shape.extend([1])
        out.contents.CopyFrom(_bytes_contents(pb_mod, reasoning_delta))
    if completion or (not text_delta and not reasoning_delta):
        out = resp.outputs.add()
        out.name = T_COMPLETION
        out.datatype = "BYTES"
        out.shape.extend([1])
        out.contents.CopyFrom(_bytes_contents(pb_mod, completion))
    if reasoning:
        out = resp.outputs.add()
        out.name = T_REASONING
        out.datatype = "BYTES"
        out.shape.extend([1])
        out.contents.CopyFrom(_bytes_contents(pb_mod, reasoning))
    if latency_ms:
        resp.parameters["latency_ms"].double_param = float(latency_ms)
    if finish_reason:
        resp.parameters["finish_reason"].string_param = finish_reason
    if peer:
        resp.parameters["peer"].string_param = peer
    return resp


def response_text(resp: Any) -> tuple[str, str]:
    """Return (completion, reasoning) from ModelInferResponse."""
    completion = ""
    reasoning = ""
    for out in resp.outputs:
        raw = b""
        if out.contents.bytes_contents:
            raw = out.contents.bytes_contents[0]
        text = raw.decode("utf-8") if raw else ""
        if out.name in (T_COMPLETION, T_TEXT_DELTA):
            if out.name == T_TEXT_DELTA:
                completion += text
            else:
                completion = text or completion
        elif out.name in (T_REASONING, T_REASONING_DELTA):
            if out.name == T_REASONING_DELTA:
                reasoning += text
            else:
                reasoning = text or reasoning
    return completion, reasoning
