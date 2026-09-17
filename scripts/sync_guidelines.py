"""
scripts/sync_guidelines.py
--------------------------
Daily cron job that syncs public-health guideline versions from an external
source against the CareSync AI knowledge base.

Workflow:
  1. Fetch version metadata from the configured external source (or mock).
  2. Load all ACTIVE documents from the `documents` table.
  3. Compare fetched versions against what is stored.
  4. Flag outdated documents as SUPERSEDED when a newer version is detected.
  5. Write a sync result summary to `system_metrics`.

Usage:
    # Run once manually
    python scripts/sync_guidelines.py

    # Typical cron entry (daily at 02:00 UTC)
    0 2 * * * cd /app && python scripts/sync_guidelines.py >> /var/log/caresync_sync.log 2>&1

Environment variables (see .env.example):
    GUIDELINES_SOURCE_URL   — data source URL, or "mock" for built-in mock
    GUIDELINES_WATCH_TITLES — comma-separated titles to watch (empty = all)
    SYNC_USER_ID            — user_id written to system_metrics (default: sync-cron)
    SUPABASE_URL            — required
    SUPABASE_KEY            — required
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap path so the script can be run from the repo root or the
# scripts/ subdirectory without needing to install the package.
# ---------------------------------------------------------------------------
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from config import GUIDELINES_SOURCE_URL, GUIDELINES_WATCH_TITLES, SYNC_USER_ID
from database.documents import fetch_all_documents, supersede_previous_versions
from database.feedback import log_metrics

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s sync_guidelines — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sync_guidelines")


# ===========================================================================
# Data source adapters
# ===========================================================================

def _fetch_from_mock() -> list[dict[str, Any]]:
    """
    Built-in mock data source simulating a public-health agency API response.

    Returns a list of guideline records with title, version, and effective_date.
    Extend or replace this with real HTTP calls when a live endpoint is available.
    """
    return [
        {
            "title":          "Vaccination Protocol",
            "version":        "v4",
            "effective_date": "2026-09-01",
            "language":       "en",
        },
        {
            "title":          "Outbreak Guidelines",
            "version":        "v3",
            "effective_date": "2026-08-20",
            "language":       "en",
        },
        {
            "title":          "Child Immunization Guidelines",
            "version":        "v2",
            "effective_date": "2026-07-15",
            "language":       "en",
        },
        {
            "title":          "Field Worker Safety Protocol",
            "version":        "v5",
            "effective_date": "2026-09-05",
            "language":       "en",
        },
    ]


def _fetch_from_url(url: str) -> list[dict[str, Any]]:
    """
    Fetches guideline version metadata from a real HTTP endpoint.

    The endpoint is expected to return a JSON array of objects, each with at
    minimum: title (str), version (str), effective_date (str "YYYY-MM-DD").

    Args:
        url: Full URL of the guidelines version feed.

    Returns:
        List of guideline dicts from the remote source.

    Raises:
        RuntimeError: If the HTTP request fails or the response is not valid JSON.
    """
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "CareSync-AI-Sync/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError(f"Expected a JSON array, got {type(data).__name__}.")
            log.info("Fetched %d guideline record(s) from %s.", len(data), url)
            return data
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch guidelines from {url!r}: {exc}") from exc


def fetch_remote_guidelines() -> list[dict[str, Any]]:
    """
    Dispatches to the correct data source adapter based on GUIDELINES_SOURCE_URL.

    Returns:
        List of guideline metadata dicts from the configured source.
    """
    source = GUIDELINES_SOURCE_URL.strip()
    if not source or source.lower() == "mock":
        log.info("Using built-in mock data source.")
        return _fetch_from_mock()

    log.info("Fetching guidelines from: %s", source)
    return _fetch_from_url(source)


# ===========================================================================
# Version comparison helpers
# ===========================================================================

def _parse_version_int(version_str: str) -> int:
    """
    Extracts the numeric part from a version string for comparison.
    e.g. "v3" → 3, "v10" → 10, "3.1" → 3, "1" → 1.
    Returns 0 if no numeric part is found.
    """
    import re
    match = re.search(r"\d+", version_str)
    return int(match.group()) if match else 0


def _is_newer(remote_version: str, stored_version: str) -> bool:
    """
    Returns True when remote_version is strictly greater than stored_version.
    Compares the leading integer component of each version string.
    """
    return _parse_version_int(remote_version) > _parse_version_int(stored_version)


# ===========================================================================
# Core sync logic
# ===========================================================================

def run_sync() -> dict[str, Any]:
    """
    Executes the full guideline sync cycle and returns a result summary dict.

    Steps:
      1. Fetch remote guideline version metadata.
      2. Load ACTIVE documents from the knowledge base.
      3. Optionally filter to the watched title list.
      4. For each remote guideline, check whether the stored version is outdated.
      5. Call supersede_previous_versions() for any outdated document.
      6. Log the result to system_metrics.

    Returns:
        Dict with keys:
            started_at      (str)  — ISO timestamp of sync start
            completed_at    (str)  — ISO timestamp of sync end
            total_ms        (float) — wall-clock time in ms
            docs_checked    (int)  — number of ACTIVE docs evaluated
            docs_superseded (int)  — number of docs flagged as SUPERSEDED
            docs_up_to_date (int)  — number of docs already on latest version
            docs_not_found  (int)  — remote titles with no matching ACTIVE doc
            errors          (int)  — number of per-document errors
            error_details   (list) — list of error message strings
            status          (str)  — "success" | "failed"
    """
    started_at = datetime.now(timezone.utc)
    t_start    = time.perf_counter()

    result: dict[str, Any] = {
        "started_at":      started_at.isoformat(),
        "completed_at":    "",
        "total_ms":        0.0,
        "docs_checked":    0,
        "docs_superseded": 0,
        "docs_up_to_date": 0,
        "docs_not_found":  0,
        "errors":          0,
        "error_details":   [],
        "status":          "success",
    }

    # ------------------------------------------------------------------
    # 1. Fetch remote guideline metadata
    # ------------------------------------------------------------------
    try:
        remote_guidelines = fetch_remote_guidelines()
    except RuntimeError as exc:
        result["status"] = "failed"
        result["error_details"].append(f"Source fetch failed: {exc}")
        result["errors"] += 1
        log.error("Source fetch failed: %s", exc)
        _finalise_result(result, t_start)
        _log_to_metrics(result)
        return result

    if not remote_guidelines:
        log.warning("Remote source returned no guidelines. Nothing to sync.")
        _finalise_result(result, t_start)
        _log_to_metrics(result)
        return result

    # ------------------------------------------------------------------
    # 2. Load ACTIVE documents from Supabase
    # ------------------------------------------------------------------
    try:
        active_docs = fetch_all_documents(status_filter="ACTIVE")
    except RuntimeError as exc:
        result["status"] = "failed"
        result["error_details"].append(f"Failed to fetch ACTIVE documents: {exc}")
        result["errors"] += 1
        log.error("Failed to fetch ACTIVE documents: %s", exc)
        _finalise_result(result, t_start)
        _log_to_metrics(result)
        return result

    # ------------------------------------------------------------------
    # 3. Build a lookup: title (lowercase) → best stored version + ids
    # ------------------------------------------------------------------
    # Multiple ACTIVE rows with the same title can exist during an upload;
    # we track the highest version stored for comparison.
    stored_index: dict[str, dict[str, Any]] = {}
    for doc in active_docs:
        title_key = doc["title"].strip().lower()
        existing  = stored_index.get(title_key)
        if existing is None or _is_newer(doc["version"], existing["version"]):
            stored_index[title_key] = doc

    # ------------------------------------------------------------------
    # 4. Apply watch-title filter
    # ------------------------------------------------------------------
    watch_set: set[str] = set()
    if GUIDELINES_WATCH_TITLES.strip():
        watch_set = {
            t.strip().lower()
            for t in GUIDELINES_WATCH_TITLES.split(",")
            if t.strip()
        }
        log.info("Watching %d specific title(s): %s", len(watch_set), watch_set)
    else:
        log.info("Watching all ACTIVE documents (%d total).", len(stored_index))

    # ------------------------------------------------------------------
    # 5. Compare each remote guideline against the stored version
    # ------------------------------------------------------------------
    for remote in remote_guidelines:
        title          = remote.get("title", "").strip()
        remote_version = remote.get("version", "").strip()

        if not title or not remote_version:
            log.warning("Skipping malformed remote record (missing title or version): %s", remote)
            continue

        title_key = title.lower()

        # Skip titles not in the watch list (when a watch list is set)
        if watch_set and title_key not in watch_set:
            continue

        result["docs_checked"] += 1

        stored_doc = stored_index.get(title_key)

        if stored_doc is None:
            log.info("No ACTIVE document found for title=%r — nothing to supersede.", title)
            result["docs_not_found"] += 1
            continue

        stored_version = stored_doc["version"].strip()

        if not _is_newer(remote_version, stored_version):
            log.info(
                "%r is up to date (stored=%s, remote=%s).",
                title, stored_version, remote_version,
            )
            result["docs_up_to_date"] += 1
            continue

        # Remote is newer — flag stored versions as SUPERSEDED
        log.info(
            "NEW VERSION detected for %r: stored=%s → remote=%s. Superseding ...",
            title, stored_version, remote_version,
        )
        try:
            # supersede_previous_versions marks everything ACTIVE except new_version.
            # Since new_version doesn't exist in the DB yet, pass remote_version so
            # ALL current ACTIVE records for this title get flagged.
            count = supersede_previous_versions(title, new_version=remote_version)
            result["docs_superseded"] += count
            log.info(
                "Superseded %d record(s) for %r (new version: %s).",
                count, title, remote_version,
            )
        except Exception as exc:
            err_msg = f"Failed to supersede '{title}': {exc}"
            result["errors"]       += 1
            result["error_details"].append(err_msg)
            log.error(err_msg)

    # ------------------------------------------------------------------
    # 6. Finalise and log
    # ------------------------------------------------------------------
    if result["errors"] > 0 and result["docs_superseded"] == 0:
        result["status"] = "failed"

    _finalise_result(result, t_start)
    _log_to_metrics(result)

    log.info(
        "Sync complete — checked=%d, superseded=%d, up_to_date=%d, "
        "not_found=%d, errors=%d, total_ms=%.1f",
        result["docs_checked"],
        result["docs_superseded"],
        result["docs_up_to_date"],
        result["docs_not_found"],
        result["errors"],
        result["total_ms"],
    )
    return result


def _finalise_result(result: dict[str, Any], t_start: float) -> None:
    """Stamps completed_at and total_ms onto the result dict."""
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    result["total_ms"]     = (time.perf_counter() - t_start) * 1000


def _log_to_metrics(result: dict[str, Any]) -> None:
    """
    Writes the sync result to system_metrics so it appears in the
    admin dashboard latency and health views.
    """
    try:
        log_metrics(
            user_id=SYNC_USER_ID or "sync-cron",
            total_ms=result["total_ms"],
            query_text=(
                f"sync_guidelines: checked={result['docs_checked']}, "
                f"superseded={result['docs_superseded']}, "
                f"errors={result['errors']}"
            ),
            status=result["status"],
            error_message=(
                "; ".join(result["error_details"])
                if result["error_details"]
                else None
            ),
        )
    except Exception as exc:
        # Never let metrics logging crash the sync run
        log.warning("Could not write sync result to system_metrics: %s", exc)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("CareSync AI — Guidelines Sync Job")
    log.info("Source : %s", GUIDELINES_SOURCE_URL or "mock")
    log.info("Watch  : %s", GUIDELINES_WATCH_TITLES or "(all titles)")
    log.info("=" * 60)

    try:
        sync_result = run_sync()
    except Exception as exc:
        log.critical("Unhandled exception during sync: %s", exc, exc_info=True)
        sys.exit(1)

    # Exit 1 on complete failure so cron/systemd can alert
    if sync_result["status"] == "failed":
        log.error("Sync finished with FAILED status.")
        sys.exit(1)

    log.info("Sync finished successfully.")
    sys.exit(0)
