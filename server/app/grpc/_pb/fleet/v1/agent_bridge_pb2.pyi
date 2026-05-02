import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from fleet.v1 import envelope_pb2 as _envelope_pb2
from fleet.v1 import results_pb2 as _results_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HostMetrics(_message.Message):
    __slots__ = ("load_1", "load_5", "load_15", "mem_used_pct", "disk_used_pct", "uptime_seconds")
    LOAD_1_FIELD_NUMBER: _ClassVar[int]
    LOAD_5_FIELD_NUMBER: _ClassVar[int]
    LOAD_15_FIELD_NUMBER: _ClassVar[int]
    MEM_USED_PCT_FIELD_NUMBER: _ClassVar[int]
    DISK_USED_PCT_FIELD_NUMBER: _ClassVar[int]
    UPTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    load_1: float
    load_5: float
    load_15: float
    mem_used_pct: float
    disk_used_pct: float
    uptime_seconds: int
    def __init__(self, load_1: _Optional[float] = ..., load_5: _Optional[float] = ..., load_15: _Optional[float] = ..., mem_used_pct: _Optional[float] = ..., disk_used_pct: _Optional[float] = ..., uptime_seconds: _Optional[int] = ...) -> None: ...

class Heartbeat(_message.Message):
    __slots__ = ("host_id", "at", "last_acked_seq", "metrics", "agent_version", "signature")
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    AT_FIELD_NUMBER: _ClassVar[int]
    LAST_ACKED_SEQ_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    AGENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    at: _timestamp_pb2.Timestamp
    last_acked_seq: int
    metrics: HostMetrics
    agent_version: str
    signature: bytes
    def __init__(self, host_id: _Optional[str] = ..., at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_acked_seq: _Optional[int] = ..., metrics: _Optional[_Union[HostMetrics, _Mapping]] = ..., agent_version: _Optional[str] = ..., signature: _Optional[bytes] = ...) -> None: ...

class HeartbeatAck(_message.Message):
    __slots__ = ("server_at", "next_expected_seq")
    SERVER_AT_FIELD_NUMBER: _ClassVar[int]
    NEXT_EXPECTED_SEQ_FIELD_NUMBER: _ClassVar[int]
    server_at: _timestamp_pb2.Timestamp
    next_expected_seq: int
    def __init__(self, server_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., next_expected_seq: _Optional[int] = ...) -> None: ...

class ResumeRequest(_message.Message):
    __slots__ = ("host_id", "stream_session_id", "last_seq")
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    STREAM_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_SEQ_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    stream_session_id: str
    last_seq: int
    def __init__(self, host_id: _Optional[str] = ..., stream_session_id: _Optional[str] = ..., last_seq: _Optional[int] = ...) -> None: ...

class CapabilityRequest(_message.Message):
    __slots__ = ("host_id", "scope")
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    SCOPE_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    scope: str
    def __init__(self, host_id: _Optional[str] = ..., scope: _Optional[str] = ...) -> None: ...

class CertRotateRequest(_message.Message):
    __slots__ = ("host_id", "csr_pem")
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    CSR_PEM_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    csr_pem: bytes
    def __init__(self, host_id: _Optional[str] = ..., csr_pem: _Optional[bytes] = ...) -> None: ...

class CertIssueResponse(_message.Message):
    __slots__ = ("cert_chain_pem", "not_after")
    CERT_CHAIN_PEM_FIELD_NUMBER: _ClassVar[int]
    NOT_AFTER_FIELD_NUMBER: _ClassVar[int]
    cert_chain_pem: bytes
    not_after: _timestamp_pb2.Timestamp
    def __init__(self, cert_chain_pem: _Optional[bytes] = ..., not_after: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ManifestUpdate(_message.Message):
    __slots__ = ("manifest_signed",)
    MANIFEST_SIGNED_FIELD_NUMBER: _ClassVar[int]
    manifest_signed: bytes
    def __init__(self, manifest_signed: _Optional[bytes] = ...) -> None: ...

class Decommission(_message.Message):
    __slots__ = ("reason", "requested_by")
    REASON_FIELD_NUMBER: _ClassVar[int]
    REQUESTED_BY_FIELD_NUMBER: _ClassVar[int]
    reason: str
    requested_by: str
    def __init__(self, reason: _Optional[str] = ..., requested_by: _Optional[str] = ...) -> None: ...

class DecommissionAck(_message.Message):
    __slots__ = ("at",)
    AT_FIELD_NUMBER: _ClassVar[int]
    at: _timestamp_pb2.Timestamp
    def __init__(self, at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class AgentToServer(_message.Message):
    __slots__ = ("heartbeat", "result", "resume", "cap_req", "cert_rotate", "decom_ack")
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    RESUME_FIELD_NUMBER: _ClassVar[int]
    CAP_REQ_FIELD_NUMBER: _ClassVar[int]
    CERT_ROTATE_FIELD_NUMBER: _ClassVar[int]
    DECOM_ACK_FIELD_NUMBER: _ClassVar[int]
    heartbeat: Heartbeat
    result: _results_pb2.ResultEnvelope
    resume: ResumeRequest
    cap_req: CapabilityRequest
    cert_rotate: CertRotateRequest
    decom_ack: DecommissionAck
    def __init__(self, heartbeat: _Optional[_Union[Heartbeat, _Mapping]] = ..., result: _Optional[_Union[_results_pb2.ResultEnvelope, _Mapping]] = ..., resume: _Optional[_Union[ResumeRequest, _Mapping]] = ..., cap_req: _Optional[_Union[CapabilityRequest, _Mapping]] = ..., cert_rotate: _Optional[_Union[CertRotateRequest, _Mapping]] = ..., decom_ack: _Optional[_Union[DecommissionAck, _Mapping]] = ...) -> None: ...

class ServerToAgent(_message.Message):
    __slots__ = ("command", "hb_ack", "cert_issue", "manifest", "decom")
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    HB_ACK_FIELD_NUMBER: _ClassVar[int]
    CERT_ISSUE_FIELD_NUMBER: _ClassVar[int]
    MANIFEST_FIELD_NUMBER: _ClassVar[int]
    DECOM_FIELD_NUMBER: _ClassVar[int]
    command: _envelope_pb2.CommandEnvelope
    hb_ack: HeartbeatAck
    cert_issue: CertIssueResponse
    manifest: ManifestUpdate
    decom: Decommission
    def __init__(self, command: _Optional[_Union[_envelope_pb2.CommandEnvelope, _Mapping]] = ..., hb_ack: _Optional[_Union[HeartbeatAck, _Mapping]] = ..., cert_issue: _Optional[_Union[CertIssueResponse, _Mapping]] = ..., manifest: _Optional[_Union[ManifestUpdate, _Mapping]] = ..., decom: _Optional[_Union[Decommission, _Mapping]] = ...) -> None: ...
