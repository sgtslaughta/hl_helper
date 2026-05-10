"""Tests for derive_exposure()."""
from __future__ import annotations




def _scan(processes=None, listeners=None, services=None, kernel_modules=None, container_exposure=None):
    """Tiny dict-shaped scan for testing — mirrors proto MessageToDict output."""
    return {
        "processes": processes or [],
        "listeners": listeners or [],
        "connections": [],
        "services": services or [],
        "kernel_modules": kernel_modules or [],
        "container_exposure": container_exposure or [],
    }


def test_derive_installed_only_when_no_runtime_evidence():
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [{"id": "CVE-1", "package": "openssl", "affected_paths": []}]
    host_packages = [{"name": "openssl", "version": "3.0.11"}]
    out = derive_exposure(_scan(), host_packages, advisories)
    assert {(d["advisory_id"], d["exposure_tier"]) for d in out} == {("CVE-1", Tier.INSTALLED_ONLY)}


def test_derive_active_when_process_running():
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [{"id": "CVE-1", "package": "nginx", "affected_paths": []}]
    host_packages = [{"name": "nginx", "version": "1.24.0"}]
    scan = _scan(
        processes=[{"pid": 1234, "exe_path": "/usr/sbin/nginx", "pkg": "nginx", "pkg_version": "1.24.0", "loaded_libs": []}],
    )
    out = derive_exposure(scan, host_packages, advisories)
    assert out[0]["exposure_tier"] == Tier.ACTIVE
    assert any("running pid 1234" in e for e in out[0]["evidence"])


def test_derive_active_when_lib_loaded():
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [
        {"id": "CVE-1", "package": "openssl", "affected_paths": ["/usr/lib/x86_64-linux-gnu/libssl.so.3"]}
    ]
    host_packages = [{"name": "openssl", "version": "3.0.11"}]
    scan = _scan(
        processes=[
            {"pid": 1234, "exe_path": "/usr/sbin/nginx", "pkg": "nginx",
             "loaded_libs": ["/usr/lib/x86_64-linux-gnu/libssl.so.3"]}
        ],
    )
    out = derive_exposure(scan, host_packages, advisories)
    assert out[0]["exposure_tier"] == Tier.ACTIVE
    assert any("loaded by /usr/sbin/nginx pid 1234" in e for e in out[0]["evidence"])


def test_derive_network_exposed_when_listener_non_loopback():
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [{"id": "CVE-1", "package": "nginx", "affected_paths": []}]
    host_packages = [{"name": "nginx", "version": "1.24.0"}]
    scan = _scan(
        processes=[{"pid": 1234, "exe_path": "/usr/sbin/nginx", "pkg": "nginx", "loaded_libs": []}],
        listeners=[{"proto": "tcp", "bind_addr": "0.0.0.0", "port": 443, "pid": 1234}],
    )
    out = derive_exposure(scan, host_packages, advisories)
    assert out[0]["exposure_tier"] == Tier.NETWORK_EXPOSED
    assert any("listening tcp/443" in e for e in out[0]["evidence"])


def test_derive_active_only_when_listener_loopback():
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [{"id": "CVE-1", "package": "redis", "affected_paths": []}]
    host_packages = [{"name": "redis", "version": "7.0"}]
    scan = _scan(
        processes=[{"pid": 1234, "exe_path": "/usr/bin/redis-server", "pkg": "redis", "loaded_libs": []}],
        listeners=[{"proto": "tcp", "bind_addr": "127.0.0.1", "port": 6379, "pid": 1234}],
    )
    out = derive_exposure(scan, host_packages, advisories)
    assert out[0]["exposure_tier"] == Tier.ACTIVE  # not NETWORK_EXPOSED
    assert any("loopback" in e for e in out[0]["evidence"])


def test_derive_service_active():
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [{"id": "CVE-1", "package": "openssh-server", "affected_paths": []}]
    host_packages = [{"name": "openssh-server", "version": "9.0"}]
    scan = _scan(
        services=[{"name": "ssh.service", "init_system": "systemd",
                   "exec_path": "/usr/sbin/sshd", "active": True, "enabled": True,
                   "pkg": "openssh-server"}],
    )
    out = derive_exposure(scan, host_packages, advisories)
    assert out[0]["exposure_tier"] == Tier.ACTIVE
    assert any("service ssh.service active" in e for e in out[0]["evidence"])


def test_derive_kmod_active():
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [{"id": "CVE-1", "package": "linux-modules-extra", "affected_paths": []}]
    host_packages = [{"name": "linux-modules-extra", "version": "6.2"}]
    scan = _scan(
        kernel_modules=[{"name": "iwlwifi", "version": "6.2", "pkg": "linux-modules-extra"}],
    )
    out = derive_exposure(scan, host_packages, advisories)
    assert out[0]["exposure_tier"] == Tier.ACTIVE
    assert any("kmod iwlwifi loaded" in e for e in out[0]["evidence"])


def test_derive_skips_advisory_for_uninstalled_package():
    from server.app.posture.exposure.derive import derive_exposure

    advisories = [{"id": "CVE-1", "package": "not-installed", "affected_paths": []}]
    host_packages = []
    out = derive_exposure(_scan(), host_packages, advisories)
    assert out == []


def test_derive_max_tier_wins():
    """If both ACTIVE and NETWORK_EXPOSED evidence exist, take NETWORK_EXPOSED."""
    from server.app.posture.exposure.derive import derive_exposure, Tier

    advisories = [{"id": "CVE-1", "package": "nginx", "affected_paths": ["/lib/libssl.so"]}]
    host_packages = [{"name": "nginx", "version": "1.24.0"}]
    scan = _scan(
        processes=[{"pid": 1, "exe_path": "/usr/sbin/nginx", "pkg": "nginx", "loaded_libs": ["/lib/libssl.so"]}],
        listeners=[{"proto": "tcp", "bind_addr": "0.0.0.0", "port": 443, "pid": 1}],
    )
    out = derive_exposure(scan, host_packages, advisories)
    assert out[0]["exposure_tier"] == Tier.NETWORK_EXPOSED
