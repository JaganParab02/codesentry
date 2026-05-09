"""
Tests for ZeroDataRetentionGuard — no GPU required.
"""
from __future__ import annotations

import json
import socket
import time
import pytest

from privacy.privacy_guard import ZeroDataRetentionGuard, zdr_session, _sign_certificate


# ──────────────────────────────────────────
# Certificate generation
# ──────────────────────────────────────────

class TestCertificateGeneration:
    def test_certificate_generated(self):
        """Guard must generate a certificate on exit."""
        with ZeroDataRetentionGuard("test-cert-001", enforce_network_block=False) as guard:
            cert = guard.generate_certificate()

        assert cert is not None
        assert isinstance(cert, dict)

    def test_certificate_has_required_fields(self):
        with ZeroDataRetentionGuard("test-cert-002", enforce_network_block=False) as guard:
            cert = guard.generate_certificate()

        required_fields = [
            "session_id", "timestamp", "guarantee",
            "model_endpoint", "data_wiped", "signature",
        ]
        for field in required_fields:
            assert field in cert, f"Certificate missing field: {field}"

    def test_certificate_session_id_matches(self):
        session_id = "my-unique-session-xyz"
        with ZeroDataRetentionGuard(session_id, enforce_network_block=False) as guard:
            cert = guard.generate_certificate()

        assert cert["session_id"] == session_id

    def test_certificate_data_wiped_true(self):
        with ZeroDataRetentionGuard("test-wipe-001", enforce_network_block=False) as guard:
            cert = guard.generate_certificate()

        assert cert["data_wiped"] is True

    def test_certificate_model_endpoint_is_localhost(self):
        with ZeroDataRetentionGuard("test-local-001", enforce_network_block=False) as guard:
            cert = guard.generate_certificate()

        assert "localhost" in cert["model_endpoint"]

    def test_certificate_guarantee_mentions_local(self):
        with ZeroDataRetentionGuard("test-guarantee-001", enforce_network_block=False) as guard:
            cert = guard.generate_certificate()

        guarantee = cert["guarantee"].lower()
        assert "localhost" in guarantee or "local" in guarantee

    def test_certificate_signature_is_hex_string(self):
        with ZeroDataRetentionGuard("test-sig-001", enforce_network_block=False) as guard:
            cert = guard.generate_certificate()

        signature = cert["signature"]
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA-256 hex = 64 chars

    def test_certificate_signature_is_deterministic_for_same_session(self):
        """Same payload should produce same signature."""
        payload = json.dumps(
            {"test": "data", "session_id": "sig-test"}, sort_keys=True
        )
        sig1 = _sign_certificate(payload)
        sig2 = _sign_certificate(payload)
        assert sig1 == sig2

    def test_different_sessions_have_different_signatures(self):
        with ZeroDataRetentionGuard("session-A", enforce_network_block=False) as gA:
            cert_a = gA.generate_certificate()
        with ZeroDataRetentionGuard("session-B", enforce_network_block=False) as gB:
            cert_b = gB.generate_certificate()

        assert cert_a["signature"] != cert_b["signature"]


# ──────────────────────────────────────────
# Session data wiping
# ──────────────────────────────────────────

class TestSessionDataWiping:
    def test_session_data_wiped_after_scan(self):
        """Data stored in the guard must be cleared after context exit."""
        guard = ZeroDataRetentionGuard("test-wipe-data", enforce_network_block=False)
        with guard:
            guard.store_session_data("sensitive_code", "import os; os.system('rm -rf /')")
            guard.store_session_data("api_key", "sk-secret-key")

        # After exit, internal store should be cleared
        assert len(guard._session_data) == 0, (
            "Session data was not wiped after context exit"
        )

    def test_session_data_accessible_during_context(self):
        guard = ZeroDataRetentionGuard("test-access-data", enforce_network_block=False)
        with guard:
            guard.store_session_data("key", "value")
            assert guard._session_data.get("key") == "value"


# ──────────────────────────────────────────
# Audit log
# ──────────────────────────────────────────

class TestAuditLog:
    def test_audit_log_contains_start_event(self):
        with ZeroDataRetentionGuard("test-audit-001", enforce_network_block=False) as guard:
            pass

        assert any("started" in entry.lower() for entry in guard.audit_log), (
            "Audit log should contain a session start entry"
        )

    def test_custom_events_logged(self):
        with ZeroDataRetentionGuard("test-audit-002", enforce_network_block=False) as guard:
            guard.log_event("Analysis phase 1 complete")
            guard.log_event("Analysis phase 2 complete")

        logged = " ".join(guard.audit_log)
        assert "Analysis phase 1 complete" in logged
        assert "Analysis phase 2 complete" in logged

    def test_blocked_calls_appear_in_certificate(self):
        """Any blocked external connection attempts should appear in certificate."""
        with ZeroDataRetentionGuard("test-blocked", enforce_network_block=False) as guard:
            # Manually add a fake blocked call entry
            guard.audit_log.append("BLOCKED outbound connection to example.com at 2024-01-01T00:00:00Z")
            cert = guard.generate_certificate()

        blocked = cert.get("external_calls_blocked", [])
        assert any("BLOCKED" in entry for entry in blocked)


# ──────────────────────────────────────────
# Network blocking
# ──────────────────────────────────────────

class TestNetworkBlocking:
    def test_no_external_calls_during_analysis(self):
        """
        With network enforcement ON, connecting to an external host must raise.
        """
        blocked_attempts = []

        with ZeroDataRetentionGuard("test-network-block", enforce_network_block=True) as guard:
            try:
                # Attempt to connect to an external host
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect(("8.8.8.8", 80))
                sock.close()
            except (ConnectionRefusedError, OSError) as e:
                blocked_attempts.append(str(e))

        # Should have been blocked
        assert len(blocked_attempts) > 0 or any("BLOCKED" in e for e in guard.audit_log), (
            "External connection was not blocked by ZDR guard"
        )

    def test_localhost_connections_allowed(self):
        """
        Connections to localhost must NOT be blocked (needed for vLLM).
        """
        with ZeroDataRetentionGuard("test-localhost-allow", enforce_network_block=True):
            # This should NOT raise — just fail to connect if no server is running
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                sock.connect(("127.0.0.1", 8080))
                sock.close()
            except (ConnectionRefusedError, TimeoutError, OSError):
                pass  # Expected — no server listening, but NOT blocked by ZDR
            except Exception as e:
                # Only ZDR-specific block errors should fail the test
                if "ZDR Guard" in str(e):
                    pytest.fail(f"Localhost connection was incorrectly blocked: {e}")


# ──────────────────────────────────────────
# Context manager (functional style)
# ──────────────────────────────────────────

class TestZDRSessionContextManager:
    def test_zdr_session_context_manager(self):
        with zdr_session("func-cm-test", enforce=False) as guard:
            assert guard.session_id == "func-cm-test"
            cert = guard.generate_certificate()
            assert cert["session_id"] == "func-cm-test"

    def test_zdr_session_data_wiped_on_exit(self):
        with zdr_session("func-cm-wipe", enforce=False) as guard:
            guard.store_session_data("secret", "classified")
        assert len(guard._session_data) == 0
