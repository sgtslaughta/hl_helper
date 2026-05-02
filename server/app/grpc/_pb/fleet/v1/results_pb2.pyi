import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ResultStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESULT_OK: _ClassVar[ResultStatus]
    RESULT_FAIL: _ClassVar[ResultStatus]
    RESULT_REJECTED: _ClassVar[ResultStatus]
    RESULT_TIMEOUT: _ClassVar[ResultStatus]
    RESULT_CAPABILITY_DENIED: _ClassVar[ResultStatus]
RESULT_OK: ResultStatus
RESULT_FAIL: ResultStatus
RESULT_REJECTED: ResultStatus
RESULT_TIMEOUT: ResultStatus
RESULT_CAPABILITY_DENIED: ResultStatus

class ResultEnvelope(_message.Message):
    __slots__ = ("command_id", "host_id", "sequence", "started_at", "completed_at", "exit_code", "stdout_chunk", "stderr_chunk", "final", "status", "rejection_reason", "prev_result_hash", "signature")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_AT_FIELD_NUMBER: _ClassVar[int]
    EXIT_CODE_FIELD_NUMBER: _ClassVar[int]
    STDOUT_CHUNK_FIELD_NUMBER: _ClassVar[int]
    STDERR_CHUNK_FIELD_NUMBER: _ClassVar[int]
    FINAL_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    REJECTION_REASON_FIELD_NUMBER: _ClassVar[int]
    PREV_RESULT_HASH_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    host_id: str
    sequence: int
    started_at: _timestamp_pb2.Timestamp
    completed_at: _timestamp_pb2.Timestamp
    exit_code: int
    stdout_chunk: bytes
    stderr_chunk: bytes
    final: bool
    status: ResultStatus
    rejection_reason: str
    prev_result_hash: bytes
    signature: bytes
    def __init__(self, command_id: _Optional[str] = ..., host_id: _Optional[str] = ..., sequence: _Optional[int] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., completed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., exit_code: _Optional[int] = ..., stdout_chunk: _Optional[bytes] = ..., stderr_chunk: _Optional[bytes] = ..., final: bool = ..., status: _Optional[_Union[ResultStatus, str]] = ..., rejection_reason: _Optional[str] = ..., prev_result_hash: _Optional[bytes] = ..., signature: _Optional[bytes] = ...) -> None: ...
