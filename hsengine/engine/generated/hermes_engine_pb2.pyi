from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class EngineStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class EngineStatusReply(_message.Message):
    __slots__ = ("project", "version", "capabilities")
    PROJECT_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    project: str
    version: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, project: _Optional[str] = ..., version: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ...) -> None: ...

class GetAgentInstanceRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAgentInstanceReply(_message.Message):
    __slots__ = ("healthy", "dashboard_url", "gateway_url", "detail")
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    DASHBOARD_URL_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_URL_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    healthy: bool
    dashboard_url: str
    gateway_url: str
    detail: str
    def __init__(self, healthy: bool = ..., dashboard_url: _Optional[str] = ..., gateway_url: _Optional[str] = ..., detail: _Optional[str] = ...) -> None: ...
