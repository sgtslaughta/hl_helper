import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from fleet.v1 import envelope_pb2 as _envelope_pb2
from fleet.v1 import results_pb2 as _results_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Disk(_message.Message):
    __slots__ = ("device", "mount", "fstype", "size_bytes")
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    MOUNT_FIELD_NUMBER: _ClassVar[int]
    FSTYPE_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    device: str
    mount: str
    fstype: str
    size_bytes: int
    def __init__(self, device: _Optional[str] = ..., mount: _Optional[str] = ..., fstype: _Optional[str] = ..., size_bytes: _Optional[int] = ...) -> None: ...

class Nic(_message.Message):
    __slots__ = ("name", "mac", "ipv4", "ipv6", "speed_mbps")
    NAME_FIELD_NUMBER: _ClassVar[int]
    MAC_FIELD_NUMBER: _ClassVar[int]
    IPV4_FIELD_NUMBER: _ClassVar[int]
    IPV6_FIELD_NUMBER: _ClassVar[int]
    SPEED_MBPS_FIELD_NUMBER: _ClassVar[int]
    name: str
    mac: str
    ipv4: _containers.RepeatedScalarFieldContainer[str]
    ipv6: _containers.RepeatedScalarFieldContainer[str]
    speed_mbps: int
    def __init__(self, name: _Optional[str] = ..., mac: _Optional[str] = ..., ipv4: _Optional[_Iterable[str]] = ..., ipv6: _Optional[_Iterable[str]] = ..., speed_mbps: _Optional[int] = ...) -> None: ...

class HostSurvey(_message.Message):
    __slots__ = ("host_id", "os", "os_version", "kernel", "arch", "virt", "cpu_model", "cpu_cores", "cpu_threads", "mem_total_bytes", "disks", "nics", "bios_vendor", "bios_version", "board_vendor", "board_product", "collected_at", "signature")
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    OS_FIELD_NUMBER: _ClassVar[int]
    OS_VERSION_FIELD_NUMBER: _ClassVar[int]
    KERNEL_FIELD_NUMBER: _ClassVar[int]
    ARCH_FIELD_NUMBER: _ClassVar[int]
    VIRT_FIELD_NUMBER: _ClassVar[int]
    CPU_MODEL_FIELD_NUMBER: _ClassVar[int]
    CPU_CORES_FIELD_NUMBER: _ClassVar[int]
    CPU_THREADS_FIELD_NUMBER: _ClassVar[int]
    MEM_TOTAL_BYTES_FIELD_NUMBER: _ClassVar[int]
    DISKS_FIELD_NUMBER: _ClassVar[int]
    NICS_FIELD_NUMBER: _ClassVar[int]
    BIOS_VENDOR_FIELD_NUMBER: _ClassVar[int]
    BIOS_VERSION_FIELD_NUMBER: _ClassVar[int]
    BOARD_VENDOR_FIELD_NUMBER: _ClassVar[int]
    BOARD_PRODUCT_FIELD_NUMBER: _ClassVar[int]
    COLLECTED_AT_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    os: str
    os_version: str
    kernel: str
    arch: str
    virt: str
    cpu_model: str
    cpu_cores: int
    cpu_threads: int
    mem_total_bytes: int
    disks: _containers.RepeatedCompositeFieldContainer[Disk]
    nics: _containers.RepeatedCompositeFieldContainer[Nic]
    bios_vendor: str
    bios_version: str
    board_vendor: str
    board_product: str
    collected_at: _timestamp_pb2.Timestamp
    signature: bytes
    def __init__(self, host_id: _Optional[str] = ..., os: _Optional[str] = ..., os_version: _Optional[str] = ..., kernel: _Optional[str] = ..., arch: _Optional[str] = ..., virt: _Optional[str] = ..., cpu_model: _Optional[str] = ..., cpu_cores: _Optional[int] = ..., cpu_threads: _Optional[int] = ..., mem_total_bytes: _Optional[int] = ..., disks: _Optional[_Iterable[_Union[Disk, _Mapping]]] = ..., nics: _Optional[_Iterable[_Union[Nic, _Mapping]]] = ..., bios_vendor: _Optional[str] = ..., bios_version: _Optional[str] = ..., board_vendor: _Optional[str] = ..., board_product: _Optional[str] = ..., collected_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., signature: _Optional[bytes] = ...) -> None: ...

class HeartbeatConfig(_message.Message):
    __slots__ = ("interval_s",)
    INTERVAL_S_FIELD_NUMBER: _ClassVar[int]
    interval_s: int
    def __init__(self, interval_s: _Optional[int] = ...) -> None: ...

class RunSurvey(_message.Message):
    __slots__ = ("reason",)
    REASON_FIELD_NUMBER: _ClassVar[int]
    reason: str
    def __init__(self, reason: _Optional[str] = ...) -> None: ...

class HostMetrics(_message.Message):
    __slots__ = ("load_1", "load_5", "load_15", "mem_used_pct", "disk_used_pct", "uptime_seconds", "net_rx_bps", "net_tx_bps")
    LOAD_1_FIELD_NUMBER: _ClassVar[int]
    LOAD_5_FIELD_NUMBER: _ClassVar[int]
    LOAD_15_FIELD_NUMBER: _ClassVar[int]
    MEM_USED_PCT_FIELD_NUMBER: _ClassVar[int]
    DISK_USED_PCT_FIELD_NUMBER: _ClassVar[int]
    UPTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    NET_RX_BPS_FIELD_NUMBER: _ClassVar[int]
    NET_TX_BPS_FIELD_NUMBER: _ClassVar[int]
    load_1: float
    load_5: float
    load_15: float
    mem_used_pct: float
    disk_used_pct: float
    uptime_seconds: int
    net_rx_bps: int
    net_tx_bps: int
    def __init__(self, load_1: _Optional[float] = ..., load_5: _Optional[float] = ..., load_15: _Optional[float] = ..., mem_used_pct: _Optional[float] = ..., disk_used_pct: _Optional[float] = ..., uptime_seconds: _Optional[int] = ..., net_rx_bps: _Optional[int] = ..., net_tx_bps: _Optional[int] = ...) -> None: ...

class Heartbeat(_message.Message):
    __slots__ = ("host_id", "at", "last_acked_seq", "metrics", "agent_version", "update_status", "update_target_version", "sleeping", "sleep_until", "signature")
    class AgentUpdateStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        AGENT_UPDATE_STATUS_UNSPECIFIED: _ClassVar[Heartbeat.AgentUpdateStatus]
        AGENT_UPDATE_STATUS_IDLE: _ClassVar[Heartbeat.AgentUpdateStatus]
        AGENT_UPDATE_STATUS_DOWNLOADING: _ClassVar[Heartbeat.AgentUpdateStatus]
        AGENT_UPDATE_STATUS_SWAPPING: _ClassVar[Heartbeat.AgentUpdateStatus]
        AGENT_UPDATE_STATUS_HEALTHCHECKING: _ClassVar[Heartbeat.AgentUpdateStatus]
        AGENT_UPDATE_STATUS_ROLLED_BACK: _ClassVar[Heartbeat.AgentUpdateStatus]
        AGENT_UPDATE_STATUS_FAILED: _ClassVar[Heartbeat.AgentUpdateStatus]
    AGENT_UPDATE_STATUS_UNSPECIFIED: Heartbeat.AgentUpdateStatus
    AGENT_UPDATE_STATUS_IDLE: Heartbeat.AgentUpdateStatus
    AGENT_UPDATE_STATUS_DOWNLOADING: Heartbeat.AgentUpdateStatus
    AGENT_UPDATE_STATUS_SWAPPING: Heartbeat.AgentUpdateStatus
    AGENT_UPDATE_STATUS_HEALTHCHECKING: Heartbeat.AgentUpdateStatus
    AGENT_UPDATE_STATUS_ROLLED_BACK: Heartbeat.AgentUpdateStatus
    AGENT_UPDATE_STATUS_FAILED: Heartbeat.AgentUpdateStatus
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    AT_FIELD_NUMBER: _ClassVar[int]
    LAST_ACKED_SEQ_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    AGENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    UPDATE_STATUS_FIELD_NUMBER: _ClassVar[int]
    UPDATE_TARGET_VERSION_FIELD_NUMBER: _ClassVar[int]
    SLEEPING_FIELD_NUMBER: _ClassVar[int]
    SLEEP_UNTIL_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    at: _timestamp_pb2.Timestamp
    last_acked_seq: int
    metrics: HostMetrics
    agent_version: str
    update_status: Heartbeat.AgentUpdateStatus
    update_target_version: str
    sleeping: bool
    sleep_until: _timestamp_pb2.Timestamp
    signature: bytes
    def __init__(self, host_id: _Optional[str] = ..., at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_acked_seq: _Optional[int] = ..., metrics: _Optional[_Union[HostMetrics, _Mapping]] = ..., agent_version: _Optional[str] = ..., update_status: _Optional[_Union[Heartbeat.AgentUpdateStatus, str]] = ..., update_target_version: _Optional[str] = ..., sleeping: bool = ..., sleep_until: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., signature: _Optional[bytes] = ...) -> None: ...

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

class AgentAuditEvent(_message.Message):
    __slots__ = ("timestamp", "task_id", "binary", "args", "elevator", "reason", "phase", "exit_code", "error")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    BINARY_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    ELEVATOR_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    EXIT_CODE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    timestamp: _timestamp_pb2.Timestamp
    task_id: str
    binary: str
    args: _containers.RepeatedScalarFieldContainer[str]
    elevator: str
    reason: str
    phase: str
    exit_code: int
    error: str
    def __init__(self, timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., task_id: _Optional[str] = ..., binary: _Optional[str] = ..., args: _Optional[_Iterable[str]] = ..., elevator: _Optional[str] = ..., reason: _Optional[str] = ..., phase: _Optional[str] = ..., exit_code: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class AgentToServer(_message.Message):
    __slots__ = ("heartbeat", "result", "resume", "cap_req", "cert_rotate", "decom_ack", "host_survey", "audit")
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    RESUME_FIELD_NUMBER: _ClassVar[int]
    CAP_REQ_FIELD_NUMBER: _ClassVar[int]
    CERT_ROTATE_FIELD_NUMBER: _ClassVar[int]
    DECOM_ACK_FIELD_NUMBER: _ClassVar[int]
    HOST_SURVEY_FIELD_NUMBER: _ClassVar[int]
    AUDIT_FIELD_NUMBER: _ClassVar[int]
    heartbeat: Heartbeat
    result: _results_pb2.ResultEnvelope
    resume: ResumeRequest
    cap_req: CapabilityRequest
    cert_rotate: CertRotateRequest
    decom_ack: DecommissionAck
    host_survey: HostSurvey
    audit: AgentAuditEvent
    def __init__(self, heartbeat: _Optional[_Union[Heartbeat, _Mapping]] = ..., result: _Optional[_Union[_results_pb2.ResultEnvelope, _Mapping]] = ..., resume: _Optional[_Union[ResumeRequest, _Mapping]] = ..., cap_req: _Optional[_Union[CapabilityRequest, _Mapping]] = ..., cert_rotate: _Optional[_Union[CertRotateRequest, _Mapping]] = ..., decom_ack: _Optional[_Union[DecommissionAck, _Mapping]] = ..., host_survey: _Optional[_Union[HostSurvey, _Mapping]] = ..., audit: _Optional[_Union[AgentAuditEvent, _Mapping]] = ...) -> None: ...

class ServerToAgent(_message.Message):
    __slots__ = ("command", "hb_ack", "cert_issue", "manifest", "decom", "hb_config", "run_survey")
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    HB_ACK_FIELD_NUMBER: _ClassVar[int]
    CERT_ISSUE_FIELD_NUMBER: _ClassVar[int]
    MANIFEST_FIELD_NUMBER: _ClassVar[int]
    DECOM_FIELD_NUMBER: _ClassVar[int]
    HB_CONFIG_FIELD_NUMBER: _ClassVar[int]
    RUN_SURVEY_FIELD_NUMBER: _ClassVar[int]
    command: _envelope_pb2.CommandEnvelope
    hb_ack: HeartbeatAck
    cert_issue: CertIssueResponse
    manifest: ManifestUpdate
    decom: Decommission
    hb_config: HeartbeatConfig
    run_survey: RunSurvey
    def __init__(self, command: _Optional[_Union[_envelope_pb2.CommandEnvelope, _Mapping]] = ..., hb_ack: _Optional[_Union[HeartbeatAck, _Mapping]] = ..., cert_issue: _Optional[_Union[CertIssueResponse, _Mapping]] = ..., manifest: _Optional[_Union[ManifestUpdate, _Mapping]] = ..., decom: _Optional[_Union[Decommission, _Mapping]] = ..., hb_config: _Optional[_Union[HeartbeatConfig, _Mapping]] = ..., run_survey: _Optional[_Union[RunSurvey, _Mapping]] = ...) -> None: ...
