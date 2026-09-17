"""
components/upload.py
---------------------
Drag-and-drop PDF uploader with metadata input fields (title, version,
effective date). On submit, the PDF is processed & embedded through the RAG
pipeline (process_and_embed_document), persisted to Supabase
(insert_document_record), and reflected in the shared document inventory
(st.session_state.documents) as ACTIVE.

Field labels and progress messages are localized through utils.i18n.t(); the
metadata written to Supabase (status, title, version) stays as entered.
"""

from __future__ import annotations

from datetime import date

import streamlit as st


from components.document_list import invalidate_document_cache
from rag.pipeline import process_and_embed_document
from utils.i18n import t


def render_upload_component() -> None:
    """Renders the PDF Document Uploader interface."""
    st.subheader(t("upload.heading"))
    st.caption(t("upload.caption"))

    with st.form("pdf_upload_form", clear_on_submit=True):
        title = st.text_input(
            t("upload.title_label"),
            placeholder=t("upload.title_placeholder"),
        )
        st.caption(
            "⚠️ **Auto-supersede tip:** To automatically mark older versions as SUPERSEDED when "
            "uploading a newer version, use the **exact same title** (e.g. `TB Diagnosis`) and "
            "increment only the version field (e.g. `v1` → `v2`). "
            "Different titles (e.g. `TB Diagnosis - 2021` vs `TB Diagnosis - 2024`) are treated "
            "as separate documents and will NOT auto-supersede each other."
        )

        col1, col2 = st.columns(2)
        with col1:
            version = st.text_input(t("upload.version_label"), value="v1")
        with col2:
            effective_date = st.date_input(t("upload.date_label"), value=date.today())

        uploaded_file = st.file_uploader(
            t("upload.file_label"),
            type=["pdf"],
            help=t("upload.file_help"),
        )

        submitted = st.form_submit_button(t("upload.submit"), use_container_width=True)

        if submitted:
            if uploaded_file is not None and title:
                file_bytes = uploaded_file.getvalue()
                if len(file_bytes) > 25 * 1024 * 1024:
                    st.error("Uploaded file exceeds the 25 MB size limit. Please upload a smaller document.")
                    return

                document_metadata = {
                    "title": title,
                    "version": version,
                    "effective_date": str(effective_date),
                    "status": "ACTIVE",
                }

                st.session_state.is_loading = True
                try:
                    with st.spinner(t("upload.processing", title=title)):
                        result = process_and_embed_document(file_bytes, document_metadata)



                    # Invalidate cached document inventory so Documents and Admin tabs refresh
                    invalidate_document_cache()

                    # Reflect the new document immediately in the shared inventory
                    # so the Documents tab shows it without a DB round-trip.
                    st.session_state.setdefault("documents", []).insert(0, document_metadata)

                    st.success(
                        t(
                            "upload.success",
                            title=title,
                            filename=uploaded_file.name,
                            pages=result["page_count"],
                            chunks=result["chunk_count"],
                        )
                    )
                except Exception as exc:
                    st.error(t("upload.failed", title=title, error=exc))
                finally:
                    st.session_state.is_loading = False
            else:
                st.warning(t("upload.missing_fields"))
