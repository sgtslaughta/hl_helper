import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PackageInventory(_message.Message):
    __slots__ = ("host_id", "at", "added", "removed", "full_snapshot")
    class Pkg(_message.Message):
        __slots__ = ("ecosystem", "name", "version", "source", "arch")
        ECOSYSTEM_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        VERSION_FIELD_NUMBER: _ClassVar[int]
        SOURCE_FIELD_NUMBER: _ClassVar[int]
        ARCH_FIELD_NUMBER: _ClassVar[int]
        ecosystem: str
        name: str
        version: str
        source: str
        arch: str
        def __init__(self, ecosystem: _Optional[str] = ..., name: _Optional[str] = ..., version: _Optional[str] = ..., source: _Optional[str] = ..., arch: _Optional[str] = ...) -> None: ...
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    AT_FIELD_NUMBER: _ClassVar[int]
    ADDED_FIELD_NUMBER: _ClassVar[int]
    REMOVED_FIELD_NUMBER: _ClassVar[int]
    FULL_SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    at: _timestamp_pb2.Timestamp
    added: _containers.RepeatedCompositeFieldContainer[PackageInventory.Pkg]
    removed: _containers.RepeatedCompositeFieldContainer[PackageInventory.Pkg]
    full_snapshot: bool
    def __init__(self, host_id: _Optional[str] = ..., at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., added: _Optional[_Iterable[_Union[PackageInventory.Pkg, _Mapping]]] = ..., removed: _Optional[_Iterable[_Union[PackageInventory.Pkg, _Mapping]]] = ..., full_snapshot: bool = ...) -> None: ...

class ContainerInventory(_message.Message):
    __slots__ = ("host_id", "at", "containers", "full_snapshot")
    class Container(_message.Message):
        __slots__ = ("id", "name", "image_ref", "image_digest", "state", "engine")
        ID_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        IMAGE_REF_FIELD_NUMBER: _ClassVar[int]
        IMAGE_DIGEST_FIELD_NUMBER: _ClassVar[int]
        STATE_FIELD_NUMBER: _ClassVar[int]
        ENGINE_FIELD_NUMBER: _ClassVar[int]
        id: str
        name: str
        image_ref: str
        image_digest: str
        state: str
        engine: str
        def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., image_ref: _Optional[str] = ..., image_digest: _Optional[str] = ..., state: _Optional[str] = ..., engine: _Optional[str] = ...) -> None: ...
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    AT_FIELD_NUMBER: _ClassVar[int]
    CONTAINERS_FIELD_NUMBER: _ClassVar[int]
    FULL_SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    at: _timestamp_pb2.Timestamp
    containers: _containers.RepeatedCompositeFieldContainer[ContainerInventory.Container]
    full_snapshot: bool
    def __init__(self, host_id: _Optional[str] = ..., at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., containers: _Optional[_Iterable[_Union[ContainerInventory.Container, _Mapping]]] = ..., full_snapshot: bool = ...) -> None: ...

class HostFacts(_message.Message):
    __slots__ = ("host_id", "at", "sshd", "sysctl", "mounts", "fs_perms")
    class SshdEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    class SysctlEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    class FsPermsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    HOST_ID_FIELD_NUMBER: _ClassVar[int]
    AT_FIELD_NUMBER: _ClassVar[int]
    SSHD_FIELD_NUMBER: _ClassVar[int]
    SYSCTL_FIELD_NUMBER: _ClassVar[int]
    MOUNTS_FIELD_NUMBER: _ClassVar[int]
    FS_PERMS_FIELD_NUMBER: _ClassVar[int]
    host_id: str
    at: _timestamp_pb2.Timestamp
    sshd: _containers.ScalarMap[str, str]
    sysctl: _containers.ScalarMap[str, str]
    mounts: _containers.RepeatedScalarFieldContainer[str]
    fs_perms: _containers.ScalarMap[str, str]
    def __init__(self, host_id: _Optional[str] = ..., at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., sshd: _Optional[_Mapping[str, str]] = ..., sysctl: _Optional[_Mapping[str, str]] = ..., mounts: _Optional[_Iterable[str]] = ..., fs_perms: _Optional[_Mapping[str, str]] = ...) -> None: ...
