"""Models package — SQLAlchemy async models for core entities."""

from __future__ import annotations

from server.app.models._catalog_base import CatalogBase
from server.app.models.advisory import Advisory, AffectedPackage, FeedStatus
from server.app.models.agent_release import AgentRelease, ReleaseChannel, ReleaseStatus
from server.app.models.api_key import ApiKey
from server.app.models.approval import Approval
from server.app.models.audit import AuditCheckpoint, AuditEntry
from server.app.models.base import Base
from server.app.models.binding import Binding
from server.app.models.bootstrap_token import BootstrapToken
from server.app.models.command import Command
from server.app.models.enrollment_token import EnrollmentToken
from server.app.models.group import Group
from server.app.models.group_membership import GroupMembership
from server.app.models.host import Host
from server.app.models.host_advisory import HostAdvisory
from server.app.models.host_advisory_exposure import HostAdvisoryExposure
from server.app.models.host_container import HostContainer
from server.app.models.host_package import HostPackage
from server.app.models.host_risk import HostRisk
from server.app.models.host_sequence import HostSequence
from server.app.models.lockout import LockoutRecord
from server.app.models.maintenance_window import MaintenanceWindow
from server.app.models.notification import Notification
from server.app.models.oidc_account_link import OidcAccountLink
from server.app.models.oidc_provider import OidcProvider
from server.app.models.plugin import Plugin
from server.app.models.recovery_code import RecoveryCode
from server.app.models.result import Result
from server.app.models.revoked_cert import RevokedCert
from server.app.models.role import Role
from server.app.models.schedule import Schedule
from server.app.models.service_account import ServiceAccount
from server.app.models.session import Session
from server.app.models.setting import Setting
from server.app.models.task import Task
from server.app.models.task_run import TaskRun
from server.app.models.totp_secret import TotpSecret
from server.app.models.update_policy import UpdatePolicy
from server.app.models.user import User
from server.app.models.user_group import UserGroup
from server.app.models.webauthn_credential import WebAuthnCredential
from server.app.models.webhook import Webhook
from server.app.posture.model import PostureFindingRow

__all__ = [
    "CatalogBase",
    "Advisory",
    "AffectedPackage",
    "FeedStatus",
    "AgentRelease",
    "ReleaseChannel",
    "ReleaseStatus",
    "Base",
    "Host",
    "HostSequence",
    "HostAdvisory",
    "HostAdvisoryExposure",
    "HostContainer",
    "HostPackage",
    "HostRisk",
    "EnrollmentToken",
    "Command",
    "Result",
    "AuditEntry",
    "AuditCheckpoint",
    "RevokedCert",
    "Group",
    "GroupMembership",
    "User",
    "UserGroup",
    "ApiKey",
    "ServiceAccount",
    "Role",
    "Binding",
    "Session",
    "BootstrapToken",
    "Task",
    "TaskRun",
    "Schedule",
    "MaintenanceWindow",
    "UpdatePolicy",
    "Approval",
    "Notification",
    "Plugin",
    "Webhook",
    "Setting",
    "LockoutRecord",
    "RecoveryCode",
    "TotpSecret",
    "WebAuthnCredential",
    "OidcProvider",
    "OidcAccountLink",
    "PostureFindingRow",
]
