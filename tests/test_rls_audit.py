"""
tests/test_rls_audit.py
-----------------------
Row-Level Security (RLS) audit tests for the CareSync AI database layer.

These tests verify that the application-layer access control is correctly
enforced — i.e. that write operations (insert, update, delete) validate inputs
and raise appropriate errors before reaching the database, and that sensitive
operations are not callable without required parameters.

Note on scope:
  True Supabase RLS policies are enforced server-side in PostgreSQL and cannot
  be fully tested in unit tests without a live database. This suite covers the
  Python-layer security controls that act as a first line of defence:
    1. Input validation (empty IDs, invalid status values, etc.)
    2. Status mutation guards (only valid ENUM values accepted)
    3. Hard-delete guard (requires explicit opt-in flag)
    4. No unauthenticated writes (all mutations require a non-empty user_id)

Run:
    python -m pytest tests/test_rls_audit.py -v
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub the `supabase` package so tests run without it installed
# ---------------------------------------------------------------------------
_supabase_stub = types.ModuleType("supabase")
_supabase_stub.create_client = MagicMock()
_supabase_stub.Client = MagicMock
sys.modules.setdefault("supabase", _supabase_stub)


# ---------------------------------------------------------------------------
# documents — insert validation
# ---------------------------------------------------------------------------

class DocumentInsertSecurityTests(unittest.TestCase):
    """insert_document_record() must reject invalid or empty inputs."""

    def test_rejects_empty_title(self) -> None:
        from database.documents import insert_document_record

        with self.assertRaises(ValueError):
            insert_document_record(title="")

    def test_rejects_whitespace_only_title(self) -> None:
        from database.documents import insert_document_record

        with self.assertRaises(ValueError):
            insert_document_record(title="   ")

    def test_rejects_invalid_status(self) -> None:
        from database.documents import insert_document_record

        with self.assertRaises(ValueError):
            insert_document_record(title="Protocol", status="UNKNOWN")

    def test_accepts_all_valid_statuses(self) -> None:
        """All three valid statuses should pass validation without raising."""
        from database.documents import insert_document_record

        for status in ("ACTIVE", "SUPERSEDED", "ARCHIVED"):
            with patch("database.documents.get_supabase_client") as mock_get:
                mock_client = MagicMock()
                mock_get.return_value = mock_client
                mock_client.table.return_value.insert.return_value.execute \
                    .return_value = MagicMock(data=[{"id": "uuid-123"}])

                doc_id = insert_document_record(title="Test Protocol", status=status)
                self.assertEqual("uuid-123", doc_id)


# ---------------------------------------------------------------------------
# documents — status mutation guards
# ---------------------------------------------------------------------------

class DocumentStatusMutationTests(unittest.TestCase):
    """update_document_status() must reject empty IDs and invalid status values."""

    def test_rejects_empty_document_id(self) -> None:
        from database.documents import update_document_status

        with self.assertRaises(ValueError):
            update_document_status(document_id="", status="ACTIVE")

    def test_rejects_invalid_status_value(self) -> None:
        from database.documents import update_document_status

        with self.assertRaises(ValueError):
            update_document_status(document_id="some-uuid", status="DELETED")

    def test_rejects_sql_injection_attempt_in_status(self) -> None:
        from database.documents import update_document_status

        # SQL injection attempt should be caught by the VALID_STATUSES check
        with self.assertRaises(ValueError):
            update_document_status(
                document_id="some-uuid",
                status="ACTIVE'; DROP TABLE documents; --",
            )


# ---------------------------------------------------------------------------
# documents — hard delete guard
# ---------------------------------------------------------------------------

class DocumentHardDeleteGuardTests(unittest.TestCase):
    """delete_document() must default to soft-delete (ARCHIVED), not hard-delete."""

    @patch("database.documents.update_document_status")
    def test_default_is_soft_delete(self, mock_update: MagicMock) -> None:
        from database.documents import delete_document

        mock_update.return_value = True
        result = delete_document("some-uuid")  # hard_delete not passed → default False

        mock_update.assert_called_once_with("some-uuid", "ARCHIVED")
        self.assertTrue(result)

    @patch("database.documents.get_supabase_client")
    def test_hard_delete_requires_explicit_flag(self, mock_get: MagicMock) -> None:
        from database.documents import delete_document

        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.table.return_value.delete.return_value.eq.return_value \
            .execute.return_value = MagicMock(data=[{"id": "some-uuid"}])

        result = delete_document("some-uuid", hard_delete=True)
        # Confirm the DELETE path was actually taken
        mock_client.table.return_value.delete.assert_called_once()
        self.assertTrue(result)

    def test_hard_delete_rejects_empty_id(self) -> None:
        from database.documents import delete_document

        with self.assertRaises(ValueError):
            delete_document("", hard_delete=True)


# ---------------------------------------------------------------------------
# chunks — write validation
# ---------------------------------------------------------------------------

class ChunkInsertSecurityTests(unittest.TestCase):
    """insert_document_chunks() must reject malformed or incomplete chunk data."""

    def test_rejects_empty_list(self) -> None:
        from database.chunks import insert_document_chunks

        with self.assertRaises(ValueError):
            insert_document_chunks([])

    def test_rejects_chunk_missing_required_fields(self) -> None:
        from database.chunks import insert_document_chunks

        incomplete = {
            "document_id": "doc-001",
            # chunk_index, page_number, content, embedding all missing
        }
        with self.assertRaises(ValueError) as ctx:
            insert_document_chunks([incomplete])
        self.assertIn("missing required fields", str(ctx.exception))

    def test_rejects_wrong_embedding_dimension(self) -> None:
        from database.chunks import insert_document_chunks

        chunk = {
            "document_id": "doc-001",
            "chunk_index": 0,
            "page_number": 1,
            "content":     "test",
            "embedding":   [0.0] * 128,   # wrong — must be 384
            "metadata":    {},
        }
        with self.assertRaises(ValueError) as ctx:
            insert_document_chunks([chunk])
        self.assertIn("invalid embedding", str(ctx.exception))


# ---------------------------------------------------------------------------
# user locale — user_id requirement
# ---------------------------------------------------------------------------

class LocaleWriteSecurityTests(unittest.TestCase):
    """upsert_user_locale() must require a non-empty user_id."""

    def test_rejects_empty_user_id(self) -> None:
        from database.locale import upsert_user_locale

        with self.assertRaises(ValueError):
            upsert_user_locale(user_id="", preferred_lang="en")

    def test_rejects_unsupported_language_tag(self) -> None:
        from database.locale import upsert_user_locale

        with self.assertRaises(ValueError):
            upsert_user_locale(user_id="user-001", preferred_lang="xx")


# ---------------------------------------------------------------------------
# feedback — vote validation
# ---------------------------------------------------------------------------

class FeedbackSecurityTests(unittest.TestCase):
    """submit_feedback() must enforce valid vote values and non-empty user_id."""

    def test_rejects_empty_user_id(self) -> None:
        from database.feedback import submit_feedback

        with self.assertRaises(ValueError):
            submit_feedback(user_id="", vote="upvote")

    def test_rejects_invalid_vote_value(self) -> None:
        from database.feedback import submit_feedback

        with self.assertRaises(ValueError):
            submit_feedback(user_id="user-001", vote="neutral")

    def test_rejects_sql_injection_in_vote(self) -> None:
        from database.feedback import submit_feedback

        with self.assertRaises(ValueError):
            submit_feedback(
                user_id="user-001",
                vote="upvote'; DELETE FROM chat_feedback; --",
            )


# ---------------------------------------------------------------------------
# conversation — session and message guards
# ---------------------------------------------------------------------------

class ConversationSecurityTests(unittest.TestCase):
    """Conversation handlers must require valid session_id and role."""

    def test_add_message_rejects_empty_session_id(self) -> None:
        from database.conversation import add_chat_message

        with self.assertRaises(ValueError):
            add_chat_message(session_id="", role="user", content="hello")

    def test_add_message_rejects_empty_content(self) -> None:
        from database.conversation import add_chat_message

        with self.assertRaises(ValueError):
            add_chat_message(session_id="sess-001", role="user", content="")

    def test_add_message_rejects_invalid_role(self) -> None:
        from database.conversation import add_chat_message

        with self.assertRaises(ValueError):
            add_chat_message(session_id="sess-001", role="admin", content="hello")

    def test_delete_session_rejects_empty_id(self) -> None:
        from database.conversation import delete_chat_session

        with self.assertRaises(ValueError):
            delete_chat_session(session_id="")


if __name__ == "__main__":
    unittest.main(verbosity=2)
