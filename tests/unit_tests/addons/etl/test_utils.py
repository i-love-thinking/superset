# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
Unit tests for addons/etl/utils.py — URL validation and SSRF protection.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _call_validate(urls: list[str], config_override: dict | None = None) -> None:
    """Call validate_source_urls inside a minimal Flask app context."""
    from flask import Flask

    app = Flask(__name__)
    overrides = {
        "ETL_ALLOWED_URL_SCHEMES": ["http", "https", "smb"],
        "ETL_ALLOW_INTERNAL_URLS": False,
        "ETL_SMB_ALLOW_INTERNAL_HOSTS": True,
    }
    if config_override:
        overrides.update(config_override)
    app.config.update(overrides)

    with app.app_context():
        from addons.etl.utils import validate_source_urls

        validate_source_urls(urls)


# ---------------------------------------------------------------------------
# Scheme tests
# ---------------------------------------------------------------------------


def test_validate_http_url_passes() -> None:
    _call_validate(["http://example.com/data.csv"])


def test_validate_https_url_passes() -> None:
    _call_validate(["https://example.com/data.csv"])


def test_validate_smb_url_passes() -> None:
    _call_validate(["smb://fileserver/share/data.csv"])


def test_validate_ftp_scheme_raises() -> None:
    with pytest.raises(ValueError, match="not in ETL_ALLOWED_URL_SCHEMES"):
        _call_validate(["ftp://example.com/data.csv"])


def test_validate_file_scheme_raises() -> None:
    with pytest.raises(ValueError, match="not in ETL_ALLOWED_URL_SCHEMES"):
        _call_validate(["file:///etc/passwd"])


def test_validate_disallowed_custom_scheme_raises() -> None:
    with pytest.raises(ValueError, match="not in ETL_ALLOWED_URL_SCHEMES"):
        _call_validate(
            ["s3://bucket/key"],
            config_override={"ETL_ALLOWED_URL_SCHEMES": ["http", "https"]},
        )


def test_validate_custom_allowed_scheme_passes() -> None:
    """Operators can extend ETL_ALLOWED_URL_SCHEMES."""
    _call_validate(
        ["s3://bucket/key"],
        config_override={"ETL_ALLOWED_URL_SCHEMES": ["http", "https", "smb", "s3"]},
    )


# ---------------------------------------------------------------------------
# Internal-host tests (HTTP)
# ---------------------------------------------------------------------------


def test_validate_localhost_http_raises_by_default() -> None:
    with pytest.raises(ValueError, match="Internal URL"):
        _call_validate(["http://localhost/data.csv"])


def test_validate_loopback_ip_raises_by_default() -> None:
    with pytest.raises(ValueError, match="Internal URL"):
        _call_validate(["http://127.0.0.1/data.csv"])


def test_validate_localhost_allowed_when_flag_set() -> None:
    _call_validate(
        ["http://localhost/data.csv"],
        config_override={"ETL_ALLOW_INTERNAL_URLS": True},
    )


def test_validate_private_ip_raises_by_default() -> None:
    """Simulate resolving to a private IP."""
    with patch("addons.etl.utils._is_private_ip", return_value=True):
        with pytest.raises(ValueError, match="Internal URL"):
            _call_validate(["http://internal-host.local/data.csv"])


def test_validate_private_ip_allowed_when_flag_set() -> None:
    with patch("addons.etl.utils._is_private_ip", return_value=True):
        _call_validate(
            ["http://internal-host.local/data.csv"],
            config_override={"ETL_ALLOW_INTERNAL_URLS": True},
        )


# ---------------------------------------------------------------------------
# SMB-specific internal-host tests
# ---------------------------------------------------------------------------


def test_validate_smb_internal_allowed_by_default() -> None:
    """SMB to internal hosts is allowed by default (ETL_SMB_ALLOW_INTERNAL_HOSTS=True)."""
    with patch("addons.etl.utils._is_private_ip", return_value=True):
        _call_validate(["smb://192.168.1.100/share/data.csv"])


def test_validate_smb_internal_blocked_when_flag_false() -> None:
    with patch("addons.etl.utils._is_private_ip", return_value=True):
        with pytest.raises(ValueError, match="ETL_SMB_ALLOW_INTERNAL_HOSTS"):
            _call_validate(
                ["smb://192.168.1.100/share/data.csv"],
                config_override={"ETL_SMB_ALLOW_INTERNAL_HOSTS": False},
            )


# ---------------------------------------------------------------------------
# Multiple URL tests
# ---------------------------------------------------------------------------


def test_validate_multiple_valid_urls_passes() -> None:
    _call_validate(
        [
            "https://example.com/a.csv",
            "smb://fileserver/share/b.csv",
        ]
    )


def test_validate_one_invalid_among_multiple_raises() -> None:
    with pytest.raises(ValueError):
        _call_validate(
            [
                "https://example.com/a.csv",
                "ftp://bad.example.com/b.csv",
            ]
        )
