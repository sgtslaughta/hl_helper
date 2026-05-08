from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PkgUpdate(_message.Message):
    __slots__ = ("classes", "dry_run")
    CLASSES_FIELD_NUMBER: _ClassVar[int]
    DRY_RUN_FIELD_NUMBER: _ClassVar[int]
    classes: _containers.RepeatedScalarFieldContainer[str]
    dry_run: bool
    def __init__(self, classes: _Optional[_Iterable[str]] = ..., dry_run: bool = ...) -> None: ...

class Reboot(_message.Message):
    __slots__ = ("delay_seconds", "reason")
    DELAY_SECONDS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    delay_seconds: int
    reason: str
    def __init__(self, delay_seconds: _Optional[int] = ..., reason: _Optional[str] = ...) -> None: ...

class ShellExec(_message.Message):
    __slots__ = ("command", "args", "timeout_seconds", "as_root", "reason")
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_SECONDS_FIELD_NUMBER: _ClassVar[int]
    AS_ROOT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    command: str
    args: _containers.RepeatedScalarFieldContainer[str]
    timeout_seconds: int
    as_root: bool
    reason: str
    def __init__(self, command: _Optional[str] = ..., args: _Optional[_Iterable[str]] = ..., timeout_seconds: _Optional[int] = ..., as_root: bool = ..., reason: _Optional[str] = ...) -> None: ...

class TerminalOpen(_message.Message):
    __slots__ = ("session_id", "cols", "rows")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    COLS_FIELD_NUMBER: _ClassVar[int]
    ROWS_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    cols: int
    rows: int
    def __init__(self, session_id: _Optional[str] = ..., cols: _Optional[int] = ..., rows: _Optional[int] = ...) -> None: ...

class FileTransfer(_message.Message):
    __slots__ = ("dir", "remote_path", "size_bytes")
    class Dir(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UPLOAD: _ClassVar[FileTransfer.Dir]
        DOWNLOAD: _ClassVar[FileTransfer.Dir]
    UPLOAD: FileTransfer.Dir
    DOWNLOAD: FileTransfer.Dir
    DIR_FIELD_NUMBER: _ClassVar[int]
    REMOTE_PATH_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    dir: FileTransfer.Dir
    remote_path: str
    size_bytes: int
    def __init__(self, dir: _Optional[_Union[FileTransfer.Dir, str]] = ..., remote_path: _Optional[str] = ..., size_bytes: _Optional[int] = ...) -> None: ...

class DockerOp(_message.Message):
    __slots__ = ("op", "container")
    OP_FIELD_NUMBER: _ClassVar[int]
    CONTAINER_FIELD_NUMBER: _ClassVar[int]
    op: str
    container: str
    def __init__(self, op: _Optional[str] = ..., container: _Optional[str] = ...) -> None: ...

class GetFacts(_message.Message):
    __slots__ = ("keys",)
    KEYS_FIELD_NUMBER: _ClassVar[int]
    keys: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, keys: _Optional[_Iterable[str]] = ...) -> None: ...

class PluginInvoke(_message.Message):
    __slots__ = ("plugin_id", "payload")
    PLUGIN_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    plugin_id: str
    payload: bytes
    def __init__(self, plugin_id: _Optional[str] = ..., payload: _Optional[bytes] = ...) -> None: ...

class AgentUpdateCmd(_message.Message):
    __slots__ = ("release_id", "manifest_json", "manifest_sig", "binary_url", "download_token", "expected_sha256", "expected_size", "force")
    RELEASE_ID_FIELD_NUMBER: _ClassVar[int]
    MANIFEST_JSON_FIELD_NUMBER: _ClassVar[int]
    MANIFEST_SIG_FIELD_NUMBER: _ClassVar[int]
    BINARY_URL_FIELD_NUMBER: _ClassVar[int]
    DOWNLOAD_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_SHA256_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_SIZE_FIELD_NUMBER: _ClassVar[int]
    FORCE_FIELD_NUMBER: _ClassVar[int]
    release_id: str
    manifest_json: bytes
    manifest_sig: bytes
    binary_url: str
    download_token: str
    expected_sha256: str
    expected_size: int
    force: bool
    def __init__(self, release_id: _Optional[str] = ..., manifest_json: _Optional[bytes] = ..., manifest_sig: _Optional[bytes] = ..., binary_url: _Optional[str] = ..., download_token: _Optional[str] = ..., expected_sha256: _Optional[str] = ..., expected_size: _Optional[int] = ..., force: bool = ...) -> None: ...

class AgentUpdateResult(_message.Message):
    __slots__ = ("from_version", "to_version", "status", "error")
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STATUS_UNSPECIFIED: _ClassVar[AgentUpdateResult.Status]
        SUCCESS: _ClassVar[AgentUpdateResult.Status]
        SIG_INVALID: _ClassVar[AgentUpdateResult.Status]
        SHA_MISMATCH: _ClassVar[AgentUpdateResult.Status]
        DOWNLOAD_FAILED: _ClassVar[AgentUpdateResult.Status]
        SWAP_FAILED: _ClassVar[AgentUpdateResult.Status]
        HEALTH_CHECK_FAILED: _ClassVar[AgentUpdateResult.Status]
        ROLLED_BACK: _ClassVar[AgentUpdateResult.Status]
    STATUS_UNSPECIFIED: AgentUpdateResult.Status
    SUCCESS: AgentUpdateResult.Status
    SIG_INVALID: AgentUpdateResult.Status
    SHA_MISMATCH: AgentUpdateResult.Status
    DOWNLOAD_FAILED: AgentUpdateResult.Status
    SWAP_FAILED: AgentUpdateResult.Status
    HEALTH_CHECK_FAILED: AgentUpdateResult.Status
    ROLLED_BACK: AgentUpdateResult.Status
    FROM_VERSION_FIELD_NUMBER: _ClassVar[int]
    TO_VERSION_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    from_version: str
    to_version: str
    status: AgentUpdateResult.Status
    error: str
    def __init__(self, from_version: _Optional[str] = ..., to_version: _Optional[str] = ..., status: _Optional[_Union[AgentUpdateResult.Status, str]] = ..., error: _Optional[str] = ...) -> None: ...
