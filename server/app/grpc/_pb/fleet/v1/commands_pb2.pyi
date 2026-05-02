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
    __slots__ = ("command", "args", "timeout_seconds")
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_SECONDS_FIELD_NUMBER: _ClassVar[int]
    command: str
    args: _containers.RepeatedScalarFieldContainer[str]
    timeout_seconds: int
    def __init__(self, command: _Optional[str] = ..., args: _Optional[_Iterable[str]] = ..., timeout_seconds: _Optional[int] = ...) -> None: ...

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
