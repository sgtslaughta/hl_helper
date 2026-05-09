"""Tests for exposure multiplier overrides via settings API."""
from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_accepts_valid_multiplier():
    from server.app.api.v1.settings import _validate_setting

    result = _validate_setting("risk.exposure_multiplier.NETWORK_EXPOSED", 3.0)
    assert result == 3.0


def test_rejects_negative_multiplier():
    from server.app.api.v1.settings import _validate_setting

    with pytest.raises(HTTPException) as exc:
        _validate_setting("risk.exposure_multiplier.ACTIVE", -0.5)
    assert exc.value.status_code == 400


def test_rejects_excessive_multiplier():
    from server.app.api.v1.settings import _validate_setting

    with pytest.raises(HTTPException) as exc:
        _validate_setting("risk.exposure_multiplier.INSTALLED_ONLY", 100.0)
    assert exc.value.status_code == 400
