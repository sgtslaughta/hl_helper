import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from fleet.v1 import commands_pb2 as _commands_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RiskLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RISK_LOW: _ClassVar[RiskLevel]
    RISK_MED: _ClassVar[RiskLevel]
    RISK_HIGH: _ClassVar[RiskLevel]
RISK_LOW: RiskLevel
RISK_MED: RiskLevel
RISK_HIGH: RiskLevel

class CapabilityToken(_message.Message):
    __slots__ = ("biscuit", "declared_scopes")
    BISCUIT_FIELD_NUMBER: _ClassVar[int]
    DECLARED_SCOPES_FIELD_NUMBER: _ClassVar[int]
    biscuit: bytes
    declared_scopes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, biscuit: _Optional[bytes] = ..., declared_scopes: _Optional[_Iterable[str]] = ...) -> None: ...

class CommandEnvelope(_message.Message):
    __slots__ = ("command_id", "host_id", "sequence", "nonce", "issued_at", "expires_at", "issued_by", "risk", "capability", "pkg_update", "reboot", "shell_exec", "terminal_open", "file_transfer", "docker_op", "get_facts", "plugin_invoke", "signature")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    NONCE_FIELD_NUMBER: _ClassVar[int]
    ISSUED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    ISSUED_BY_FIELD_NUMBER: _ClassVar[int]
    RISK_FIELD_NUMBER: _ClassVar[int]
    CAPABILITY_FIELD_NUMBER: _ClassVar[int]
    PKG_UPDATE_FIELD_NUMBER: _ClassVar[int]
    REBOOT_FIELD_NUMBER: _ClassVar[int]
    SHELL_EXEC_FIELD_NUMBER: _ClassVar[int]
    TERMINAL_OPEN_FIELD_NUMBER: _ClassVar[int]
    FILE_TRANSFER_FIELD_NUMBER: _ClassVar[int]
    DOCKER_OP_FIELD_NUMBER: _ClassVar[int]
    GET_FACTS_FIELD_NUMBER: _ClassVar[int]
    PLUGIN_INVOKE_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    host_id: str
    sequence: int
    nonce: bytes
    issued_at: _timestamp_pb2.Timestamp
    expires_at: _timestamp_pb2.Timestamp
    issued_by: str
    risk: RiskLevel
    capability: CapabilityToken
    pkg_update: _commands_pb2.PkgUpdate
    reboot: _commands_pb2.Reboot
    shell_exec: _commands_pb2.ShellExec
    terminal_open: _commands_pb2.TerminalOpen
    file_transfer: _commands_pb2.FileTransfer
    docker_op: _commands_pb2.DockerOp
    get_facts: _commands_pb2.GetFacts
    plugin_invoke: _commands_pb2.PluginInvoke
    signature: bytes
    def __init__(self, command_id: _Optional[str] = ..., host_id: _Optional[str] = ..., sequence: _Optional[int] = ..., nonce: _Optional[bytes] = ..., issued_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., issued_by: _Optional[str] = ..., risk: _Optional[_Union[RiskLevel, str]] = ..., capability: _Optional[_Union[CapabilityToken, _Mapping]] = ..., pkg_update: _Optional[_Union[_commands_pb2.PkgUpdate, _Mapping]] = ..., reboot: _Optional[_Union[_commands_pb2.Reboot, _Mapping]] = ..., shell_exec: _Optional[_Union[_commands_pb2.ShellExec, _Mapping]] = ..., terminal_open: _Optional[_Union[_commands_pb2.TerminalOpen, _Mapping]] = ..., file_transfer: _Optional[_Union[_commands_pb2.FileTransfer, _Mapping]] = ..., docker_op: _Optional[_Union[_commands_pb2.DockerOp, _Mapping]] = ..., get_facts: _Optional[_Union[_commands_pb2.GetFacts, _Mapping]] = ..., plugin_invoke: _Optional[_Union[_commands_pb2.PluginInvoke, _Mapping]] = ..., signature: _Optional[bytes] = ...) -> None: ...
