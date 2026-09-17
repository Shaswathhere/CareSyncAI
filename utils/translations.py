"""
utils/translations.py
----------------------
The UI string catalog, one dict per supported language.

`en` is the source of truth: every key that exists anywhere must exist here,
because utils/i18n.py falls back to the English string whenever a translation
is missing. That makes a partially translated language render as mixed text
rather than crashing or showing raw keys.

Placeholders use str.format() syntax ({title}, {count}, …). A translation must
keep every placeholder its English counterpart uses; i18n.t() falls back to
English if a translation's placeholders don't match the arguments given.

Adding a language:
    1. Add its code and native display name to LANGUAGES below.
    2. Add a dict of the same keys to TRANSLATIONS. Partial is fine.

Language codes are BCP-47 tags, deliberately a subset of the registries the
rest of the app already uses — database.locale.SUPPORTED_LANGUAGES and
rag.translator.LANGUAGE_NAMES — so a UI language always has a matching
translation and document-locale path. Only the display names differ: those
modules hold English names ("Tamil"), the picker shows native ones ("தமிழ்").
Do not add a UI language that is missing from those two registries.

Note on scope: this catalog covers interface chrome only. Guidance documents,
retrieved passages, and generated answers are handled by rag/translator.py,
and the downloadable summary export stays English — PyMuPDF's base-14 fonts
cannot render Devanagari or Tamil script.
"""

from __future__ import annotations

from typing import Dict

# Language code -> native display name, in the order they appear in the picker.
LANGUAGES: Dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी",
    "ta": "தமிழ்",
    "es": "Español",
}

DEFAULT_LANGUAGE = "en"


_EN: Dict[str, str] = {
    # ── App shell ────────────────────────────────────────────────────────────
    "app.page_title": "CareSync AI — Ask. Verify. Act.",
    "app.title": "CareSync AI — Ask. Verify. Act.",
    "app.tagline": "AI-powered public-health guidance assistant for field workers",
    "app.sidebar_title": "CareSync AI",
    "app.sidebar_caption": "Sprint 2 MVP",
    "app.sidebar_about": (
        "Retrieval-Augmented Generation for public-health field workers.\n\n"
        "Every answer is grounded in official, versioned guidance documents "
        "and backed by citations."
    ),
    "app.tab.chat": "💬 Chat Assistant",
    "app.tab.documents": "📄 Uploaded Documents",
    "app.tab.upload": "⬆️ Upload Guideline",

    # ── Language picker ──────────────────────────────────────────────────────
    "lang.heading": "🌐 Language",
    "lang.label": "Interface language",
    "lang.help": "Changes the labels, buttons, and messages across the whole app.",
    "lang.note": (
        "Interface language only — guidance documents, retrieved passages, and "
        "answers stay in their source language."
    ),

    # ── Document statuses ────────────────────────────────────────────────────
    "status.ACTIVE": "ACTIVE",
    "status.SUPERSEDED": "SUPERSEDED",
    "status.ARCHIVED": "ARCHIVED",
    "status.any": "All statuses",
    "status.hint.ACTIVE": "Current guidance — safe to act on.",
    "status.hint.SUPERSEDED": "A newer version of this document exists — verify before acting.",
    "status.hint.ARCHIVED": "Withdrawn from active guidance — retained for audit only.",

    # ── Sidebar search filters ───────────────────────────────────────────────
    "filters.heading": "🔍 Search Filters",
    "filters.title_label": "Document title contains",
    "filters.title_placeholder": "e.g. Vaccination",
    "filters.title_help": "Filters the Uploaded Documents tab.",
    "filters.status_label": "Document status",
    "filters.status_help": "Chat retrieval always answers from ACTIVE guidance when 'All statuses' is selected.",
    "filters.use_dates": "Filter by effective date",
    "filters.date_label": "Effective date range",
    "filters.date_help": "Inclusive lower and upper bounds on a document's effective date.",
    "filters.date_order_warning": "Start date is after end date — showing no results.",
    "filters.keyword_label": "Keyword boost (optional)",
    "filters.keyword_placeholder": "e.g. measles dosage",
    "filters.keyword_help": "Passed to the hybrid retriever as an explicit full-text keyword.",
    "filters.reset": "Reset filters",

    # ── Documents tab ────────────────────────────────────────────────────────
    "docs.heading": "📄 Uploaded Public-Health Documents",
    "docs.empty": "No documents have been uploaded yet. Use the **Upload Guideline** tab to add one.",
    "docs.session_notice": "⚠️ Showing session data — Supabase is not reachable, so status edits won't persist.",
    "docs.showing": "Showing **{visible}** of **{total}** documents · {active} active — filter them in the sidebar.",
    "docs.no_match": "No documents match the current sidebar filters. Try widening the date range or status.",
    "docs.version_effective": "Version {version} · Effective {effective}",
    "docs.set_status": "Set status",
    "docs.apply": "Apply",
    "docs.apply_help": "Move this document to the selected status.",
    "docs.delete": "🗑️ Delete",
    "docs.delete_help": "Archive or permanently remove this document.",
    "docs.timeline": "🕓 Version timeline — {title}",
    "docs.status_changed": "'{title}' is now {status}.",
    "docs.status_session_only": (
        "'{title}' set to {status} for this session only — "
        "connect Supabase to persist status changes."
    ),
    "docs.status_failed": "Could not update '{title}': {error}",
    "docs.status_missing": "No document found with id {id} — it may have been deleted.",

    # ── Version timeline ─────────────────────────────────────────────────────
    "timeline.empty": "No version history is available for this document yet.",
    "timeline.this_row": "this row",
    "timeline.effective": "Effective {date}",
    "timeline.superseded_note": " · replaced by a later version",

    # ── Delete confirmation modal ────────────────────────────────────────────
    "delete.modal_title": "Remove this document?",
    "delete.inline_title": "🗑️ Remove this document?",
    "delete.mode_question": "How should this document be removed?",
    "delete.mode.archive": "Archive it (recoverable)",
    "delete.mode.permanent": "Delete permanently",
    "delete.mode.archive_caption": (
        "Keeps the record and its citations for audit, but retrieval stops answering from it."
    ),
    "delete.mode.permanent_caption": (
        "Erases the document and its indexed passages. This cannot be undone."
    ),
    "delete.permanent_warning": (
        "Permanent deletion also removes every indexed passage of this document, "
        "so past answers can no longer be traced back to it."
    ),
    "delete.ack": "I understand this cannot be undone.",
    "delete.session_notice": "Supabase is not reachable, so this only affects the current session.",
    "delete.cancel": "Cancel",
    "delete.confirm_archive": "Archive document",
    "delete.confirm_permanent": "Delete permanently",
    "delete.done_archived": "'{title}' was archived.",
    "delete.done_deleted": "'{title}' was permanently deleted.",
    "delete.session_archived": (
        "'{title}' was archived for this session only — connect Supabase to persist deletions."
    ),
    "delete.session_deleted": (
        "'{title}' was permanently deleted for this session only — "
        "connect Supabase to persist deletions."
    ),
    "delete.failed": "Could not delete '{title}': {error}",
    "delete.not_found": "No document found with id {id} — it may already have been deleted.",

    # ── Chat assistant ───────────────────────────────────────────────────────
    "chat.heading": "💬 Ask Public Health Guidance",
    "chat.welcome": (
        "Hello! I am **CareSync AI**, your public-health guidance assistant. "
        "Ask me questions about active outbreak protocols, vaccination guidelines, "
        "or health advisories."
    ),
    "chat.input_placeholder": "What is the current vaccination protocol?",
    "chat.spinner": "Searching active public-health guidance...",
    "chat.searching": "🔍 Searching {filters} — change these in the sidebar.",
    "chat.filter_status": "status **{status}**",
    "chat.filter_status_any": "status **ACTIVE** (chat always answers from active guidance)",
    "chat.filter_dates": "effective **{date_from} → {date_to}**",
    "chat.filter_keyword": "keyword **{keyword}**",
    "chat.sources": "📌 **Sources & Citations** ({count})",
    "chat.sources_stale": " — {count} from non-active guidance",
    "chat.sources_scored": " · ranked by relevance to your question",
    "chat.citation_meta": "Page {page} · Version {version} · Effective {effective}",
    "chat.passage_preview": "🔍 Passage preview — {title}, page {page}",
    "chat.highlight_note": "Highlighted terms come from your question.",

    # ── Prompt chips ─────────────────────────────────────────────────────────
    "chat.chips_intro": "✨ Not sure where to start? Try one of these:",
    "chat.prompt.1": "What is the current measles vaccination schedule?",
    "chat.prompt.2": "How do I report a suspected outbreak?",
    "chat.prompt.3": "What PPE is required for a household visit?",
    "chat.prompt.4": "Has the cholera treatment guidance changed?",

    # ── Answer actions ───────────────────────────────────────────────────────
    "chat.copy": "📋 Copy",
    "chat.copy_hint": "Hover the box and click the copy icon to copy the answer.",
    "chat.export_pdf": "📄 PDF",
    "chat.export_pdf_help": "Download this answer and its citations as a PDF summary.",
    "chat.export_pdf_unavailable": "PDF export needs PyMuPDF — install it with `pip install pymupdf`.",
    "chat.export_txt": "⬇️ TXT",
    "chat.export_txt_help": "Download this answer and its citations as plain text.",
    "chat.export_note": "Downloads are in English — they mirror the source guidance documents.",

    # ── Conflict banners ─────────────────────────────────────────────────────
    "conflict.title_warning": "Conflicting guidance detected",
    "conflict.title_danger": "Conflicting guidance across document versions",
    "conflict.footer": (
        "Cross-check the citations below against the most recent ACTIVE guidance "
        "before acting on this answer."
    ),
    "conflict.fallback": "Retrieved documents give differing guidance.",

    # ── Upload tab ───────────────────────────────────────────────────────────
    "upload.heading": "⬆️ Upload Approved Guidance PDF",
    "upload.caption": "Drag and drop a PDF below, or click to browse. Approved guidance only.",
    "upload.title_label": "Document Title",
    "upload.title_placeholder": "e.g., Child Immunization Guideline",
    "upload.version_label": "Version",
    "upload.date_label": "Effective Date",
    "upload.file_label": "Drop PDF file here, or click to browse",
    "upload.file_help": "Only PDF documents are supported in this MVP.",
    "upload.submit": "Upload & Index Guidance",
    "upload.processing": "Processing '{title}'... extracting text, chunking & generating embeddings.",
    "upload.indexing": "Indexing '{title}' into the knowledge base...",
    "upload.success": (
        "'{title}' ({filename}) processed and added to the knowledge base — "
        "**{pages} pages**, **{chunks} chunks** indexed."
    ),
    "upload.failed": "Failed to process '{title}': {error}",
    "upload.missing_fields": "Please fill in the document title and select a PDF file.",
    # ── Chat history drawer ──────────────────────────────────────────────────
    "history.heading": "🕓 Chat History",
    "history.new_chat": "➕ New Chat",
    "history.new_chat_help": "Start a fresh conversation. The current one stays saved.",
    "history.recent": "Recent conversations ({count})",
    "history.empty": "No saved conversations yet — ask a question and this chat will appear here.",
    "history.unavailable": (
        "Chat history is unavailable right now — this conversation is kept on "
        "this device only and will be lost when the page is closed."
    ),
    "history.untitled": "Untitled chat",
    "history.open_help": "Open this conversation — last active {when}.",
    "history.rename_help": "Rename this conversation",
    "history.rename_label": "Conversation title",
    "history.rename_save": "Save",
    "history.rename_cancel": "Cancel",
    "history.renamed": "Renamed to '{title}'.",
    "history.rename_failed": "Could not rename '{title}'.",
    "history.delete_help": "Delete this conversation",
    "history.deleted": "'{title}' was deleted.",
    "history.delete_failed": "Could not delete '{title}'.",
    "history.delete_missing": "That conversation no longer exists.",
    "history.just_now": "just now",
    "history.minutes_ago": "{count} min ago",
    "history.hours_ago": "{count} h ago",
    "history.days_ago": "{count} d ago",

    # ── Answer feedback ──────────────────────────────────────────────────────
    "feedback.prompt": "Was this answer helpful?",
    "feedback.up_help": "This answer was accurate and useful.",
    "feedback.down_help": "This answer was wrong, incomplete, or unhelpful.",
    "feedback.thanks_up": "✅ Thanks — logged as helpful.",
    "feedback.thanks_down": "Thanks — logged for review by the guidance team.",
    "feedback.thanks_down_comment": "Thanks — your note went to the guidance team.",
    "feedback.not_saved": "⚠️ Recorded on this device only — the feedback service is unreachable.",
    "feedback.comment_label": "What was wrong with this answer? (optional)",
    "feedback.comment_placeholder": "e.g. cited a superseded protocol, missed the dosage table",
    "feedback.comment_send": "Send",
    "feedback.comment_skip": "Skip",

    # ── Voice input ──────────────────────────────────────────────────────────
    "voice.heading": "🎙️ Ask by voice",
    "voice.intro": "Record your question, play it back, then check the transcript before it is asked.",
    "voice.record_label": "Record your question",
    "voice.record_help": "Tap the microphone to start recording, and again to stop.",
    "voice.recorder_unsupported": (
        "This Streamlit build has no microphone recorder — upload an audio clip "
        "instead, or upgrade to Streamlit 1.41 or newer."
    ),
    "voice.upload_label": "Upload an audio question",
    "voice.upload_help": "WAV, MP3, M4A, OGG, WEBM, or FLAC.",
    "voice.too_large": "That recording is over {limit} MB — record a shorter question.",
    "voice.transcribe": "✍️ Transcribe",
    "voice.transcribe_help": "Convert the recording to text before it is asked.",
    "voice.transcribing": "Transcribing your recording...",
    "voice.transcript_caption": "Transcribed in {seconds}s — check it before asking.",
    "voice.transcript_label": "Transcript",
    "voice.transcript_help": "Correct anything speech-to-text got wrong, then ask.",
    "voice.ask": "Ask this question",
    "voice.discard": "Discard",
    "voice.empty_transcript": "No speech was detected in that recording — try again, closer to the microphone.",
    "voice.failed": "Could not transcribe that recording: {error}",

    # ── Retrieval confidence ─────────────────────────────────────────────────
    "confidence.high": "High relevance",
    "confidence.medium": "Moderate relevance",
    "confidence.low": "Low relevance",
    "confidence.badge": "{percent}%",
    "confidence.help": (
        "{label} — the reranker scored this passage {percent}% relevant to your "
        "question (model score {score})."
    ),
    "confidence.detail": "Reranked #{rank} · {label} ({percent}%)",
    # ── Admin analytics dashboard ──────────────────────────────────
    "app.tab.analytics": "📊 Analytics",
    "analytics.heading": "📊 Admin Analytics Dashboard",
    "analytics.caption": "Operational health of the retrieval pipeline, and how useful field workers found its answers.",
    "analytics.window_label": "Time window",
    "analytics.window.1": "Last hour",
    "analytics.window.6": "Last 6 hours",
    "analytics.window.24": "Last 24 hours",
    "analytics.window.168": "Last 7 days",
    "analytics.window.720": "Last 30 days",
    "analytics.window_note": "All four figures cover {window}.",
    "analytics.refresh": "🔄 Refresh",
    "analytics.refresh_help": "Discard the cached figures and re-read the metrics tables.",
    "analytics.no_data": "No queries have been recorded in this window yet.",
    "analytics.unavailable": "Metrics are unavailable right now — {error}",
    "analytics.unavailable_hint": "The RAG pipeline writes these figures to Supabase as it runs. Check the connection, then refresh.",
    "analytics.source_note": "Reading from {module}. Figures are cached for {seconds}s.",
    "analytics.millis": "{value} ms",
    "analytics.seconds": "{value} s",
    "analytics.table.show": "Show data table",
    "analytics.kpi.queries": "Queries answered",
    "analytics.kpi.queries_sub": "{rate} per hour",
    "analytics.kpi.queries_help": "Every RAG pipeline run recorded in this window, successful or not.",
    "analytics.kpi.latency": "Average response",
    "analytics.kpi.latency_sub": "p95 {p95} · slowest {max}",
    "analytics.kpi.latency_help": "End-to-end wall-clock time from question to grounded answer.",
    "analytics.kpi.success": "Success rate",
    "analytics.kpi.success_sub": "{failed} failed or timed out",
    "analytics.kpi.success_help": "Share of queries that returned an answer without erroring or timing out.",
    "analytics.kpi.helpful": "Helpful answers",
    "analytics.kpi.helpful_sub": "👍 {up} · 👎 {down}",
    "analytics.kpi.helpful_help": "Share of rated answers a field worker marked helpful.",
    "analytics.kpi.none": "—",
    "analytics.breakdown.heading": "Where the time goes",
    "analytics.breakdown.caption": "Average milliseconds per pipeline stage across {count} queries.",
    "analytics.stage.embedding": "Embedding",
    "analytics.stage.retrieval": "Retrieval",
    "analytics.stage.llm": "LLM generation",
    "analytics.stage.other": "Other",
    "analytics.stage.other_help": "“Other” covers reranking, conflict detection, and the gaps between the timed stages.",
    "analytics.windows.heading": "Response time by lookback window",
    "analytics.windows.caption": "Each window is cumulative — the 24-hour bars include the last hour.",
    "analytics.series.avg": "Average",
    "analytics.series.p95": "95th percentile",
    "analytics.quality.heading": "Answer quality",
    "analytics.quality.caption": "Based on {count} rated answers.",
    "analytics.quality.none": "No answers have been rated in this window.",
    "analytics.quality.summary": "{percent}% helpful — 👍 {helpful} · 👎 {unhelpful}",
    "analytics.comments.heading": "What the downvotes said",
    "analytics.comments.none": "No written feedback in this window.",
    "analytics.slow.heading": "Slowest queries",
    "analytics.slow.caption": "Slower than {threshold} ms, slowest first.",
    "analytics.slow.none": "No query took longer than {threshold} ms.",
    "analytics.slow.threshold_label": "Slow query threshold (ms)",
    "analytics.slow.threshold_help": "Queries slower than this are listed below.",
    "analytics.failed.heading": "Failed & timed-out queries",
    "analytics.failed.caption": "Runs that returned no answer: {count}. Most recent first.",
    "analytics.failed.none": "No failures recorded.",
    "analytics.session.heading": "This browser session’s pipeline timings",
    "analytics.session.caption": "Measured in this process — available even when the metrics tables are not.",
    "analytics.session.none": "No pipeline operations have been timed in this session yet — ask a question in the Chat tab.",
    "analytics.col.stage": "Stage",
    "analytics.col.ms": "Milliseconds",
    "analytics.col.share": "Share",
    "analytics.col.window": "Window",
    "analytics.col.metric": "Metric",
    "analytics.col.query": "Question",
    "analytics.col.total": "Total",
    "analytics.col.when": "When",
    "analytics.col.status": "Status",
    "analytics.col.error": "Error",
    "analytics.col.operation": "Operation",
    "analytics.col.calls": "Calls",
    "analytics.col.avg_ms": "Average ms",
    "analytics.col.vote": "Vote",
    "analytics.col.comment": "Comment",
    # ── Guideline management (admin) ───────────────────────────────
    "guidelines.heading": "🗂️ Guideline Management",
    "guidelines.caption": "Every document in the knowledge base, what retrieval can see of it, and the controls to retire one.",
    "guidelines.count": "{count} documents · {active} active",
    "guidelines.empty": "No documents have been uploaded yet.",
    "guidelines.unavailable": "The document registry is unavailable — {error}",
    "guidelines.session_only": "Showing local sample data — connect Supabase to manage real documents.",
    "guidelines.refresh": "🔄 Reload",
    "guidelines.refresh_help": "Re-read the document registry and its passage counts.",
    "guidelines.indexed_unknown": "—",
    "guidelines.failed": "Could not update “{title} {version}”: {error}",
    "guidelines.missing": "That document no longer exists in the registry.",
    "guidelines.col.title": "Document",
    "guidelines.col.version": "Version",
    "guidelines.col.status": "Status",
    "guidelines.col.effective": "Effective",
    "guidelines.col.indexed": "Passages",
    "guidelines.col.actions": "Admin actions",
    "guidelines.action.archive": "Archive",
    "guidelines.action.archive_help": "Retire this document from retrieval. The record and its passages are kept, so it can be restored.",
    "guidelines.action.supersede": "Supersede",
    "guidelines.action.supersede_help": "Force this version to SUPERSEDED without uploading a replacement.",
    "guidelines.action.needs_db": "Connect Supabase to change a document’s status.",
    "guidelines.action.no_change": "Already {status} — this action would change nothing.",
    "guidelines.confirm.archive_title": "Archive “{title} {version}”?",
    "guidelines.confirm.archive_body": "Field workers will stop being answered from this document. The record and its indexed passages are kept, and it can be restored from the Documents tab.",
    "guidelines.confirm.supersede_title": "Force “{title} {version}” to SUPERSEDED?",
    "guidelines.confirm.supersede_body": "This version stays searchable but is marked out of date, and any answer citing it will carry a stale-guidance warning. Use this when the replacement exists outside CareSync AI.",
    "guidelines.confirm.yes": "Yes, apply",
    "guidelines.confirm.no": "Cancel",
    "guidelines.done.archive": "“{title} {version}” is archived.",
    "guidelines.done.supersede": "“{title} {version}” is marked superseded.",
    "guidelines.sync.heading": "Sync warnings",
    "guidelines.sync.none": "✅ No sync problems found across {count} documents.",
    "guidelines.sync.footer": "Resolve these before field workers act on the affected guidance.",
    "guidelines.sync.needs_db": "Sync checks need the document registry — connect Supabase to run them.",
    "guidelines.sync.source_batch": "Flagged by the sync batch job.",
    "guidelines.sync.source_local": "The sync batch job publishes no flags yet, so these checks ran live against the registry.",
    "guidelines.sync.unverified": "Passage counts could not be read, so indexing was not checked.",
    "guidelines.sync.row_flag": "⚠️ {count}",
    "guidelines.sync.row_flag_help": "This document has {count} sync warning(s) — see the banners above.",
    "guidelines.sync.batch": "Flagged by the batch job",
    "guidelines.sync.duplicate_active": "Multiple ACTIVE versions",
    "guidelines.sync.duplicate_active_detail": "“{title}” has {count} versions marked ACTIVE ({versions}) — retrieval may answer from any of them. Newest is {newest}.",
    "guidelines.sync.not_indexed": "Active but not indexed",
    "guidelines.sync.not_indexed_detail": "“{title} {version}” is ACTIVE but has no indexed passages — retrieval cannot see it at all.",
    "guidelines.sync.future_effective": "Not yet in effect",
    "guidelines.sync.future_effective_detail": "“{title} {version}” is ACTIVE but does not take effect until {date}.",
    "guidelines.sync.no_effective_date": "Missing effective date",
    "guidelines.sync.no_effective_date_detail": "“{title} {version}” is ACTIVE with no effective date, so its currency cannot be checked.",
}


_HI: Dict[str, str] = {
    "app.page_title": "केयरसिंक AI — पूछें। जाँचें। कार्य करें।",
    "app.title": "केयरसिंक AI — पूछें। जाँचें। कार्य करें।",
    "app.tagline": "क्षेत्रीय स्वास्थ्यकर्मियों के लिए AI-आधारित जन-स्वास्थ्य मार्गदर्शन सहायक",
    "app.sidebar_title": "केयरसिंक AI",
    "app.sidebar_caption": "स्प्रिंट 2 MVP",
    "app.sidebar_about": (
        "जन-स्वास्थ्य क्षेत्रीय कर्मियों के लिए रिट्रीवल-ऑगमेंटेड जनरेशन।\n\n"
        "हर उत्तर आधिकारिक, संस्करण-युक्त मार्गदर्शन दस्तावेज़ों पर आधारित होता है "
        "और उद्धरणों से समर्थित होता है।"
    ),
    "app.tab.chat": "💬 चैट सहायक",
    "app.tab.documents": "📄 अपलोड किए गए दस्तावेज़",
    "app.tab.upload": "⬆️ दिशानिर्देश अपलोड करें",

    "lang.heading": "🌐 भाषा",
    "lang.label": "इंटरफ़ेस भाषा",
    "lang.help": "पूरे ऐप के लेबल, बटन और संदेशों की भाषा बदलता है।",
    "lang.note": (
        "केवल इंटरफ़ेस की भाषा — मार्गदर्शन दस्तावेज़, प्राप्त अंश और उत्तर "
        "अपनी मूल भाषा में ही रहते हैं।"
    ),

    "status.ACTIVE": "सक्रिय",
    "status.SUPERSEDED": "अधिक्रमित",
    "status.ARCHIVED": "संग्रहीत",
    "status.any": "सभी स्थितियाँ",
    "status.hint.ACTIVE": "वर्तमान मार्गदर्शन — इस पर कार्य करना सुरक्षित है।",
    "status.hint.SUPERSEDED": "इस दस्तावेज़ का नया संस्करण मौजूद है — कार्य करने से पहले जाँच लें।",
    "status.hint.ARCHIVED": "सक्रिय मार्गदर्शन से हटाया गया — केवल ऑडिट के लिए रखा गया है।",

    "filters.heading": "🔍 खोज फ़िल्टर",
    "filters.title_label": "दस्तावेज़ शीर्षक में शामिल है",
    "filters.title_placeholder": "उदा. टीकाकरण",
    "filters.title_help": "अपलोड किए गए दस्तावेज़ टैब को फ़िल्टर करता है।",
    "filters.status_label": "दस्तावेज़ की स्थिति",
    "filters.status_help": "'सभी स्थितियाँ' चुनने पर चैट हमेशा सक्रिय मार्गदर्शन से ही उत्तर देती है।",
    "filters.use_dates": "प्रभावी तिथि से फ़िल्टर करें",
    "filters.date_label": "प्रभावी तिथि सीमा",
    "filters.date_help": "दस्तावेज़ की प्रभावी तिथि की समावेशी निचली और ऊपरी सीमा।",
    "filters.date_order_warning": "आरंभ तिथि अंतिम तिथि के बाद है — कोई परिणाम नहीं दिखाया जा रहा।",
    "filters.keyword_label": "कीवर्ड बूस्ट (वैकल्पिक)",
    "filters.keyword_placeholder": "उदा. खसरा खुराक",
    "filters.keyword_help": "हाइब्रिड रिट्रीवर को स्पष्ट फुल-टेक्स्ट कीवर्ड के रूप में भेजा जाता है।",
    "filters.reset": "फ़िल्टर रीसेट करें",

    "docs.heading": "📄 अपलोड किए गए जन-स्वास्थ्य दस्तावेज़",
    "docs.empty": "अभी तक कोई दस्तावेज़ अपलोड नहीं हुआ है। जोड़ने के लिए **दिशानिर्देश अपलोड करें** टैब का उपयोग करें।",
    "docs.session_notice": "⚠️ सत्र डेटा दिखाया जा रहा है — Supabase उपलब्ध नहीं है, इसलिए स्थिति में बदलाव सहेजे नहीं जाएँगे।",
    "docs.showing": "**{total}** में से **{visible}** दस्तावेज़ दिखाए जा रहे हैं · {active} सक्रिय — साइडबार से फ़िल्टर करें।",
    "docs.no_match": "वर्तमान साइडबार फ़िल्टर से कोई दस्तावेज़ मेल नहीं खाता। तिथि सीमा या स्थिति को विस्तृत करें।",
    "docs.version_effective": "संस्करण {version} · प्रभावी {effective}",
    "docs.set_status": "स्थिति निर्धारित करें",
    "docs.apply": "लागू करें",
    "docs.apply_help": "इस दस्तावेज़ को चयनित स्थिति में ले जाएँ।",
    "docs.delete": "🗑️ हटाएँ",
    "docs.delete_help": "इस दस्तावेज़ को संग्रहीत करें या स्थायी रूप से हटाएँ।",
    "docs.timeline": "🕓 संस्करण समयरेखा — {title}",
    "docs.status_changed": "'{title}' अब {status} है।",
    "docs.status_session_only": (
        "'{title}' को केवल इस सत्र के लिए {status} किया गया — "
        "स्थिति परिवर्तन सहेजने के लिए Supabase जोड़ें।"
    ),
    "docs.status_failed": "'{title}' को अपडेट नहीं किया जा सका: {error}",
    "docs.status_missing": "id {id} वाला कोई दस्तावेज़ नहीं मिला — संभवतः इसे हटा दिया गया है।",

    "timeline.empty": "इस दस्तावेज़ के लिए अभी कोई संस्करण इतिहास उपलब्ध नहीं है।",
    "timeline.this_row": "यह पंक्ति",
    "timeline.effective": "प्रभावी {date}",
    "timeline.superseded_note": " · बाद के संस्करण द्वारा प्रतिस्थापित",

    "delete.modal_title": "इस दस्तावेज़ को हटाएँ?",
    "delete.inline_title": "🗑️ इस दस्तावेज़ को हटाएँ?",
    "delete.mode_question": "इस दस्तावेज़ को कैसे हटाया जाए?",
    "delete.mode.archive": "संग्रहीत करें (पुनर्प्राप्ति योग्य)",
    "delete.mode.permanent": "स्थायी रूप से हटाएँ",
    "delete.mode.archive_caption": (
        "ऑडिट के लिए रिकॉर्ड और उद्धरण बने रहते हैं, पर उत्तर इससे नहीं दिए जाएँगे।"
    ),
    "delete.mode.permanent_caption": (
        "दस्तावेज़ और उसके अनुक्रमित अंश मिटा देता है। इसे वापस नहीं लिया जा सकता।"
    ),
    "delete.permanent_warning": (
        "स्थायी विलोपन इस दस्तावेज़ के हर अनुक्रमित अंश को भी हटा देता है, "
        "इसलिए पुराने उत्तरों को इससे जोड़ा नहीं जा सकेगा।"
    ),
    "delete.ack": "मैं समझता/समझती हूँ कि इसे वापस नहीं लिया जा सकता।",
    "delete.session_notice": "Supabase उपलब्ध नहीं है, इसलिए इसका प्रभाव केवल इसी सत्र पर पड़ेगा।",
    "delete.cancel": "रद्द करें",
    "delete.confirm_archive": "दस्तावेज़ संग्रहीत करें",
    "delete.confirm_permanent": "स्थायी रूप से हटाएँ",
    "delete.done_archived": "'{title}' संग्रहीत कर दिया गया।",
    "delete.done_deleted": "'{title}' स्थायी रूप से हटा दिया गया।",
    "delete.session_archived": (
        "'{title}' केवल इस सत्र के लिए संग्रहीत किया गया — "
        "विलोपन सहेजने के लिए Supabase जोड़ें।"
    ),
    "delete.session_deleted": (
        "'{title}' केवल इस सत्र के लिए स्थायी रूप से हटाया गया — "
        "विलोपन सहेजने के लिए Supabase जोड़ें।"
    ),
    "delete.failed": "'{title}' को हटाया नहीं जा सका: {error}",
    "delete.not_found": "id {id} वाला कोई दस्तावेज़ नहीं मिला — संभवतः इसे पहले ही हटा दिया गया है।",

    "chat.heading": "💬 जन-स्वास्थ्य मार्गदर्शन पूछें",
    "chat.welcome": (
        "नमस्ते! मैं **केयरसिंक AI** हूँ, आपका जन-स्वास्थ्य मार्गदर्शन सहायक। "
        "मुझसे सक्रिय प्रकोप प्रोटोकॉल, टीकाकरण दिशानिर्देश या स्वास्थ्य परामर्श "
        "के बारे में प्रश्न पूछें।"
    ),
    "chat.input_placeholder": "वर्तमान टीकाकरण प्रोटोकॉल क्या है?",
    "chat.spinner": "सक्रिय जन-स्वास्थ्य मार्गदर्शन खोजा जा रहा है...",
    "chat.searching": "🔍 {filters} के अनुसार खोज — इन्हें साइडबार से बदलें।",
    "chat.filter_status": "स्थिति **{status}**",
    "chat.filter_status_any": "स्थिति **सक्रिय** (चैट हमेशा सक्रिय मार्गदर्शन से उत्तर देती है)",
    "chat.filter_dates": "प्रभावी **{date_from} → {date_to}**",
    "chat.filter_keyword": "कीवर्ड **{keyword}**",
    "chat.sources": "📌 **स्रोत और उद्धरण** ({count})",
    "chat.sources_stale": " — {count} गैर-सक्रिय मार्गदर्शन से",
    "chat.sources_scored": " · आपके प्रश्न से प्रासंगिकता के क्रम में",
    "chat.citation_meta": "पृष्ठ {page} · संस्करण {version} · प्रभावी {effective}",
    "chat.passage_preview": "🔍 अंश पूर्वावलोकन — {title}, पृष्ठ {page}",
    "chat.highlight_note": "हाइलाइट किए गए शब्द आपके प्रश्न से लिए गए हैं।",

    "chat.chips_intro": "✨ कहाँ से शुरू करें? इनमें से कोई आज़माएँ:",
    "chat.prompt.1": "वर्तमान खसरा टीकाकरण कार्यक्रम क्या है?",
    "chat.prompt.2": "संदिग्ध प्रकोप की रिपोर्ट कैसे करूँ?",
    "chat.prompt.3": "घरेलू दौरे के लिए कौन-से PPE आवश्यक हैं?",
    "chat.prompt.4": "क्या हैजा उपचार मार्गदर्शन बदला है?",

    "chat.copy": "📋 कॉपी",
    "chat.copy_hint": "बॉक्स पर माउस ले जाएँ और उत्तर कॉपी करने के लिए कॉपी आइकन पर क्लिक करें।",
    "chat.export_pdf": "📄 PDF",
    "chat.export_pdf_help": "इस उत्तर और उसके उद्धरणों को PDF सारांश के रूप में डाउनलोड करें।",
    "chat.export_pdf_unavailable": "PDF निर्यात के लिए PyMuPDF आवश्यक है — `pip install pymupdf` चलाएँ।",
    "chat.export_txt": "⬇️ TXT",
    "chat.export_txt_help": "इस उत्तर और उसके उद्धरणों को सादे पाठ के रूप में डाउनलोड करें।",
    "chat.export_note": "डाउनलोड अंग्रेज़ी में होते हैं — वे मूल मार्गदर्शन दस्तावेज़ों के अनुरूप हैं।",

    "conflict.title_warning": "परस्पर विरोधी मार्गदर्शन मिला",
    "conflict.title_danger": "दस्तावेज़ संस्करणों के बीच परस्पर विरोधी मार्गदर्शन",
    "conflict.footer": (
        "इस उत्तर पर कार्य करने से पहले नीचे दिए उद्धरणों की तुलना नवीनतम "
        "सक्रिय मार्गदर्शन से करें।"
    ),
    "conflict.fallback": "प्राप्त दस्तावेज़ अलग-अलग मार्गदर्शन देते हैं।",

    "upload.heading": "⬆️ स्वीकृत मार्गदर्शन PDF अपलोड करें",
    "upload.caption": "नीचे PDF खींचकर छोड़ें, या ब्राउज़ करने के लिए क्लिक करें। केवल स्वीकृत मार्गदर्शन।",
    "upload.title_label": "दस्तावेज़ शीर्षक",
    "upload.title_placeholder": "उदा., बाल टीकाकरण दिशानिर्देश",
    "upload.version_label": "संस्करण",
    "upload.date_label": "प्रभावी तिथि",
    "upload.file_label": "PDF फ़ाइल यहाँ छोड़ें, या ब्राउज़ करने के लिए क्लिक करें",
    "upload.file_help": "इस MVP में केवल PDF दस्तावेज़ समर्थित हैं।",
    "upload.submit": "अपलोड करें और अनुक्रमित करें",
    "upload.processing": "'{title}' संसाधित हो रहा है... पाठ निकालना, चंकिंग और एम्बेडिंग।",
    "upload.indexing": "'{title}' को ज्ञान-कोश में अनुक्रमित किया जा रहा है...",
    "upload.success": (
        "'{title}' ({filename}) संसाधित होकर ज्ञान-कोश में जोड़ा गया — "
        "**{pages} पृष्ठ**, **{chunks} चंक** अनुक्रमित।"
    ),
    "upload.failed": "'{title}' को संसाधित नहीं किया जा सका: {error}",
    "upload.missing_fields": "कृपया दस्तावेज़ शीर्षक भरें और एक PDF फ़ाइल चुनें।",
    # ── Chat history drawer ──────────────────────────────────────────────────
    "history.heading": "🕓 चैट इतिहास",
    "history.new_chat": "➕ नई चैट",
    "history.new_chat_help": "नई बातचीत शुरू करें। मौजूदा बातचीत सहेजी रहेगी।",
    "history.recent": "हाल की बातचीत ({count})",
    "history.empty": "अभी कोई सहेजी गई बातचीत नहीं है — कोई प्रश्न पूछें, यह चैट यहाँ दिखेगी।",
    "history.unavailable": (
        "चैट इतिहास अभी उपलब्ध नहीं है — यह बातचीत केवल इसी डिवाइस पर रखी जा रही "
        "है और पृष्ठ बंद करने पर मिट जाएगी।"
    ),
    "history.untitled": "बिना शीर्षक चैट",
    "history.open_help": "यह बातचीत खोलें — अंतिम बार सक्रिय {when}।",
    "history.rename_help": "इस बातचीत का नाम बदलें",
    "history.rename_label": "बातचीत का शीर्षक",
    "history.rename_save": "सहेजें",
    "history.rename_cancel": "रद्द करें",
    "history.renamed": "नाम बदलकर '{title}' किया गया।",
    "history.rename_failed": "'{title}' का नाम नहीं बदला जा सका।",
    "history.delete_help": "यह बातचीत हटाएँ",
    "history.deleted": "'{title}' हटा दी गई।",
    "history.delete_failed": "'{title}' को हटाया नहीं जा सका।",
    "history.delete_missing": "वह बातचीत अब मौजूद नहीं है।",
    "history.just_now": "अभी-अभी",
    "history.minutes_ago": "{count} मिनट पहले",
    "history.hours_ago": "{count} घंटे पहले",
    "history.days_ago": "{count} दिन पहले",

    # ── Answer feedback ──────────────────────────────────────────────────────
    "feedback.prompt": "क्या यह उत्तर उपयोगी था?",
    "feedback.up_help": "यह उत्तर सही और उपयोगी था।",
    "feedback.down_help": "यह उत्तर ग़लत, अधूरा या अनुपयोगी था।",
    "feedback.thanks_up": "✅ धन्यवाद — उपयोगी के रूप में दर्ज किया गया।",
    "feedback.thanks_down": "धन्यवाद — मार्गदर्शन टीम की समीक्षा के लिए दर्ज किया गया।",
    "feedback.thanks_down_comment": "धन्यवाद — आपकी टिप्पणी मार्गदर्शन टीम को भेज दी गई।",
    "feedback.not_saved": "⚠️ केवल इसी डिवाइस पर दर्ज — फ़ीडबैक सेवा उपलब्ध नहीं है।",
    "feedback.comment_label": "इस उत्तर में क्या ग़लत था? (वैकल्पिक)",
    "feedback.comment_placeholder": "जैसे: पुराना प्रोटोकॉल उद्धृत किया, ख़ुराक तालिका छूट गई",
    "feedback.comment_send": "भेजें",
    "feedback.comment_skip": "छोड़ें",

    # ── Voice input ──────────────────────────────────────────────────────────
    "voice.heading": "🎙️ बोलकर पूछें",
    "voice.intro": "अपना प्रश्न रिकॉर्ड करें, सुनें, फिर पूछने से पहले प्रतिलेख जाँच लें।",
    "voice.record_label": "अपना प्रश्न रिकॉर्ड करें",
    "voice.record_help": "रिकॉर्डिंग शुरू करने के लिए माइक्रोफ़ोन दबाएँ, रोकने के लिए फिर दबाएँ।",
    "voice.recorder_unsupported": (
        "इस Streamlit संस्करण में माइक्रोफ़ोन रिकॉर्डर नहीं है — इसके बजाय ऑडियो "
        "फ़ाइल अपलोड करें, या Streamlit 1.41+ पर अपग्रेड करें।"
    ),
    "voice.upload_label": "ऑडियो प्रश्न अपलोड करें",
    "voice.upload_help": "WAV, MP3, M4A, OGG, WEBM या FLAC।",
    "voice.too_large": "यह रिकॉर्डिंग {limit} MB से बड़ी है — छोटा प्रश्न रिकॉर्ड करें।",
    "voice.transcribe": "✍️ प्रतिलेख बनाएँ",
    "voice.transcribe_help": "पूछने से पहले रिकॉर्डिंग को पाठ में बदलें।",
    "voice.transcribing": "आपकी रिकॉर्डिंग का प्रतिलेख बनाया जा रहा है...",
    "voice.transcript_caption": "{seconds} सेकंड में प्रतिलेख तैयार — पूछने से पहले जाँच लें।",
    "voice.transcript_label": "प्रतिलेख",
    "voice.transcript_help": "वाक्-से-पाठ में हुई कोई भी ग़लती सुधारें, फिर पूछें।",
    "voice.ask": "यह प्रश्न पूछें",
    "voice.discard": "हटाएँ",
    "voice.empty_transcript": "इस रिकॉर्डिंग में कोई आवाज़ नहीं मिली — माइक्रोफ़ोन के पास से फिर प्रयास करें।",
    "voice.failed": "इस रिकॉर्डिंग का प्रतिलेख नहीं बनाया जा सका: {error}",

    # ── Retrieval confidence ─────────────────────────────────────────────────
    "confidence.high": "उच्च प्रासंगिकता",
    "confidence.medium": "मध्यम प्रासंगिकता",
    "confidence.low": "कम प्रासंगिकता",
    "confidence.badge": "{percent}%",
    "confidence.help": (
        "{label} — रीरैंकर ने इस अंश को आपके प्रश्न के लिए {percent}% प्रासंगिक "
        "आँका (मॉडल स्कोर {score})।"
    ),
    "confidence.detail": "पुनःक्रम #{rank} · {label} ({percent}%)",
    # ── Admin analytics dashboard ──────────────────────────────────
    "app.tab.analytics": "📊 विश्लेषण",
    "analytics.heading": "📊 एडमिन विश्लेषण डैशबोर्ड",
    "analytics.caption": "पुनर्प्राप्ति पाइपलाइन का परिचालन स्वास्थ्य, और क्षेत्र कर्मियों को उसके उत्तर कितने उपयोगी लगे।",
    "analytics.window_label": "समयावधि",
    "analytics.window.1": "पिछला 1 घंटा",
    "analytics.window.6": "पिछले 6 घंटे",
    "analytics.window.24": "पिछले 24 घंटे",
    "analytics.window.168": "पिछले 7 दिन",
    "analytics.window.720": "पिछले 30 दिन",
    "analytics.window_note": "चारों आँकड़े {window} के हैं।",
    "analytics.refresh": "🔄 ताज़ा करें",
    "analytics.refresh_help": "संचित आँकड़े हटाकर मेट्रिक्स तालिकाएँ फिर से पढ़ें।",
    "analytics.no_data": "इस अवधि में अभी कोई प्रश्न दर्ज नहीं हुआ है।",
    "analytics.unavailable": "मेट्रिक्स इस समय उपलब्ध नहीं हैं — {error}",
    "analytics.unavailable_hint": "RAG पाइपलाइन चलते समय ये आँकड़े Supabase में लिखती है। कनेक्शन जाँचें, फिर ताज़ा करें।",
    "analytics.source_note": "{module} से पढ़ा जा रहा है। आँकड़े {seconds} सेकंड तक संचित रहते हैं।",
    "analytics.millis": "{value} मि.से.",
    "analytics.seconds": "{value} से.",
    "analytics.table.show": "डेटा तालिका दिखाएँ",
    "analytics.kpi.queries": "उत्तर दिए गए प्रश्न",
    "analytics.kpi.queries_sub": "{rate} प्रति घंटा",
    "analytics.kpi.queries_help": "इस अवधि में दर्ज हर RAG पाइपलाइन रन — सफल हो या नहीं।",
    "analytics.kpi.latency": "औसत प्रतिक्रिया",
    "analytics.kpi.latency_sub": "p95 {p95} · सबसे धीमा {max}",
    "analytics.kpi.latency_help": "प्रश्न से आधारित उत्तर तक का कुल समय।",
    "analytics.kpi.success": "सफलता दर",
    "analytics.kpi.success_sub": "{failed} विफल या समय-समाप्त",
    "analytics.kpi.success_help": "बिना त्रुटि या समय-समाप्ति के उत्तर देने वाले प्रश्नों का हिस्सा।",
    "analytics.kpi.helpful": "उपयोगी उत्तर",
    "analytics.kpi.helpful_sub": "👍 {up} · 👎 {down}",
    "analytics.kpi.helpful_help": "रेटिंग वाले उत्तरों में से जिन्हें क्षेत्र कर्मी ने उपयोगी बताया।",
    "analytics.kpi.none": "—",
    "analytics.breakdown.heading": "समय कहाँ जाता है",
    "analytics.breakdown.caption": "{count} प्रश्नों में प्रति पाइपलाइन चरण औसत मिलीसेकंड।",
    "analytics.stage.embedding": "एम्बेडिंग",
    "analytics.stage.retrieval": "पुनर्प्राप्ति",
    "analytics.stage.llm": "LLM उत्तर-निर्माण",
    "analytics.stage.other": "अन्य",
    "analytics.stage.other_help": "“अन्य” में पुनःक्रमण, विरोधाभास पहचान और मापे गए चरणों के बीच का समय शामिल है।",
    "analytics.windows.heading": "समयावधि के अनुसार प्रतिक्रिया समय",
    "analytics.windows.caption": "हर अवधि संचयी है — 24-घंटे के बार में पिछला 1 घंटा भी शामिल है।",
    "analytics.series.avg": "औसत",
    "analytics.series.p95": "95वाँ प्रतिशतक",
    "analytics.quality.heading": "उत्तर की गुणवत्ता",
    "analytics.quality.caption": "{count} रेटिंग वाले उत्तरों पर आधारित।",
    "analytics.quality.none": "इस अवधि में किसी उत्तर को रेटिंग नहीं मिली।",
    "analytics.quality.summary": "{percent}% उपयोगी — 👍 {helpful} · 👎 {unhelpful}",
    "analytics.comments.heading": "नकारात्मक रेटिंग पर टिप्पणियाँ",
    "analytics.comments.none": "इस अवधि में कोई लिखित प्रतिक्रिया नहीं।",
    "analytics.slow.heading": "सबसे धीमे प्रश्न",
    "analytics.slow.caption": "{threshold} मि.से. से धीमे, सबसे धीमा पहले।",
    "analytics.slow.none": "कोई भी प्रश्न {threshold} मि.से. से अधिक नहीं लगा।",
    "analytics.slow.threshold_label": "धीमे प्रश्न की सीमा (मि.से.)",
    "analytics.slow.threshold_help": "इससे धीमे प्रश्न नीचे सूचीबद्ध हैं।",
    "analytics.failed.heading": "विफल और समय-समाप्त प्रश्न",
    "analytics.failed.caption": "उत्तर न मिलने वाले रन: {count}। नवीनतम पहले।",
    "analytics.failed.none": "कोई विफलता दर्ज नहीं।",
    "analytics.session.heading": "इस ब्राउज़र सत्र की पाइपलाइन अवधि",
    "analytics.session.caption": "इसी प्रक्रिया में मापा गया — मेट्रिक्स तालिकाएँ न मिलने पर भी उपलब्ध।",
    "analytics.session.none": "इस सत्र में अभी कोई पाइपलाइन संचालन मापा नहीं गया — चैट टैब में एक प्रश्न पूछें।",
    "analytics.col.stage": "चरण",
    "analytics.col.ms": "मिलीसेकंड",
    "analytics.col.share": "हिस्सा",
    "analytics.col.window": "अवधि",
    "analytics.col.metric": "माप",
    "analytics.col.query": "प्रश्न",
    "analytics.col.total": "कुल",
    "analytics.col.when": "कब",
    "analytics.col.status": "स्थिति",
    "analytics.col.error": "त्रुटि",
    "analytics.col.operation": "संचालन",
    "analytics.col.calls": "कॉल",
    "analytics.col.avg_ms": "औसत मि.से.",
    "analytics.col.vote": "रेटिंग",
    "analytics.col.comment": "टिप्पणी",
    # ── Guideline management (admin) ───────────────────────────────
    "guidelines.heading": "🗂️ दिशानिर्देश प्रबंधन",
    "guidelines.caption": "ज्ञान-भंडार का हर दस्तावेज़, पुनर्प्राप्ति उसमें से क्या देख पाती है, और उसे हटाने के नियंत्रण।",
    "guidelines.count": "{count} दस्तावेज़ · {active} सक्रिय",
    "guidelines.empty": "अभी तक कोई दस्तावेज़ अपलोड नहीं हुआ है।",
    "guidelines.unavailable": "दस्तावेज़ रजिस्ट्री उपलब्ध नहीं है — {error}",
    "guidelines.session_only": "स्थानीय नमूना डेटा दिख रहा है — वास्तविक दस्तावेज़ प्रबंधित करने के लिए Supabase से जोड़ें।",
    "guidelines.refresh": "🔄 पुनः लोड करें",
    "guidelines.refresh_help": "दस्तावेज़ रजिस्ट्री और उसकी अंश-संख्याएँ फिर से पढ़ें।",
    "guidelines.indexed_unknown": "—",
    "guidelines.failed": "“{title} {version}” को अद्यतन नहीं किया जा सका: {error}",
    "guidelines.missing": "वह दस्तावेज़ अब रजिस्ट्री में नहीं है।",
    "guidelines.col.title": "दस्तावेज़",
    "guidelines.col.version": "संस्करण",
    "guidelines.col.status": "स्थिति",
    "guidelines.col.effective": "प्रभावी",
    "guidelines.col.indexed": "अंश",
    "guidelines.col.actions": "एडमिन कार्रवाई",
    "guidelines.action.archive": "संग्रह",
    "guidelines.action.archive_help": "इस दस्तावेज़ को पुनर्प्राप्ति से हटाएँ। रिकॉर्ड और अंश सुरक्षित रहते हैं, इसलिए इसे वापस लाया जा सकता है।",
    "guidelines.action.supersede": "अधिक्रमित",
    "guidelines.action.supersede_help": "प्रतिस्थापन अपलोड किए बिना इस संस्करण को SUPERSEDED करें।",
    "guidelines.action.needs_db": "दस्तावेज़ की स्थिति बदलने के लिए Supabase से जोड़ें।",
    "guidelines.action.no_change": "पहले से ही {status} — इस कार्रवाई से कुछ नहीं बदलेगा।",
    "guidelines.confirm.archive_title": "क्या “{title} {version}” को संग्रहित करें?",
    "guidelines.confirm.archive_body": "क्षेत्र कर्मियों को अब इस दस्तावेज़ से उत्तर नहीं मिलेंगे। रिकॉर्ड और अनुक्रमित अंश सुरक्षित रहते हैं, और इसे दस्तावेज़ टैब से वापस लाया जा सकता है।",
    "guidelines.confirm.supersede_title": "क्या “{title} {version}” को SUPERSEDED करें?",
    "guidelines.confirm.supersede_body": "यह संस्करण खोजने योग्य रहेगा पर पुराना चिह्नित होगा, और इसे उद्धृत करने वाले उत्तर पर पुरानी-मार्गदर्शन चेतावनी दिखेगी। इसका उपयोग तब करें जब प्रतिस्थापन CareSync AI के बाहर मौजूद हो।",
    "guidelines.confirm.yes": "हाँ, लागू करें",
    "guidelines.confirm.no": "रद्द करें",
    "guidelines.done.archive": "“{title} {version}” संग्रहित कर दिया गया।",
    "guidelines.done.supersede": "“{title} {version}” अधिक्रमित चिह्नित कर दिया गया।",
    "guidelines.sync.heading": "समन्वयन चेतावनियाँ",
    "guidelines.sync.none": "✅ {count} दस्तावेज़ों में कोई समन्वयन समस्या नहीं मिली।",
    "guidelines.sync.footer": "क्षेत्र कर्मियों द्वारा इस मार्गदर्शन पर कार्य करने से पहले इन्हें हल करें।",
    "guidelines.sync.needs_db": "समन्वयन जाँच के लिए दस्तावेज़ रजिस्ट्री चाहिए — Supabase से जोड़ें।",
    "guidelines.sync.source_batch": "समन्वयन बैच कार्य द्वारा चिह्नित।",
    "guidelines.sync.source_local": "समन्वयन बैच कार्य अभी कोई चिह्न प्रकाशित नहीं करता, इसलिए ये जाँच रजिस्ट्री पर सीधे चलाई गईं।",
    "guidelines.sync.unverified": "अंश-संख्याएँ पढ़ी नहीं जा सकीं, इसलिए अनुक्रमण की जाँच नहीं हुई।",
    "guidelines.sync.row_flag": "⚠️ {count}",
    "guidelines.sync.row_flag_help": "इस दस्तावेज़ पर {count} समन्वयन चेतावनी है — ऊपर के बैनर देखें।",
    "guidelines.sync.batch": "बैच कार्य द्वारा चिह्नित",
    "guidelines.sync.duplicate_active": "एक से अधिक ACTIVE संस्करण",
    "guidelines.sync.duplicate_active_detail": "“{title}” के {count} संस्करण ACTIVE चिह्नित हैं ({versions}) — पुनर्प्राप्ति इनमें से किसी से भी उत्तर दे सकती है। नवीनतम {newest} है।",
    "guidelines.sync.not_indexed": "सक्रिय पर अनुक्रमित नहीं",
    "guidelines.sync.not_indexed_detail": "“{title} {version}” ACTIVE है पर इसका कोई अनुक्रमित अंश नहीं — पुनर्प्राप्ति इसे देख ही नहीं सकती।",
    "guidelines.sync.future_effective": "अभी प्रभावी नहीं",
    "guidelines.sync.future_effective_detail": "“{title} {version}” ACTIVE है पर {date} से ही प्रभावी होगा।",
    "guidelines.sync.no_effective_date": "प्रभावी तिथि अनुपस्थित",
    "guidelines.sync.no_effective_date_detail": "“{title} {version}” ACTIVE है पर कोई प्रभावी तिथि नहीं, इसलिए इसकी नवीनता जाँची नहीं जा सकती।",
}


_TA: Dict[str, str] = {
    "app.page_title": "கேர்சிங்க் AI — கேளுங்கள். சரிபாருங்கள். செயல்படுங்கள்.",
    "app.title": "கேர்சிங்க் AI — கேளுங்கள். சரிபாருங்கள். செயல்படுங்கள்.",
    "app.tagline": "கள சுகாதாரப் பணியாளர்களுக்கான AI அடிப்படையிலான பொது சுகாதார வழிகாட்டி உதவியாளர்",
    "app.sidebar_title": "கேர்சிங்க் AI",
    "app.sidebar_caption": "ஸ்பிரிண்ட் 2 MVP",
    "app.sidebar_about": (
        "பொது சுகாதாரக் கள பணியாளர்களுக்கான Retrieval-Augmented Generation.\n\n"
        "ஒவ்வொரு பதிலும் அதிகாரப்பூர்வ, பதிப்பு அடையாளமிடப்பட்ட வழிகாட்டி "
        "ஆவணங்களை அடிப்படையாகக் கொண்டு மேற்கோள்களுடன் வழங்கப்படுகிறது."
    ),
    "app.tab.chat": "💬 அரட்டை உதவியாளர்",
    "app.tab.documents": "📄 பதிவேற்றிய ஆவணங்கள்",
    "app.tab.upload": "⬆️ வழிகாட்டி பதிவேற்று",

    "lang.heading": "🌐 மொழி",
    "lang.label": "இடைமுக மொழி",
    "lang.help": "செயலி முழுவதும் உள்ள லேபிள்கள், பொத்தான்கள் மற்றும் செய்திகளை மாற்றுகிறது.",
    "lang.note": (
        "இடைமுக மொழி மட்டுமே — வழிகாட்டி ஆவணங்கள், மீட்டெடுக்கப்பட்ட பகுதிகள் "
        "மற்றும் பதில்கள் அவற்றின் மூல மொழியிலேயே இருக்கும்."
    ),

    "status.ACTIVE": "செயலில்",
    "status.SUPERSEDED": "மாற்றப்பட்டது",
    "status.ARCHIVED": "காப்பகப்படுத்தப்பட்டது",
    "status.any": "அனைத்து நிலைகளும்",
    "status.hint.ACTIVE": "தற்போதைய வழிகாட்டுதல் — செயல்படுத்த பாதுகாப்பானது.",
    "status.hint.SUPERSEDED": "இந்த ஆவணத்தின் புதிய பதிப்பு உள்ளது — செயல்படுவதற்கு முன் சரிபார்க்கவும்.",
    "status.hint.ARCHIVED": "செயலில் உள்ள வழிகாட்டுதலிலிருந்து விலக்கப்பட்டது — தணிக்கைக்காக மட்டுமே வைக்கப்பட்டுள்ளது.",

    "filters.heading": "🔍 தேடல் வடிகட்டிகள்",
    "filters.title_label": "ஆவணத் தலைப்பில் உள்ளது",
    "filters.title_placeholder": "எ.கா. தடுப்பூசி",
    "filters.title_help": "பதிவேற்றிய ஆவணங்கள் தாவலை வடிகட்டுகிறது.",
    "filters.status_label": "ஆவண நிலை",
    "filters.status_help": "'அனைத்து நிலைகளும்' தேர்ந்தெடுக்கும்போது அரட்டை எப்போதும் செயலில் உள்ள வழிகாட்டுதலிலிருந்தே பதிலளிக்கும்.",
    "filters.use_dates": "அமல் தேதி மூலம் வடிகட்டு",
    "filters.date_label": "அமல் தேதி வரம்பு",
    "filters.date_help": "ஆவணத்தின் அமல் தேதிக்கான உள்ளடக்கிய கீழ் மற்றும் மேல் வரம்புகள்.",
    "filters.date_order_warning": "தொடக்க தேதி முடிவு தேதிக்குப் பிறகு உள்ளது — முடிவுகள் எதுவும் இல்லை.",
    "filters.keyword_label": "முக்கியச்சொல் ஊக்கம் (விருப்பத்தேர்வு)",
    "filters.keyword_placeholder": "எ.கா. தட்டம்மை அளவு",
    "filters.keyword_help": "கலப்பு மீட்டெடுப்பானுக்கு வெளிப்படையான முழு-உரை முக்கியச்சொல்லாக அனுப்பப்படுகிறது.",
    "filters.reset": "வடிகட்டிகளை மீட்டமை",

    "docs.heading": "📄 பதிவேற்றிய பொது சுகாதார ஆவணங்கள்",
    "docs.empty": "இதுவரை எந்த ஆவணமும் பதிவேற்றப்படவில்லை. சேர்க்க **வழிகாட்டி பதிவேற்று** தாவலைப் பயன்படுத்தவும்.",
    "docs.session_notice": "⚠️ அமர்வுத் தரவு காட்டப்படுகிறது — Supabase அணுக முடியவில்லை, எனவே நிலை மாற்றங்கள் சேமிக்கப்படாது.",
    "docs.showing": "**{total}** இல் **{visible}** ஆவணங்கள் காட்டப்படுகின்றன · {active} செயலில் — பக்கப்பட்டியில் வடிகட்டவும்.",
    "docs.no_match": "தற்போதைய வடிகட்டிகளுக்கு எந்த ஆவணமும் பொருந்தவில்லை. தேதி வரம்பையோ நிலையையோ விரிவாக்கவும்.",
    "docs.version_effective": "பதிப்பு {version} · அமல் {effective}",
    "docs.set_status": "நிலையை அமை",
    "docs.apply": "பயன்படுத்து",
    "docs.apply_help": "இந்த ஆவணத்தைத் தேர்ந்தெடுத்த நிலைக்கு மாற்றவும்.",
    "docs.delete": "🗑️ நீக்கு",
    "docs.delete_help": "இந்த ஆவணத்தைக் காப்பகப்படுத்தவும் அல்லது நிரந்தரமாக நீக்கவும்.",
    "docs.timeline": "🕓 பதிப்பு கால வரிசை — {title}",
    "docs.status_changed": "'{title}' இப்போது {status}.",
    "docs.status_session_only": (
        "'{title}' இந்த அமர்வுக்கு மட்டும் {status} ஆக அமைக்கப்பட்டது — "
        "நிலை மாற்றங்களைச் சேமிக்க Supabase இணைக்கவும்."
    ),
    "docs.status_failed": "'{title}' ஐப் புதுப்பிக்க முடியவில்லை: {error}",
    "docs.status_missing": "id {id} உடன் ஆவணம் எதுவும் இல்லை — அது நீக்கப்பட்டிருக்கலாம்.",

    "timeline.empty": "இந்த ஆவணத்திற்கு இதுவரை பதிப்பு வரலாறு இல்லை.",
    "timeline.this_row": "இந்த வரிசை",
    "timeline.effective": "அமல் {date}",
    "timeline.superseded_note": " · பிந்தைய பதிப்பால் மாற்றப்பட்டது",

    "delete.modal_title": "இந்த ஆவணத்தை நீக்கவா?",
    "delete.inline_title": "🗑️ இந்த ஆவணத்தை நீக்கவா?",
    "delete.mode_question": "இந்த ஆவணத்தை எவ்வாறு நீக்க வேண்டும்?",
    "delete.mode.archive": "காப்பகப்படுத்து (மீட்டெடுக்கக்கூடியது)",
    "delete.mode.permanent": "நிரந்தரமாக நீக்கு",
    "delete.mode.archive_caption": (
        "தணிக்கைக்காக பதிவும் மேற்கோள்களும் இருக்கும், ஆனால் இதிலிருந்து பதில்கள் வழங்கப்படாது."
    ),
    "delete.mode.permanent_caption": (
        "ஆவணத்தையும் அதன் அட்டவணைப்படுத்தப்பட்ட பகுதிகளையும் அழிக்கும். இதைத் திரும்பப் பெற முடியாது."
    ),
    "delete.permanent_warning": (
        "நிரந்தர நீக்கம் இந்த ஆவணத்தின் ஒவ்வொரு அட்டவணைப் பகுதியையும் நீக்குகிறது, "
        "எனவே கடந்த பதில்களை இதனுடன் இணைக்க முடியாது."
    ),
    "delete.ack": "இதைத் திரும்பப் பெற முடியாது என்பதை நான் புரிந்துகொள்கிறேன்.",
    "delete.session_notice": "Supabase அணுக முடியவில்லை, எனவே இது தற்போதைய அமர்வை மட்டுமே பாதிக்கும்.",
    "delete.cancel": "ரத்து செய்",
    "delete.confirm_archive": "ஆவணத்தைக் காப்பகப்படுத்து",
    "delete.confirm_permanent": "நிரந்தரமாக நீக்கு",
    "delete.done_archived": "'{title}' காப்பகப்படுத்தப்பட்டது.",
    "delete.done_deleted": "'{title}' நிரந்தரமாக நீக்கப்பட்டது.",
    "delete.session_archived": (
        "'{title}' இந்த அமர்வுக்கு மட்டும் காப்பகப்படுத்தப்பட்டது — "
        "நீக்கங்களைச் சேமிக்க Supabase இணைக்கவும்."
    ),
    "delete.session_deleted": (
        "'{title}' இந்த அமர்வுக்கு மட்டும் நிரந்தரமாக நீக்கப்பட்டது — "
        "நீக்கங்களைச் சேமிக்க Supabase இணைக்கவும்."
    ),
    "delete.failed": "'{title}' ஐ நீக்க முடியவில்லை: {error}",
    "delete.not_found": "id {id} உடன் ஆவணம் எதுவும் இல்லை — அது ஏற்கனவே நீக்கப்பட்டிருக்கலாம்.",

    "chat.heading": "💬 பொது சுகாதார வழிகாட்டுதலைக் கேளுங்கள்",
    "chat.welcome": (
        "வணக்கம்! நான் **கேர்சிங்க் AI**, உங்கள் பொது சுகாதார வழிகாட்டி உதவியாளர். "
        "செயலில் உள்ள பரவல் நெறிமுறைகள், தடுப்பூசி வழிகாட்டுதல்கள் அல்லது சுகாதார "
        "அறிவுரைகள் குறித்து என்னிடம் கேளுங்கள்."
    ),
    "chat.input_placeholder": "தற்போதைய தடுப்பூசி நெறிமுறை என்ன?",
    "chat.spinner": "செயலில் உள்ள பொது சுகாதார வழிகாட்டுதல் தேடப்படுகிறது...",
    "chat.searching": "🔍 {filters} அடிப்படையில் தேடல் — இவற்றைப் பக்கப்பட்டியில் மாற்றவும்.",
    "chat.filter_status": "நிலை **{status}**",
    "chat.filter_status_any": "நிலை **செயலில்** (அரட்டை எப்போதும் செயலில் உள்ள வழிகாட்டுதலிலிருந்தே பதிலளிக்கும்)",
    "chat.filter_dates": "அமல் **{date_from} → {date_to}**",
    "chat.filter_keyword": "முக்கியச்சொல் **{keyword}**",
    "chat.sources": "📌 **ஆதாரங்கள் & மேற்கோள்கள்** ({count})",
    "chat.sources_stale": " — {count} செயலற்ற வழிகாட்டுதலிலிருந்து",
    "chat.sources_scored": " · உங்கள் கேள்விக்கான தொடர்பின் அடிப்படையில் வரிசைப்படுத்தப்பட்டது",
    "chat.citation_meta": "பக்கம் {page} · பதிப்பு {version} · அமல் {effective}",
    "chat.passage_preview": "🔍 பகுதி முன்னோட்டம் — {title}, பக்கம் {page}",
    "chat.highlight_note": "சிறப்பிக்கப்பட்ட சொற்கள் உங்கள் கேள்வியிலிருந்து எடுக்கப்பட்டவை.",

    "chat.chips_intro": "✨ எங்கு தொடங்குவது எனத் தெரியவில்லையா? இவற்றில் ஒன்றை முயற்சிக்கவும்:",
    "chat.prompt.1": "தற்போதைய தட்டம்மை தடுப்பூசி அட்டவணை என்ன?",
    "chat.prompt.2": "சந்தேகத்திற்குரிய பரவலை எப்படிப் புகாரளிப்பது?",
    "chat.prompt.3": "வீட்டு வருகைக்கு எந்த PPE தேவை?",
    "chat.prompt.4": "காலரா சிகிச்சை வழிகாட்டுதல் மாறியுள்ளதா?",

    "chat.copy": "📋 நகலெடு",
    "chat.copy_hint": "பெட்டியின் மேல் சுட்டியை வைத்து, பதிலை நகலெடுக்க நகல் ஐகானைக் கிளிக் செய்யவும்.",
    "chat.export_pdf": "📄 PDF",
    "chat.export_pdf_help": "இந்தப் பதிலையும் அதன் மேற்கோள்களையும் PDF சுருக்கமாகப் பதிவிறக்கவும்.",
    "chat.export_pdf_unavailable": "PDF ஏற்றுமதிக்கு PyMuPDF தேவை — `pip install pymupdf` இயக்கவும்.",
    "chat.export_txt": "⬇️ TXT",
    "chat.export_txt_help": "இந்தப் பதிலையும் அதன் மேற்கோள்களையும் எளிய உரையாகப் பதிவிறக்கவும்.",
    "chat.export_note": "பதிவிறக்கங்கள் ஆங்கிலத்தில் உள்ளன — அவை மூல வழிகாட்டி ஆவணங்களைப் பிரதிபலிக்கின்றன.",

    "conflict.title_warning": "முரண்பட்ட வழிகாட்டுதல் கண்டறியப்பட்டது",
    "conflict.title_danger": "ஆவணப் பதிப்புகளுக்கு இடையே முரண்பட்ட வழிகாட்டுதல்",
    "conflict.footer": (
        "இந்தப் பதிலின்படி செயல்படுவதற்கு முன், கீழுள்ள மேற்கோள்களை சமீபத்திய "
        "செயலில் உள்ள வழிகாட்டுதலுடன் ஒப்பிட்டுப் பாருங்கள்."
    ),
    "conflict.fallback": "மீட்டெடுக்கப்பட்ட ஆவணங்கள் வெவ்வேறு வழிகாட்டுதலை வழங்குகின்றன.",

    "upload.heading": "⬆️ அங்கீகரிக்கப்பட்ட வழிகாட்டி PDF ஐப் பதிவேற்று",
    "upload.caption": "கீழே PDF ஐ இழுத்து விடவும், அல்லது உலாவ கிளிக் செய்யவும். அங்கீகரிக்கப்பட்ட வழிகாட்டுதல் மட்டும்.",
    "upload.title_label": "ஆவணத் தலைப்பு",
    "upload.title_placeholder": "எ.கா., குழந்தை நோய்த்தடுப்பு வழிகாட்டி",
    "upload.version_label": "பதிப்பு",
    "upload.date_label": "அமல் தேதி",
    "upload.file_label": "PDF கோப்பை இங்கே விடவும், அல்லது உலாவ கிளிக் செய்யவும்",
    "upload.file_help": "இந்த MVP இல் PDF ஆவணங்கள் மட்டுமே ஆதரிக்கப்படுகின்றன.",
    "upload.submit": "பதிவேற்றி அட்டவணைப்படுத்து",
    "upload.processing": "'{title}' செயலாக்கப்படுகிறது... உரை பிரித்தெடுத்தல், துண்டாக்கம் மற்றும் உட்பொதிப்பு.",
    "upload.indexing": "'{title}' அறிவுத் தளத்தில் அட்டவணைப்படுத்தப்படுகிறது...",
    "upload.success": (
        "'{title}' ({filename}) செயலாக்கப்பட்டு அறிவுத் தளத்தில் சேர்க்கப்பட்டது — "
        "**{pages} பக்கங்கள்**, **{chunks} துண்டுகள்** அட்டவணைப்படுத்தப்பட்டன."
    ),
    "upload.failed": "'{title}' ஐ செயலாக்க முடியவில்லை: {error}",
    "upload.missing_fields": "ஆவணத் தலைப்பை நிரப்பி, ஒரு PDF கோப்பைத் தேர்ந்தெடுக்கவும்.",
    # ── Chat history drawer ──────────────────────────────────────────────────
    "history.heading": "🕓 உரையாடல் வரலாறு",
    "history.new_chat": "➕ புதிய உரையாடல்",
    "history.new_chat_help": "புதிய உரையாடலைத் தொடங்கவும். தற்போதையது சேமிக்கப்பட்டே இருக்கும்.",
    "history.recent": "சமீபத்திய உரையாடல்கள் ({count})",
    "history.empty": "இதுவரை சேமிக்கப்பட்ட உரையாடல் இல்லை — ஒரு கேள்வி கேளுங்கள், இங்கே தோன்றும்.",
    "history.unavailable": (
        "உரையாடல் வரலாறு தற்போது கிடைக்கவில்லை — இந்த உரையாடல் இந்தச் சாதனத்தில் "
        "மட்டுமே உள்ளது, பக்கத்தை மூடினால் அழிந்துவிடும்."
    ),
    "history.untitled": "தலைப்பில்லா உரையாடல்",
    "history.open_help": "இந்த உரையாடலைத் திறக்கவும் — கடைசியாகச் செயலில் {when}.",
    "history.rename_help": "இந்த உரையாடலின் பெயரை மாற்று",
    "history.rename_label": "உரையாடல் தலைப்பு",
    "history.rename_save": "சேமி",
    "history.rename_cancel": "ரத்து",
    "history.renamed": "'{title}' எனப் பெயர் மாற்றப்பட்டது.",
    "history.rename_failed": "'{title}' பெயரை மாற்ற முடியவில்லை.",
    "history.delete_help": "இந்த உரையாடலை நீக்கு",
    "history.deleted": "'{title}' நீக்கப்பட்டது.",
    "history.delete_failed": "'{title}' நீக்க முடியவில்லை.",
    "history.delete_missing": "அந்த உரையாடல் இப்போது இல்லை.",
    "history.just_now": "இப்போதுதான்",
    "history.minutes_ago": "{count} நிமிடங்களுக்கு முன்",
    "history.hours_ago": "{count} மணி நேரத்திற்கு முன்",
    "history.days_ago": "{count} நாட்களுக்கு முன்",

    # ── Answer feedback ──────────────────────────────────────────────────────
    "feedback.prompt": "இந்தப் பதில் பயனுள்ளதாக இருந்ததா?",
    "feedback.up_help": "இந்தப் பதில் சரியாகவும் பயனுள்ளதாகவும் இருந்தது.",
    "feedback.down_help": "இந்தப் பதில் தவறானது, முழுமையற்றது அல்லது பயனற்றது.",
    "feedback.thanks_up": "✅ நன்றி — பயனுள்ளதாகப் பதிவு செய்யப்பட்டது.",
    "feedback.thanks_down": "நன்றி — வழிகாட்டுதல் குழுவின் மறுஆய்வுக்குப் பதிவு செய்யப்பட்டது.",
    "feedback.thanks_down_comment": "நன்றி — உங்கள் குறிப்பு வழிகாட்டுதல் குழுவுக்கு அனுப்பப்பட்டது.",
    "feedback.not_saved": "⚠️ இந்தச் சாதனத்தில் மட்டும் பதிவு — கருத்துச் சேவையை அணுக முடியவில்லை.",
    "feedback.comment_label": "இந்தப் பதிலில் என்ன தவறு? (விருப்பத்தேர்வு)",
    "feedback.comment_placeholder": "எ.கா. காலாவதியான நெறிமுறையை மேற்கோள் காட்டியது, அளவு அட்டவணை விடுபட்டது",
    "feedback.comment_send": "அனுப்பு",
    "feedback.comment_skip": "தவிர்",

    # ── Voice input ──────────────────────────────────────────────────────────
    "voice.heading": "🎙️ குரலில் கேளுங்கள்",
    "voice.intro": "உங்கள் கேள்வியைப் பதிவு செய்து, கேட்டுப் பார்த்து, கேட்பதற்கு முன் எழுத்துப்படியைச் சரிபாருங்கள்.",
    "voice.record_label": "உங்கள் கேள்வியைப் பதிவு செய்யுங்கள்",
    "voice.record_help": "பதிவைத் தொடங்க மைக்ரோஃபோனைத் தட்டவும், நிறுத்த மீண்டும் தட்டவும்.",
    "voice.recorder_unsupported": (
        "இந்த Streamlit பதிப்பில் மைக்ரோஃபோன் பதிவி இல்லை — அதற்குப் பதிலாக ஒரு "
        "ஒலிக்கோப்பைப் பதிவேற்றவும், அல்லது Streamlit 1.41+ க்கு மேம்படுத்தவும்."
    ),
    "voice.upload_label": "ஒலிக் கேள்வியைப் பதிவேற்றவும்",
    "voice.upload_help": "WAV, MP3, M4A, OGG, WEBM அல்லது FLAC.",
    "voice.too_large": "இந்தப் பதிவு {limit} MB-ஐ விடப் பெரியது — சுருக்கமான கேள்வியைப் பதிவு செய்யுங்கள்.",
    "voice.transcribe": "✍️ எழுத்தாக்கு",
    "voice.transcribe_help": "கேட்பதற்கு முன் பதிவை உரையாக மாற்றவும்.",
    "voice.transcribing": "உங்கள் பதிவு எழுத்தாக்கப்படுகிறது...",
    "voice.transcript_caption": "{seconds} வினாடிகளில் எழுத்தாக்கப்பட்டது — கேட்பதற்கு முன் சரிபாருங்கள்.",
    "voice.transcript_label": "எழுத்துப்படி",
    "voice.transcript_help": "பேச்சு-உரை மாற்றத்தில் ஏற்பட்ட பிழைகளைத் திருத்திவிட்டுக் கேளுங்கள்.",
    "voice.ask": "இந்தக் கேள்வியைக் கேள்",
    "voice.discard": "நீக்கு",
    "voice.empty_transcript": "அந்தப் பதிவில் பேச்சு எதுவும் கண்டறியப்படவில்லை — மைக்ரோஃபோனுக்கு அருகில் மீண்டும் முயலவும்.",
    "voice.failed": "அந்தப் பதிவை எழுத்தாக்க முடியவில்லை: {error}",

    # ── Retrieval confidence ─────────────────────────────────────────────────
    "confidence.high": "உயர் தொடர்பு",
    "confidence.medium": "நடுத்தரத் தொடர்பு",
    "confidence.low": "குறைந்த தொடர்பு",
    "confidence.badge": "{percent}%",
    "confidence.help": (
        "{label} — உங்கள் கேள்விக்கு இந்தப் பகுதி {percent}% தொடர்புடையது என "
        "மறுதரவரிசைப்படுத்தி மதிப்பிட்டது (மாதிரி மதிப்பெண் {score})."
    ),
    "confidence.detail": "மறுதரவரிசை #{rank} · {label} ({percent}%)",
    # ── Admin analytics dashboard ──────────────────────────────────
    "app.tab.analytics": "📊 பகுப்பாய்வு",
    "analytics.heading": "📊 நிர்வாகப் பகுப்பாய்வு டாஷ்போர்டு",
    "analytics.caption": "மீட்டெடுப்புக் குழாயின் செயல்பாட்டு நிலை, மற்றும் அதன் பதில்கள் கள ஊழியர்களுக்கு எவ்வளவு பயனுள்ளதாக இருந்தன.",
    "analytics.window_label": "கால அளவு",
    "analytics.window.1": "கடந்த 1 மணி நேரம்",
    "analytics.window.6": "கடந்த 6 மணி நேரம்",
    "analytics.window.24": "கடந்த 24 மணி நேரம்",
    "analytics.window.168": "கடந்த 7 நாட்கள்",
    "analytics.window.720": "கடந்த 30 நாட்கள்",
    "analytics.window_note": "நான்கு புள்ளிவிவரங்களும் {window} சார்ந்தவை.",
    "analytics.refresh": "🔄 புதுப்பி",
    "analytics.refresh_help": "சேமித்த புள்ளிவிவரங்களை நீக்கி அளவீட்டு அட்டவணைகளை மீண்டும் படி.",
    "analytics.no_data": "இந்தக் காலத்தில் இதுவரை எந்தக் கேள்வியும் பதிவாகவில்லை.",
    "analytics.unavailable": "அளவீடுகள் தற்போது கிடைக்கவில்லை — {error}",
    "analytics.unavailable_hint": "RAG குழாய் இயங்கும்போது இந்தப் புள்ளிவிவரங்களை Supabase-இல் எழுதுகிறது. இணைப்பைச் சரிபார்த்து மீண்டும் புதுப்பிக்கவும்.",
    "analytics.source_note": "{module} இலிருந்து படிக்கப்படுகிறது. புள்ளிவிவரங்கள் {seconds} வினாடிகள் சேமிக்கப்படும்.",
    "analytics.millis": "{value} மி.வி.",
    "analytics.seconds": "{value} வி.",
    "analytics.table.show": "தரவு அட்டவணையைக் காட்டு",
    "analytics.kpi.queries": "பதிலளிக்கப்பட்ட கேள்விகள்",
    "analytics.kpi.queries_sub": "மணிக்கு {rate}",
    "analytics.kpi.queries_help": "இந்தக் காலத்தில் பதிவான ஒவ்வொரு RAG குழாய் இயக்கமும் — வெற்றியோ இல்லையோ.",
    "analytics.kpi.latency": "சராசரிப் பதில் நேரம்",
    "analytics.kpi.latency_sub": "p95 {p95} · மிக மெதுவானது {max}",
    "analytics.kpi.latency_help": "கேள்வியிலிருந்து ஆதாரப்பூர்வப் பதில் வரையிலான மொத்த நேரம்.",
    "analytics.kpi.success": "வெற்றி விகிதம்",
    "analytics.kpi.success_sub": "{failed} தோல்வி அல்லது கால நிறைவு",
    "analytics.kpi.success_help": "பிழையின்றிப் பதிலளித்த கேள்விகளின் பங்கு.",
    "analytics.kpi.helpful": "பயனுள்ள பதில்கள்",
    "analytics.kpi.helpful_sub": "👍 {up} · 👎 {down}",
    "analytics.kpi.helpful_help": "மதிப்பிடப்பட்ட பதில்களில் கள ஊழியர் பயனுள்ளது எனக் குறித்தவற்றின் பங்கு.",
    "analytics.kpi.none": "—",
    "analytics.breakdown.heading": "நேரம் எங்கே செலவாகிறது",
    "analytics.breakdown.caption": "{count} கேள்விகளில் ஒவ்வொரு குழாய் நிலைக்கும் சராசரி மில்லி வினாடிகள்.",
    "analytics.stage.embedding": "உட்பொதிப்பு",
    "analytics.stage.retrieval": "மீட்டெடுப்பு",
    "analytics.stage.llm": "LLM பதில் உருவாக்கம்",
    "analytics.stage.other": "மற்றவை",
    "analytics.stage.other_help": "“மற்றவை” என்பதில் மறுதரவரிசை, முரண்பாடு கண்டறிதல், மற்றும் அளவிடப்பட்ட நிலைகளுக்கு இடையிலான நேரம் அடங்கும்.",
    "analytics.windows.heading": "கால அளவின்படி பதில் நேரம்",
    "analytics.windows.caption": "ஒவ்வொரு காலமும் ஒட்டுமொத்தமானது — 24 மணி நேரப் பட்டையில் கடந்த 1 மணி நேரமும் அடங்கும்.",
    "analytics.series.avg": "சராசரி",
    "analytics.series.p95": "95வது சதவீதம்",
    "analytics.quality.heading": "பதில் தரம்",
    "analytics.quality.caption": "{count} மதிப்பிடப்பட்ட பதில்களின் அடிப்படையில்.",
    "analytics.quality.none": "இந்தக் காலத்தில் எந்தப் பதிலும் மதிப்பிடப்படவில்லை.",
    "analytics.quality.summary": "{percent}% பயனுள்ளது — 👍 {helpful} · 👎 {unhelpful}",
    "analytics.comments.heading": "எதிர்மறை மதிப்பீட்டுக் குறிப்புகள்",
    "analytics.comments.none": "இந்தக் காலத்தில் எழுத்துப்பூர்வக் கருத்து இல்லை.",
    "analytics.slow.heading": "மிக மெதுவான கேள்விகள்",
    "analytics.slow.caption": "{threshold} மி.வி.-க்கும் மெதுவானவை, மெதுவானது முதலில்.",
    "analytics.slow.none": "எந்தக் கேள்வியும் {threshold} மி.வி.-ஐத் தாண்டவில்லை.",
    "analytics.slow.threshold_label": "மெதுவான கேள்வி வரம்பு (மி.வி.)",
    "analytics.slow.threshold_help": "இதைவிட மெதுவான கேள்விகள் கீழே பட்டியலிடப்படும்.",
    "analytics.failed.heading": "தோல்வி மற்றும் கால நிறைவுக் கேள்விகள்",
    "analytics.failed.caption": "பதில் கிடைக்காத இயக்கங்கள்: {count}. சமீபத்தியது முதலில்.",
    "analytics.failed.none": "எந்தத் தோல்வியும் பதிவாகவில்லை.",
    "analytics.session.heading": "இந்த உலாவி அமர்வின் குழாய் நேரங்கள்",
    "analytics.session.caption": "இதே செயல்பாட்டில் அளவிடப்பட்டது — அளவீட்டு அட்டவணைகள் கிடைக்காதபோதும் இது கிடைக்கும்.",
    "analytics.session.none": "இந்த அமர்வில் இதுவரை எந்தக் குழாய் செயல்பாடும் அளவிடப்படவில்லை — அரட்டைத் தாவலில் ஒரு கேள்வி கேளுங்கள்.",
    "analytics.col.stage": "நிலை",
    "analytics.col.ms": "மில்லி வினாடிகள்",
    "analytics.col.share": "பங்கு",
    "analytics.col.window": "காலம்",
    "analytics.col.metric": "அளவீடு",
    "analytics.col.query": "கேள்வி",
    "analytics.col.total": "மொத்தம்",
    "analytics.col.when": "எப்போது",
    "analytics.col.status": "நிலை",
    "analytics.col.error": "பிழை",
    "analytics.col.operation": "செயல்பாடு",
    "analytics.col.calls": "அழைப்புகள்",
    "analytics.col.avg_ms": "சராசரி மி.வி.",
    "analytics.col.vote": "மதிப்பீடு",
    "analytics.col.comment": "கருத்து",
    # ── Guideline management (admin) ───────────────────────────────
    "guidelines.heading": "🗂️ வழிகாட்டுதல் மேலாண்மை",
    "guidelines.caption": "அறிவுத் தளத்தின் ஒவ்வொரு ஆவணமும், மீட்டெடுப்பு அதில் எதைப் பார்க்கிறது, மற்றும் ஒன்றை நீக்கும் கட்டுப்பாடுகள்.",
    "guidelines.count": "{count} ஆவணங்கள் · {active} செயலில்",
    "guidelines.empty": "இதுவரை எந்த ஆவணமும் பதிவேற்றப்படவில்லை.",
    "guidelines.unavailable": "ஆவணப் பதிவேடு கிடைக்கவில்லை — {error}",
    "guidelines.session_only": "உள்ளூர் மாதிரித் தரவு காட்டப்படுகிறது — உண்மையான ஆவணங்களை நிர்வகிக்க Supabase-ஐ இணைக்கவும்.",
    "guidelines.refresh": "🔄 மீள்ஏற்று",
    "guidelines.refresh_help": "ஆவணப் பதிவேட்டையும் அதன் பகுதி எண்ணிக்கையையும் மீண்டும் படி.",
    "guidelines.indexed_unknown": "—",
    "guidelines.failed": "“{title} {version}” ஐப் புதுப்பிக்க முடியவில்லை: {error}",
    "guidelines.missing": "அந்த ஆவணம் இனி பதிவேட்டில் இல்லை.",
    "guidelines.col.title": "ஆவணம்",
    "guidelines.col.version": "பதிப்பு",
    "guidelines.col.status": "நிலை",
    "guidelines.col.effective": "அமலுக்கு",
    "guidelines.col.indexed": "பகுதிகள்",
    "guidelines.col.actions": "நிர்வாகச் செயல்கள்",
    "guidelines.action.archive": "காப்பகம்",
    "guidelines.action.archive_help": "இந்த ஆவணத்தை மீட்டெடுப்பிலிருந்து நீக்கு. பதிவும் பகுதிகளும் தக்கவைக்கப்படுவதால் மீட்டெடுக்க முடியும்.",
    "guidelines.action.supersede": "மாற்றப்பட்டது",
    "guidelines.action.supersede_help": "மாற்றுப் பதிப்பைப் பதிவேற்றாமலேயே இந்தப் பதிப்பை SUPERSEDED ஆக்கு.",
    "guidelines.action.needs_db": "ஆவண நிலையை மாற்ற Supabase-ஐ இணைக்கவும்.",
    "guidelines.action.no_change": "ஏற்கனவே {status} — இந்தச் செயலால் எதுவும் மாறாது.",
    "guidelines.confirm.archive_title": "“{title} {version}” ஐக் காப்பகப்படுத்தவா?",
    "guidelines.confirm.archive_body": "கள ஊழியர்களுக்கு இனி இந்த ஆவணத்திலிருந்து பதில் வராது. பதிவும் அட்டவணைப்படுத்தப்பட்ட பகுதிகளும் தக்கவைக்கப்படும், ஆவணத் தாவலிலிருந்து மீட்டெடுக்கலாம்.",
    "guidelines.confirm.supersede_title": "“{title} {version}” ஐ SUPERSEDED ஆக்கவா?",
    "guidelines.confirm.supersede_body": "இந்தப் பதிப்பு தேடலில் இருக்கும், ஆனால் காலாவதியாகக் குறிக்கப்படும்; இதை மேற்கோள் காட்டும் பதில்களில் பழைய-வழிகாட்டுதல் எச்சரிக்கை தோன்றும். மாற்று CareSync AI-க்கு வெளியே இருக்கும்போது இதைப் பயன்படுத்துங்கள்.",
    "guidelines.confirm.yes": "ஆம், செயல்படுத்து",
    "guidelines.confirm.no": "ரத்து",
    "guidelines.done.archive": "“{title} {version}” காப்பகப்படுத்தப்பட்டது.",
    "guidelines.done.supersede": "“{title} {version}” மாற்றப்பட்டதாகக் குறிக்கப்பட்டது.",
    "guidelines.sync.heading": "ஒத்திசைவு எச்சரிக்கைகள்",
    "guidelines.sync.none": "✅ {count} ஆவணங்களில் ஒத்திசைவுச் சிக்கல் எதுவும் இல்லை.",
    "guidelines.sync.footer": "பாதிக்கப்பட்ட வழிகாட்டுதலின்படி கள ஊழியர்கள் செயல்படும் முன் இவற்றைச் சரிசெய்யவும்.",
    "guidelines.sync.needs_db": "ஒத்திசைவுச் சோதனைகளுக்கு ஆவணப் பதிவேடு தேவை — Supabase-ஐ இணைக்கவும்.",
    "guidelines.sync.source_batch": "ஒத்திசைவு தொகுதிப் பணியால் குறிக்கப்பட்டது.",
    "guidelines.sync.source_local": "ஒத்திசைவு தொகுதிப் பணி இன்னும் எந்தக் குறியீட்டையும் வெளியிடவில்லை, எனவே இந்தச் சோதனைகள் பதிவேட்டில் நேரடியாக இயக்கப்பட்டன.",
    "guidelines.sync.unverified": "பகுதி எண்ணிக்கையைப் படிக்க முடியவில்லை, எனவே அட்டவணைப்படுத்தல் சோதிக்கப்படவில்லை.",
    "guidelines.sync.row_flag": "⚠️ {count}",
    "guidelines.sync.row_flag_help": "இந்த ஆவணத்தில் {count} ஒத்திசைவு எச்சரிக்கை உள்ளது — மேலே உள்ள பதாகைகளைப் பார்க்கவும்.",
    "guidelines.sync.batch": "தொகுதிப் பணியால் குறிக்கப்பட்டது",
    "guidelines.sync.duplicate_active": "பல ACTIVE பதிப்புகள்",
    "guidelines.sync.duplicate_active_detail": "“{title}” இன் {count} பதிப்புகள் ACTIVE எனக் குறிக்கப்பட்டுள்ளன ({versions}) — மீட்டெடுப்பு இவற்றில் எதிலிருந்தும் பதிலளிக்கலாம். சமீபத்தியது {newest}.",
    "guidelines.sync.not_indexed": "செயலில் ஆனால் அட்டவணைப்படுத்தப்படவில்லை",
    "guidelines.sync.not_indexed_detail": "“{title} {version}” ACTIVE ஆக உள்ளது, ஆனால் அட்டவணைப்படுத்தப்பட்ட பகுதிகள் இல்லை — மீட்டெடுப்பால் இதைப் பார்க்கவே முடியாது.",
    "guidelines.sync.future_effective": "இன்னும் அமலுக்கு வரவில்லை",
    "guidelines.sync.future_effective_detail": "“{title} {version}” ACTIVE ஆக உள்ளது, ஆனால் {date} முதல்தான் அமலுக்கு வரும்.",
    "guidelines.sync.no_effective_date": "அமல் தேதி இல்லை",
    "guidelines.sync.no_effective_date_detail": "“{title} {version}” ACTIVE ஆக உள்ளது, ஆனால் அமல் தேதி இல்லை, எனவே அதன் நடப்புத்தன்மையைச் சோதிக்க முடியாது.",
}


_ES: Dict[str, str] = {
    "app.page_title": "CareSync AI — Pregunta. Verifica. Actúa.",
    "app.title": "CareSync AI — Pregunta. Verifica. Actúa.",
    "app.tagline": "Asistente de orientación en salud pública con IA para personal de campo",
    "app.sidebar_title": "CareSync AI",
    "app.sidebar_caption": "Sprint 2 MVP",
    "app.sidebar_about": (
        "Generación aumentada por recuperación para personal de salud pública.\n\n"
        "Cada respuesta se basa en documentos de orientación oficiales y "
        "versionados, y viene respaldada por citas."
    ),
    "app.tab.chat": "💬 Asistente de chat",
    "app.tab.documents": "📄 Documentos cargados",
    "app.tab.upload": "⬆️ Cargar directriz",

    "lang.heading": "🌐 Idioma",
    "lang.label": "Idioma de la interfaz",
    "lang.help": "Cambia las etiquetas, los botones y los mensajes de toda la aplicación.",
    "lang.note": (
        "Solo el idioma de la interfaz: los documentos de orientación, los pasajes "
        "recuperados y las respuestas se mantienen en su idioma original."
    ),

    "status.ACTIVE": "ACTIVO",
    "status.SUPERSEDED": "SUSTITUIDO",
    "status.ARCHIVED": "ARCHIVADO",
    "status.any": "Todos los estados",
    "status.hint.ACTIVE": "Orientación vigente: se puede actuar con seguridad.",
    "status.hint.SUPERSEDED": "Existe una versión más reciente de este documento: verifique antes de actuar.",
    "status.hint.ARCHIVED": "Retirado de la orientación vigente: se conserva solo para auditoría.",

    "filters.heading": "🔍 Filtros de búsqueda",
    "filters.title_label": "El título del documento contiene",
    "filters.title_placeholder": "p. ej. Vacunación",
    "filters.title_help": "Filtra la pestaña Documentos cargados.",
    "filters.status_label": "Estado del documento",
    "filters.status_help": "Con 'Todos los estados', el chat siempre responde a partir de orientación ACTIVA.",
    "filters.use_dates": "Filtrar por fecha de entrada en vigor",
    "filters.date_label": "Rango de fechas de vigencia",
    "filters.date_help": "Límites inferior y superior inclusivos de la fecha de vigencia del documento.",
    "filters.date_order_warning": "La fecha inicial es posterior a la final: no se muestran resultados.",
    "filters.keyword_label": "Refuerzo por palabra clave (opcional)",
    "filters.keyword_placeholder": "p. ej. dosis de sarampión",
    "filters.keyword_help": "Se envía al recuperador híbrido como palabra clave explícita de texto completo.",
    "filters.reset": "Restablecer filtros",

    "docs.heading": "📄 Documentos de salud pública cargados",
    "docs.empty": "Aún no se ha cargado ningún documento. Use la pestaña **Cargar directriz** para añadir uno.",
    "docs.session_notice": "⚠️ Mostrando datos de la sesión: Supabase no está disponible, los cambios de estado no se guardarán.",
    "docs.showing": "Mostrando **{visible}** de **{total}** documentos · {active} activos — fíltrelos en la barra lateral.",
    "docs.no_match": "Ningún documento coincide con los filtros actuales. Amplíe el rango de fechas o el estado.",
    "docs.version_effective": "Versión {version} · Vigente {effective}",
    "docs.set_status": "Establecer estado",
    "docs.apply": "Aplicar",
    "docs.apply_help": "Mueve este documento al estado seleccionado.",
    "docs.delete": "🗑️ Eliminar",
    "docs.delete_help": "Archivar o eliminar definitivamente este documento.",
    "docs.timeline": "🕓 Historial de versiones — {title}",
    "docs.status_changed": "'{title}' ahora está {status}.",
    "docs.status_session_only": (
        "'{title}' se ha puesto en {status} solo para esta sesión: "
        "conecte Supabase para conservar los cambios de estado."
    ),
    "docs.status_failed": "No se pudo actualizar '{title}': {error}",
    "docs.status_missing": "No se encontró ningún documento con id {id}: puede que se haya eliminado.",

    "timeline.empty": "Todavía no hay historial de versiones para este documento.",
    "timeline.this_row": "esta fila",
    "timeline.effective": "Vigente {date}",
    "timeline.superseded_note": " · reemplazado por una versión posterior",

    "delete.modal_title": "¿Eliminar este documento?",
    "delete.inline_title": "🗑️ ¿Eliminar este documento?",
    "delete.mode_question": "¿Cómo desea eliminar este documento?",
    "delete.mode.archive": "Archivarlo (recuperable)",
    "delete.mode.permanent": "Eliminar definitivamente",
    "delete.mode.archive_caption": (
        "Conserva el registro y sus citas para auditoría, pero deja de usarse en las respuestas."
    ),
    "delete.mode.permanent_caption": (
        "Borra el documento y sus pasajes indexados. Esta acción no se puede deshacer."
    ),
    "delete.permanent_warning": (
        "La eliminación definitiva también borra todos los pasajes indexados de este "
        "documento, por lo que las respuestas anteriores ya no podrán rastrearse hasta él."
    ),
    "delete.ack": "Entiendo que esta acción no se puede deshacer.",
    "delete.session_notice": "Supabase no está disponible, así que esto solo afecta a la sesión actual.",
    "delete.cancel": "Cancelar",
    "delete.confirm_archive": "Archivar documento",
    "delete.confirm_permanent": "Eliminar definitivamente",
    "delete.done_archived": "'{title}' se ha archivado.",
    "delete.done_deleted": "'{title}' se ha eliminado definitivamente.",
    "delete.session_archived": (
        "'{title}' se ha archivado solo para esta sesión: "
        "conecte Supabase para conservar las eliminaciones."
    ),
    "delete.session_deleted": (
        "'{title}' se ha eliminado definitivamente solo para esta sesión: "
        "conecte Supabase para conservar las eliminaciones."
    ),
    "delete.failed": "No se pudo eliminar '{title}': {error}",
    "delete.not_found": "No se encontró ningún documento con id {id}: puede que ya se haya eliminado.",

    "chat.heading": "💬 Consulte la orientación de salud pública",
    "chat.welcome": (
        "¡Hola! Soy **CareSync AI**, su asistente de orientación en salud pública. "
        "Pregúnteme sobre protocolos de brotes vigentes, directrices de vacunación "
        "o avisos sanitarios."
    ),
    "chat.input_placeholder": "¿Cuál es el protocolo de vacunación vigente?",
    "chat.spinner": "Buscando en la orientación de salud pública vigente...",
    "chat.searching": "🔍 Buscando {filters} — cámbielos en la barra lateral.",
    "chat.filter_status": "estado **{status}**",
    "chat.filter_status_any": "estado **ACTIVO** (el chat siempre responde desde orientación vigente)",
    "chat.filter_dates": "vigencia **{date_from} → {date_to}**",
    "chat.filter_keyword": "palabra clave **{keyword}**",
    "chat.sources": "📌 **Fuentes y citas** ({count})",
    "chat.sources_stale": " — {count} de orientación no vigente",
    "chat.sources_scored": " · ordenadas por relevancia para tu pregunta",
    "chat.citation_meta": "Página {page} · Versión {version} · Vigente {effective}",
    "chat.passage_preview": "🔍 Vista previa del pasaje — {title}, página {page}",
    "chat.highlight_note": "Los términos resaltados provienen de su pregunta.",

    "chat.chips_intro": "✨ ¿No sabe por dónde empezar? Pruebe una de estas:",
    "chat.prompt.1": "¿Cuál es el calendario actual de vacunación contra el sarampión?",
    "chat.prompt.2": "¿Cómo notifico un brote sospechoso?",
    "chat.prompt.3": "¿Qué EPP se requiere para una visita domiciliaria?",
    "chat.prompt.4": "¿Ha cambiado la orientación sobre el tratamiento del cólera?",

    "chat.copy": "📋 Copiar",
    "chat.copy_hint": "Pase el cursor sobre el cuadro y haga clic en el icono de copiar.",
    "chat.export_pdf": "📄 PDF",
    "chat.export_pdf_help": "Descargue esta respuesta y sus citas como resumen en PDF.",
    "chat.export_pdf_unavailable": "La exportación a PDF necesita PyMuPDF: instálelo con `pip install pymupdf`.",
    "chat.export_txt": "⬇️ TXT",
    "chat.export_txt_help": "Descargue esta respuesta y sus citas como texto plano.",
    "chat.export_note": "Las descargas están en inglés: reflejan los documentos de orientación originales.",

    "conflict.title_warning": "Se detectó orientación contradictoria",
    "conflict.title_danger": "Orientación contradictoria entre versiones del documento",
    "conflict.footer": (
        "Contraste las citas siguientes con la orientación ACTIVA más reciente "
        "antes de actuar según esta respuesta."
    ),
    "conflict.fallback": "Los documentos recuperados ofrecen orientaciones distintas.",

    "upload.heading": "⬆️ Cargar PDF de orientación aprobada",
    "upload.caption": "Arrastre y suelte un PDF abajo, o haga clic para explorar. Solo orientación aprobada.",
    "upload.title_label": "Título del documento",
    "upload.title_placeholder": "p. ej., Directriz de inmunización infantil",
    "upload.version_label": "Versión",
    "upload.date_label": "Fecha de vigencia",
    "upload.file_label": "Suelte el archivo PDF aquí, o haga clic para explorar",
    "upload.file_help": "En este MVP solo se admiten documentos PDF.",
    "upload.submit": "Cargar e indexar orientación",
    "upload.processing": "Procesando '{title}'... extrayendo texto, fragmentando y generando embeddings.",
    "upload.indexing": "Indexando '{title}' en la base de conocimiento...",
    "upload.success": (
        "'{title}' ({filename}) se procesó y se añadió a la base de conocimiento — "
        "**{pages} páginas**, **{chunks} fragmentos** indexados."
    ),
    "upload.failed": "No se pudo procesar '{title}': {error}",
    "upload.missing_fields": "Complete el título del documento y seleccione un archivo PDF.",
    # ── Chat history drawer ──────────────────────────────────────────────────
    "history.heading": "🕓 Historial de chats",
    "history.new_chat": "➕ Chat nuevo",
    "history.new_chat_help": "Inicia una conversación nueva. La actual queda guardada.",
    "history.recent": "Conversaciones recientes ({count})",
    "history.empty": "Aún no hay conversaciones guardadas — haz una pregunta y este chat aparecerá aquí.",
    "history.unavailable": (
        "El historial de chats no está disponible ahora mismo — esta conversación "
        "solo se guarda en este dispositivo y se perderá al cerrar la página."
    ),
    "history.untitled": "Chat sin título",
    "history.open_help": "Abrir esta conversación — última actividad {when}.",
    "history.rename_help": "Cambiar el nombre de esta conversación",
    "history.rename_label": "Título de la conversación",
    "history.rename_save": "Guardar",
    "history.rename_cancel": "Cancelar",
    "history.renamed": "Renombrada como '{title}'.",
    "history.rename_failed": "No se pudo renombrar '{title}'.",
    "history.delete_help": "Eliminar esta conversación",
    "history.deleted": "'{title}' se eliminó.",
    "history.delete_failed": "No se pudo eliminar '{title}'.",
    "history.delete_missing": "Esa conversación ya no existe.",
    "history.just_now": "ahora mismo",
    "history.minutes_ago": "hace {count} min",
    "history.hours_ago": "hace {count} h",
    "history.days_ago": "hace {count} d",

    # ── Answer feedback ──────────────────────────────────────────────────────
    "feedback.prompt": "¿Te resultó útil esta respuesta?",
    "feedback.up_help": "Esta respuesta fue precisa y útil.",
    "feedback.down_help": "Esta respuesta fue incorrecta, incompleta o poco útil.",
    "feedback.thanks_up": "✅ Gracias — registrada como útil.",
    "feedback.thanks_down": "Gracias — registrada para revisión del equipo de orientación.",
    "feedback.thanks_down_comment": "Gracias — tu comentario llegó al equipo de orientación.",
    "feedback.not_saved": "⚠️ Registrada solo en este dispositivo — el servicio de valoraciones no responde.",
    "feedback.comment_label": "¿Qué falló en esta respuesta? (opcional)",
    "feedback.comment_placeholder": "p. ej. citó un protocolo sustituido, omitió la tabla de dosis",
    "feedback.comment_send": "Enviar",
    "feedback.comment_skip": "Omitir",

    # ── Voice input ──────────────────────────────────────────────────────────
    "voice.heading": "🎙️ Preguntar por voz",
    "voice.intro": "Graba tu pregunta, escúchala y revisa la transcripción antes de enviarla.",
    "voice.record_label": "Graba tu pregunta",
    "voice.record_help": "Toca el micrófono para grabar y otra vez para detener.",
    "voice.recorder_unsupported": (
        "Esta versión de Streamlit no tiene grabadora de micrófono — sube un "
        "archivo de audio en su lugar, o actualiza a Streamlit 1.41 o posterior."
    ),
    "voice.upload_label": "Sube una pregunta en audio",
    "voice.upload_help": "WAV, MP3, M4A, OGG, WEBM o FLAC.",
    "voice.too_large": "Esa grabación supera los {limit} MB — graba una pregunta más corta.",
    "voice.transcribe": "✍️ Transcribir",
    "voice.transcribe_help": "Convierte la grabación en texto antes de enviarla.",
    "voice.transcribing": "Transcribiendo tu grabación...",
    "voice.transcript_caption": "Transcrita en {seconds} s — revísala antes de preguntar.",
    "voice.transcript_label": "Transcripción",
    "voice.transcript_help": "Corrige lo que el reconocimiento de voz haya entendido mal y pregunta.",
    "voice.ask": "Hacer esta pregunta",
    "voice.discard": "Descartar",
    "voice.empty_transcript": "No se detectó voz en esa grabación — inténtalo otra vez, más cerca del micrófono.",
    "voice.failed": "No se pudo transcribir esa grabación: {error}",

    # ── Retrieval confidence ─────────────────────────────────────────────────
    "confidence.high": "Relevancia alta",
    "confidence.medium": "Relevancia media",
    "confidence.low": "Relevancia baja",
    "confidence.badge": "{percent}%",
    "confidence.help": (
        "{label} — el reordenador calificó este pasaje como {percent}% relevante "
        "para tu pregunta (puntuación del modelo {score})."
    ),
    "confidence.detail": "Reordenado n.º {rank} · {label} ({percent}%)",
    # ── Admin analytics dashboard ──────────────────────────────────
    "app.tab.analytics": "📊 Analítica",
    "analytics.heading": "📊 Panel de analítica de administración",
    "analytics.caption": "Salud operativa del sistema de recuperación y utilidad de sus respuestas para el personal de campo.",
    "analytics.window_label": "Periodo",
    "analytics.window.1": "Última hora",
    "analytics.window.6": "Últimas 6 horas",
    "analytics.window.24": "Últimas 24 horas",
    "analytics.window.168": "Últimos 7 días",
    "analytics.window.720": "Últimos 30 días",
    "analytics.window_note": "Las cuatro cifras corresponden a: {window}.",
    "analytics.refresh": "🔄 Actualizar",
    "analytics.refresh_help": "Descarta las cifras en caché y vuelve a leer las tablas de métricas.",
    "analytics.no_data": "Aún no se ha registrado ninguna consulta en este periodo.",
    "analytics.unavailable": "Las métricas no están disponibles ahora mismo — {error}",
    "analytics.unavailable_hint": "El sistema RAG escribe estas cifras en Supabase mientras funciona. Comprueba la conexión y actualiza.",
    "analytics.source_note": "Leyendo de {module}. Las cifras se guardan en caché {seconds} s.",
    "analytics.millis": "{value} ms",
    "analytics.seconds": "{value} s",
    "analytics.table.show": "Ver tabla de datos",
    "analytics.kpi.queries": "Consultas respondidas",
    "analytics.kpi.queries_sub": "{rate} por hora",
    "analytics.kpi.queries_help": "Cada ejecución del sistema RAG registrada en este periodo, con éxito o sin él.",
    "analytics.kpi.latency": "Respuesta media",
    "analytics.kpi.latency_sub": "p95 {p95} · más lenta {max}",
    "analytics.kpi.latency_help": "Tiempo total desde la pregunta hasta la respuesta fundamentada.",
    "analytics.kpi.success": "Tasa de éxito",
    "analytics.kpi.success_sub": "{failed} fallaron o expiraron",
    "analytics.kpi.success_help": "Proporción de consultas que devolvieron respuesta sin error ni expiración.",
    "analytics.kpi.helpful": "Respuestas útiles",
    "analytics.kpi.helpful_sub": "👍 {up} · 👎 {down}",
    "analytics.kpi.helpful_help": "Proporción de respuestas valoradas que el personal de campo marcó como útiles.",
    "analytics.kpi.none": "—",
    "analytics.breakdown.heading": "En qué se va el tiempo",
    "analytics.breakdown.caption": "Milisegundos medios por etapa a lo largo de {count} consultas.",
    "analytics.stage.embedding": "Vectorización",
    "analytics.stage.retrieval": "Recuperación",
    "analytics.stage.llm": "Generación del LLM",
    "analytics.stage.other": "Otros",
    "analytics.stage.other_help": "“Otros” incluye el reordenamiento, la detección de contradicciones y los huecos entre etapas medidas.",
    "analytics.windows.heading": "Tiempo de respuesta por periodo",
    "analytics.windows.caption": "Cada periodo es acumulativo: las barras de 24 horas incluyen la última hora.",
    "analytics.series.avg": "Media",
    "analytics.series.p95": "Percentil 95",
    "analytics.quality.heading": "Calidad de las respuestas",
    "analytics.quality.caption": "Sobre {count} respuestas valoradas.",
    "analytics.quality.none": "Ninguna respuesta se ha valorado en este periodo.",
    "analytics.quality.summary": "{percent}% útiles — 👍 {helpful} · 👎 {unhelpful}",
    "analytics.comments.heading": "Qué decían los votos negativos",
    "analytics.comments.none": "Sin comentarios escritos en este periodo.",
    "analytics.slow.heading": "Consultas más lentas",
    "analytics.slow.caption": "Más lentas de {threshold} ms, de mayor a menor.",
    "analytics.slow.none": "Ninguna consulta superó los {threshold} ms.",
    "analytics.slow.threshold_label": "Umbral de consulta lenta (ms)",
    "analytics.slow.threshold_help": "Las consultas más lentas que esto se listan abajo.",
    "analytics.failed.heading": "Consultas fallidas y expiradas",
    "analytics.failed.caption": "Ejecuciones sin respuesta: {count}. Las más recientes primero.",
    "analytics.failed.none": "Sin fallos registrados.",
    "analytics.session.heading": "Tiempos de esta sesión del navegador",
    "analytics.session.caption": "Medidos en este proceso — disponibles aunque las tablas de métricas no lo estén.",
    "analytics.session.none": "Aún no se ha medido ninguna operación en esta sesión — haz una pregunta en la pestaña de chat.",
    "analytics.col.stage": "Etapa",
    "analytics.col.ms": "Milisegundos",
    "analytics.col.share": "Proporción",
    "analytics.col.window": "Periodo",
    "analytics.col.metric": "Métrica",
    "analytics.col.query": "Pregunta",
    "analytics.col.total": "Total",
    "analytics.col.when": "Cuándo",
    "analytics.col.status": "Estado",
    "analytics.col.error": "Error",
    "analytics.col.operation": "Operación",
    "analytics.col.calls": "Llamadas",
    "analytics.col.avg_ms": "Media ms",
    "analytics.col.vote": "Voto",
    "analytics.col.comment": "Comentario",
    # ── Guideline management (admin) ───────────────────────────────
    "guidelines.heading": "🗂️ Gestión de directrices",
    "guidelines.caption": "Todos los documentos de la base de conocimiento, lo que la recuperación ve de ellos y los controles para retirar uno.",
    "guidelines.count": "{count} documentos · {active} vigentes",
    "guidelines.empty": "Todavía no se ha subido ningún documento.",
    "guidelines.unavailable": "El registro de documentos no está disponible — {error}",
    "guidelines.session_only": "Mostrando datos de ejemplo locales — conecta Supabase para gestionar documentos reales.",
    "guidelines.refresh": "🔄 Recargar",
    "guidelines.refresh_help": "Vuelve a leer el registro de documentos y sus recuentos de pasajes.",
    "guidelines.indexed_unknown": "—",
    "guidelines.failed": "No se pudo actualizar «{title} {version}»: {error}",
    "guidelines.missing": "Ese documento ya no existe en el registro.",
    "guidelines.col.title": "Documento",
    "guidelines.col.version": "Versión",
    "guidelines.col.status": "Estado",
    "guidelines.col.effective": "Vigencia",
    "guidelines.col.indexed": "Pasajes",
    "guidelines.col.actions": "Acciones de administración",
    "guidelines.action.archive": "Archivar",
    "guidelines.action.archive_help": "Retira este documento de la recuperación. Se conservan el registro y sus pasajes, así que puede restaurarse.",
    "guidelines.action.supersede": "Sustituir",
    "guidelines.action.supersede_help": "Marca esta versión como SUPERSEDED sin subir un reemplazo.",
    "guidelines.action.needs_db": "Conecta Supabase para cambiar el estado de un documento.",
    "guidelines.action.no_change": "Ya está {status}: esta acción no cambiaría nada.",
    "guidelines.confirm.archive_title": "¿Archivar «{title} {version}»?",
    "guidelines.confirm.archive_body": "El personal de campo dejará de recibir respuestas de este documento. Se conservan el registro y sus pasajes indexados, y puede restaurarse desde la pestaña de documentos.",
    "guidelines.confirm.supersede_title": "¿Marcar «{title} {version}» como SUPERSEDED?",
    "guidelines.confirm.supersede_body": "Esta versión seguirá siendo consultable pero quedará marcada como desactualizada, y toda respuesta que la cite llevará un aviso de orientación no vigente. Úsalo cuando el reemplazo exista fuera de CareSync AI.",
    "guidelines.confirm.yes": "Sí, aplicar",
    "guidelines.confirm.no": "Cancelar",
    "guidelines.done.archive": "«{title} {version}» está archivado.",
    "guidelines.done.supersede": "«{title} {version}» está marcado como sustituido.",
    "guidelines.sync.heading": "Avisos de sincronización",
    "guidelines.sync.none": "✅ Sin problemas de sincronización en {count} documentos.",
    "guidelines.sync.footer": "Resuélvelos antes de que el personal de campo actúe según la orientación afectada.",
    "guidelines.sync.needs_db": "Las comprobaciones necesitan el registro de documentos — conecta Supabase para ejecutarlas.",
    "guidelines.sync.source_batch": "Marcado por el proceso por lotes de sincronización.",
    "guidelines.sync.source_local": "El proceso por lotes aún no publica marcas, así que estas comprobaciones se ejecutaron en vivo sobre el registro.",
    "guidelines.sync.unverified": "No se pudieron leer los recuentos de pasajes, así que no se comprobó la indexación.",
    "guidelines.sync.row_flag": "⚠️ {count}",
    "guidelines.sync.row_flag_help": "Este documento tiene {count} aviso(s) de sincronización — mira los banners de arriba.",
    "guidelines.sync.batch": "Marcado por el proceso por lotes",
    "guidelines.sync.duplicate_active": "Varias versiones ACTIVE",
    "guidelines.sync.duplicate_active_detail": "«{title}» tiene {count} versiones marcadas ACTIVE ({versions}): la recuperación puede responder desde cualquiera. La más reciente es {newest}.",
    "guidelines.sync.not_indexed": "Vigente pero sin indexar",
    "guidelines.sync.not_indexed_detail": "«{title} {version}» está ACTIVE pero no tiene pasajes indexados: la recuperación no puede verlo.",
    "guidelines.sync.future_effective": "Todavía no vigente",
    "guidelines.sync.future_effective_detail": "«{title} {version}» está ACTIVE pero no entra en vigor hasta el {date}.",
    "guidelines.sync.no_effective_date": "Falta la fecha de vigencia",
    "guidelines.sync.no_effective_date_detail": "«{title} {version}» está ACTIVE sin fecha de vigencia, así que no se puede comprobar su actualidad.",
}


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": _EN,
    "hi": _HI,
    "ta": _TA,
    "es": _ES,
}
