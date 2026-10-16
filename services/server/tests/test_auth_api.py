"""Keep the existing authentication regressions active after the schema contract change."""

from legacy_workbench_fixture import (
    client,
    test_auth_required_and_expired,
    test_login_refresh_cookie_and_expired_logout,
    test_refresh_origin_and_invalid_credentials,
)

__all__ = [
    "client",
    "test_auth_required_and_expired",
    "test_login_refresh_cookie_and_expired_logout",
    "test_refresh_origin_and_invalid_credentials",
]
