# CareSync AI — Public Health Guidance Assistant

**Tagline:** *Ask. Verify. Act.*  
CareSync AI is a RAG-based AI assistant designed to help public-health field workers retrieve, verify, and cite up-to-date outbreak guidelines, vaccination protocols, and advisories.

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/kalviumcommunity/SW2627_CareSyncAI.git
cd SW2627_CareSyncAI

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to `.env` and populate your API credentials:

```bash
cp .env.example .env
```

Set the following variables:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `GROQ_API_KEY`

Optionally set `CARESYNC_USER_ID` to pin a shared device to one identity, so its
chat history and feedback survive a browser refresh. Left empty, each browser
session gets its own anonymous id.

The microphone recorder in the Chat tab needs Streamlit 1.41 or newer; older
builds fall back to an audio file uploader.

### 3. Run Application

```bash
streamlit run app.py
```

---

## 📁 Repository Structure

```text
SW2627_CareSyncAI/
├── config.py                 # Application configuration & environment loader
├── requirements.txt          # Project dependencies
├── database/                 # Supabase & PostgreSQL schema & client
│   ├── schema.sql
│   └── supabase_client.py
├── rag/                      # Chunking, embedding & RAG pipeline logic
│   ├── chunker.py
│   ├── embeddings.py
│   └── pipeline.py
├── utils/                    # PDF extraction, text processing, i18n & export
│   ├── pdf_processor.py
│   ├── ui_helpers.py
│   ├── export.py             # Guidance summary PDF/TXT export builders
│   ├── i18n.py               # Language picker, t() lookup & fallbacks
│   ├── translations.py       # UI string catalog (en, hi, ta, es)
│   └── user.py               # Per-device / per-session identity for the DB
├── components/               # Streamlit UI components
│   ├── chat.py               # Q&A, citations, relevance badges, copy & export
│   ├── chat_history.py       # Sidebar history drawer & chat persistence
│   ├── feedback.py           # Thumbs-up/down answer ratings
│   ├── audio_input.py        # Microphone recorder & speech-to-text
│   ├── analytics.py          # Admin analytics dashboard (KPIs & charts)
│   ├── guidelines_admin.py   # Guideline registry, sync warnings & retire actions
│   ├── document_list.py
│   └── upload.py
└── app.py                    # Main Streamlit UI entry point
```
