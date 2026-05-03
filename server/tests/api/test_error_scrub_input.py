"""Tests for scrubbing Pydantic input fields from validation errors."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel

from server.app.errors import validation_exception_handler


class StrictModel(BaseModel):
    name: str
    count: int


def test_validation_error_does_not_leak_input_secret():
    """Posting invalid body with secret in field must not echo secret in response."""
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.post("/test")
    def test_endpoint(data: StrictModel):
        return {"ok": True}

    with TestClient(app) as client:
        # Send body with validation error AND a secret in the JSON
        response = client.post(
            "/test",
            json={
                "name": "valid",
                "count": "not_an_int",  # validation error
                "secret_api_key": "sk-supersecretkey123",  # attacker injects secret
            }
        )
        assert response.status_code == 422
        # Response should not contain the secret
        assert "sk-supersecretkey123" not in response.text
        assert "supersecret" not in response.text


def test_validation_error_retains_loc_msg_type():
    """Scrubbed errors should keep loc, msg, type."""
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.post("/test")
    def test_endpoint(data: StrictModel):
        return {"ok": True}

    with TestClient(app) as client:
        response = client.post(
            "/test",
            json={
                "name": "valid",
                "count": "not_an_int",
            }
        )
        assert response.status_code == 422
        errors = response.json().get("errors", [])
        assert len(errors) > 0
        # Each error should have loc, msg, type but no input/ctx.input
        for error in errors:
            assert "loc" in error
            assert "msg" in error
            assert "type" in error
            assert "input" not in error
            assert "ctx" not in error or "input" not in error.get("ctx", {})
