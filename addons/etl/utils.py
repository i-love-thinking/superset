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
Shared utility functions for the ETL addon.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from flask import current_app

logger = logging.getLogger(__name__)

# Private IPv4 + IPv6 network ranges used for SSRF detection
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback IP address."""
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for _family, _type, _proto, _canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if any(ip in net for net in _PRIVATE_NETWORKS):
                return True
    except (socket.gaierror, ValueError):
        # Cannot resolve → allow the request to fail naturally
        pass
    return False


# SMB file shares almost always reside on internal networks, so the internal-
# host check is controlled by a separate flag rather than the generic
# ETL_ALLOW_INTERNAL_URLS one.
_SMB_SCHEMES = frozenset({"smb"})


def validate_source_urls(urls: list[str]) -> None:
    """
    Raise ValueError if any URL is not permitted by the server configuration.

    Checks performed:
    - Scheme must be in ETL_ALLOWED_URL_SCHEMES (default: http, https, smb)
    - For HTTP/HTTPS: internal/private IP addresses are blocked unless
      ETL_ALLOW_INTERNAL_URLS is True
    - For SMB: internal/private IP addresses are blocked unless
      ETL_SMB_ALLOW_INTERNAL_HOSTS is True (defaults to True because SMB
      shares are typically on internal networks)
    """
    allowed_schemes: list[str] = current_app.config.get(
        "ETL_ALLOWED_URL_SCHEMES", ["http", "https", "smb"]
    )
    allow_internal_http: bool = current_app.config.get("ETL_ALLOW_INTERNAL_URLS", False)
    allow_internal_smb: bool = current_app.config.get(
        "ETL_SMB_ALLOW_INTERNAL_HOSTS", True
    )

    for url in urls:
        parsed = urlparse(url)

        if parsed.scheme not in allowed_schemes:
            raise ValueError(
                f"URL scheme '{parsed.scheme}' is not in ETL_ALLOWED_URL_SCHEMES"
            )

        is_smb = parsed.scheme in _SMB_SCHEMES
        allow_internal = allow_internal_smb if is_smb else allow_internal_http

        if not allow_internal:
            hostname = parsed.hostname or ""
            if hostname in ("localhost", "127.0.0.1", "::1") or _is_private_ip(
                hostname
            ):
                raise ValueError(
                    f"Internal URL '{url}' is not allowed. "
                    + (
                        "Set ETL_SMB_ALLOW_INTERNAL_HOSTS=True to permit internal SMB hosts."
                        if is_smb
                        else "Set ETL_ALLOW_INTERNAL_URLS=True to permit internal hosts."
                    )
                )
