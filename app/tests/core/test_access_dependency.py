"""
Unit tests for the care-unit scope request dependency (_get_care_unit_scope).

Verifies the key security distinction introduced after code review:
  - enforcement OFF                       → None (unrestricted)
  - ON, access CANNOT be determined       → HTTP 503 (never a silent empty deny)
  - ON, access RESOLVED but no unit group → [] (legitimate deny → empty/404)
  - ON, resolved admin / unit             → None / ["MICU"]
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import icu_step_down.backend.core._access as access_dep


def _config(enforce: bool) -> SimpleNamespace:
    return SimpleNamespace(enforce_unit_access=enforce)


def _headers(token: str | None) -> SimpleNamespace:
    tok = SimpleNamespace(get_secret_value=lambda: token) if token else None
    return SimpleNamespace(token=tok)


def _client_returning(me: object) -> type:
    class _OkClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.current_user = SimpleNamespace(me=lambda: me)

    return _OkClient


def _me(*group_displays: str) -> SimpleNamespace:
    return SimpleNamespace(groups=[SimpleNamespace(display=d) for d in group_displays])


class TestEnforcementDisabled:
    def test_off_returns_none_without_token(self) -> None:
        assert access_dep._get_care_unit_scope(_config(False), _headers(None)) is None


class TestAccessUndetermined:
    def test_on_missing_token_raises_503(self) -> None:
        with pytest.raises(HTTPException) as exc:
            access_dep._get_care_unit_scope(_config(True), _headers(None))
        assert exc.value.status_code == 503

    def test_on_resolution_failure_raises_503(self, monkeypatch) -> None:
        class _BoomClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                raise RuntimeError("SCIM Me unavailable")

        monkeypatch.setattr(access_dep, "WorkspaceClient", _BoomClient)
        with pytest.raises(HTTPException) as exc:
            access_dep._get_care_unit_scope(_config(True), _headers("tok"))
        assert exc.value.status_code == 503


class TestAccessResolved:
    def test_admin_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(
            access_dep, "WorkspaceClient", _client_returning(_me("icu_admins"))
        )
        assert access_dep._get_care_unit_scope(_config(True), _headers("tok")) is None

    def test_no_recognised_group_returns_empty_deny(self, monkeypatch) -> None:
        monkeypatch.setattr(
            access_dep, "WorkspaceClient", _client_returning(_me("other_group"))
        )
        assert access_dep._get_care_unit_scope(_config(True), _headers("tok")) == []

    def test_unit_group_returns_unit_list(self, monkeypatch) -> None:
        monkeypatch.setattr(
            access_dep, "WorkspaceClient", _client_returning(_me("icu_micu"))
        )
        assert access_dep._get_care_unit_scope(_config(True), _headers("tok")) == [
            "MICU"
        ]
