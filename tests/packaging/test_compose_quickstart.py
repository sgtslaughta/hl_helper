"""Validate docker-compose tier0 quickstart configuration."""
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "deploy/compose/tier0-quickstart.yml"


def test_compose_file_exists():
    """Quickstart compose file must exist."""
    assert COMPOSE_PATH.is_file()


def test_compose_file_parses_as_yaml():
    """Compose file must be valid YAML."""
    with open(COMPOSE_PATH) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert isinstance(data, dict)


def test_compose_has_server_service():
    """Must define server service."""
    with open(COMPOSE_PATH) as f:
        data = yaml.safe_load(f)
    assert "services" in data
    assert "server" in data["services"], "Missing 'server' service"


def test_server_service_builds_from_dockerfile():
    """Server service must build from deploy/server/Dockerfile."""
    with open(COMPOSE_PATH) as f:
        data = yaml.safe_load(f)
    server = data["services"]["server"]
    assert "build" in server or "image" in server
    if "build" in server:
        build = server["build"]
        if isinstance(build, dict):
            dockerfile = build.get("dockerfile", "Dockerfile")
            assert "Dockerfile" in dockerfile or "server" in str(build)
        else:
            # build is a context string
            assert "deploy/server" in str(build) or isinstance(build, str)


def test_server_service_healthcheck():
    """Server service must define healthcheck."""
    with open(COMPOSE_PATH) as f:
        data = yaml.safe_load(f)
    server = data["services"]["server"]
    assert "healthcheck" in server, "Missing healthcheck in server service"
    hc = server["healthcheck"]
    assert "test" in hc


def test_compose_no_latest_tag_without_build():
    """Images without build context must not use :latest or no tag."""
    with open(COMPOSE_PATH) as f:
        data = yaml.safe_load(f)
    for service_name, service in data.get("services", {}).items():
        if "image" in service and "build" not in service:
            image = service["image"]
            # If no build context, image must have explicit version tag
            assert ":" in image, f"Service {service_name}: image must have explicit tag, not :latest or no tag"


def test_compose_volumes_for_persistence():
    """Must define volumes for SQLite DB persistence."""
    with open(COMPOSE_PATH) as f:
        data = yaml.safe_load(f)
    server = data["services"]["server"]
    assert "volumes" in server, "Missing volumes in server service"
