# CareSync AI — Product Requirements Document

**Tagline:** *Ask. Verify. Act.*  
**Product Type:** AI-powered public-health guidance assistant  
**Core Architecture:** Retrieval-Augmented Generation (RAG)  
**Primary Users:** Public-health field workers  
**Team:** Shaswath, Akhil, Karishma  
**Sprint:** Sprint 2 MVP

---

## 1. Product Overview

CareSync AI is an AI-powered public-health guidance assistant that helps field workers quickly find and verify the latest outbreak guidelines, vaccination protocols, and health advisories.

The application uses **Retrieval-Augmented Generation (RAG)** to retrieve relevant information from an approved document collection before generating an answer. Every answer is accompanied by source citations so field workers can verify the information against the original guideline.

---

## 2. Problem Statement

A public health agency publishes outbreak guidelines, vaccination protocols, and advisories that update rapidly, but field workers cannot confirm the current correct guidance during fast-moving situations.

### Current Challenges

- Searching through multiple PDF documents.
- Identifying which guideline is the latest.
- Comparing different versions of protocols.
- Finding relevant information buried inside lengthy documents.
- Determining whether a recommendation applies to a specific situation.
- Manually verifying information during time-sensitive situations.

These challenges create delays and increase the risk of relying on outdated or incorrect guidance.

---

## 3. Proposed Solution

CareSync AI provides a centralized conversational interface where field workers can:

1. Upload approved public-health documents.
2. Automatically process and index those documents.
3. Ask questions in natural language.
4. Retrieve relevant sections from the document repository.
5. Generate an answer using the retrieved evidence.
6. View the source document, page, version, and effective date associated with the answer.

### Example

**User:** What is the current vaccination protocol for children under 5?

**CareSync AI:** Provides an answer based on the latest active guideline.

**Source:** Vaccination Protocol v3 — Page 12 — Effective August 8, 2026.

---

## 4. Product Goals

The primary goal is to reduce the time and effort required for field workers to locate current public-health guidance while maintaining traceability to official source documents.

### Success Criteria

- Retrieve relevant information quickly.
- Prefer current and effective guidelines.
- Provide citations with answers.
- Reduce manual document searching.
- Avoid generating answers unsupported by the document corpus.
- Make document updates easy for administrators.

---

## 5. Target Users

### Primary Users — Public Health Field Workers

Examples:

- Community health workers
- Vaccination teams
- Outbreak response teams
- Field medical staff
- Public-health officers

**Primary need:** Give me the correct current guidance quickly, and show me where it came from.

### Secondary Users — Agency Administrators

Administrators can:

- Upload new guidelines.
- Update existing documents.
- Monitor the knowledge base.
- Remove or archive outdated documents.
- Maintain document metadata.

---

# 6. Core Product Features

## 6.1 Chat Assistant

The main interface allows users to ask natural-language questions about uploaded public-health documents.

Example questions:

- What is the current vaccination protocol?
- What precautions should field workers follow?
- What is the recommended dosage according to the latest guideline?
- Which guideline is currently active?
- What changed between the previous and current protocol?

The assistant retrieves relevant evidence before generating an answer.

## 6.2 PDF Upload

Administrators can upload approved public-health PDF documents.

### Upload Flow

```text
Upload PDF
    ↓
Validate Document
    ↓
Extract Text
    ↓
Chunk Text
    ↓
Generate Embeddings
    ↓
Store in Supabase
    ↓
Document Becomes Searchable
```

**MVP:** PDF support.

**Future:** DOCX, TXT, HTML, web pages, and scanned PDFs using OCR.

## 6.3 Uploaded PDF List

The UI will contain a list of documents already uploaded to the knowledge base.

Example:

```text
Uploaded Documents

📄 Vaccination Protocol v3
   Effective: Aug 8, 2026
   Status: ACTIVE

📄 Outbreak Guidelines v2
   Effective: Aug 5, 2026
   Status: ACTIVE

📄 Vaccination Protocol v2
   Effective: Jul 20, 2026
   Status: SUPERSEDED
```

Each document should retain:

- Document name
- Version
- Publication date
- Effective date
- Status
- Upload date
- Source

## 6.4 Source and Citation Display

Citations are a core feature.

```text
Answer
────────────────────────
According to the latest vaccination protocol...

Sources
────────────────────────
📄 Vaccination Protocol v3
   Page 12
   Effective: Aug 8, 2026
```

Where possible, users can open or preview the source document.

## 6.5 Document Status

Possible statuses:

- `ACTIVE`
- `SUPERSEDED`
- `ARCHIVED`

The retrieval system should prioritize active/effective guidance.

---

# 7. User Interface

The MVP should remain simple and focused.

### Main Sections

1. **Chat**
   - Ask questions.
   - Display AI responses.
   - Display citations.

2. **Uploaded PDFs**
   - View uploaded documents.
   - Show version/date/status.

3. **Upload PDF**
   - Upload and process a new guideline.

### Supporting UI Elements

- Document processing status
- Loading indicators
- Error messages
- Citation/source panel
- Active/superseded status

### UI Structure

```text
┌─────────────────────────────────────────────┐
│              🩺 CareSync AI                 │
│          Ask. Verify. Act.                  │
├──────────────┬──────────────────────────────┤
│ 💬 Chat      │ Ask about public-health      │
│              │ guidelines...               │
│ 📄 Documents │                              │
│              │ [ Your question... ]         │
│ ⬆️ Upload    │                              │
│              │ AI Answer                    │
│              │                              │
│              │ Sources                      │
│              │ 📄 Guideline v3 — p.14      │
└──────────────┴──────────────────────────────┘
```

Avoid unnecessary MVP sections such as analytics, profiles, and complex settings.

---

# 8. Document Processing Pipeline

## 8.1 Text Extraction

**Technology:** PyMuPDF

```text
PDF
 ↓
PyMuPDF
 ↓
Raw Text
```

## 8.2 Text Chunking

Long documents are divided into smaller meaningful sections.

```text
100-page document
       ↓
    Chunking
       ↓
Chunk 1
Chunk 2
Chunk 3
...
```

Chunk metadata must be preserved so citations can be generated accurately.

---

# 9. Embedding Generation

**Technology:** Sentence Transformers

Sentence Transformers converts document chunks into numerical vectors representing semantic meaning.

```text
"Children under 5 should receive..."
              ↓
     Sentence Transformer
              ↓
     [vector representation]
```

User questions are also converted into embeddings, allowing semantic search rather than exact keyword matching.

---

# 10. Vector Database

**Technology:** Supabase + PostgreSQL + pgvector

Supabase will be used as the application's database and vector storage layer.

### Document Chunk Data

| Field | Example |
|---|---|
| Document ID | DOC-001 |
| Document Name | Vaccination Protocol |
| Text Chunk | Vaccination recommendation... |
| Embedding | Vector representation |
| Page Number | 12 |
| Version | v3 |
| Publication Date | Aug 8, 2026 |
| Effective Date | Aug 8, 2026 |
| Source | Official agency document |
| Upload Date | Aug 8, 2026 |
| Status | ACTIVE |

Metadata is critical because the problem involves rapidly changing guidelines.

---

# 11. Retrieval System

```text
User Question
      ↓
Query Embedding
      ↓
Supabase Vector Search
      ↓
Relevant Document Chunks
      ↓
Metadata / Version Filtering
      ↓
Top Relevant Sources
```

Example:

```text
Question:
"What is the current vaccination protocol?"

Retrieved:
1. Vaccination Protocol v3 — Page 12
2. Outbreak Advisory — Page 4
3. Child Immunization Guidelines — Page 7
```

The retrieval system should prioritize active and currently effective documents.

---

# 12. RAG Pipeline

**Technology:** LangChain

LangChain will orchestrate retrieval, context construction, and generation.

```text
User Question
      ↓
Query Embedding
      ↓
Supabase Vector Search
      ↓
Relevant Document Chunks
      ↓
Context Building
      ↓
Gemini LLM
      ↓
Answer + Citations
      ↓
Streamlit UI
```

---

# 13. LLM

**Technology:** Gemini API

Gemini generates the final response based on retrieved evidence.

The model receives:

```text
System Instructions
+
Retrieved Document Context
+
User Question
```

### Grounding Principle

The model should not rely on general knowledge when answering questions about agency guidelines.

It should:

- Use retrieved official documents.
- Avoid unsupported claims.
- Cite supporting documents.
- Clearly state when sufficient information is unavailable.

### Safe fallback

> No relevant guidance was found in the current knowledge base. Please verify with the appropriate public-health authority.

---

# 14. Document Version Management

Because guidance changes rapidly, version management is critical.

```text
Vaccination Protocol

v1 — July 1
v2 — July 20
v3 — August 8 ← Current
```

### Metadata

- Version
- Publication date
- Effective date
- Status
- Document type
- Source
- Upload date

### Status

```text
ACTIVE
SUPERSEDED
ARCHIVED
```

The system should prioritize active and currently effective guidance.

---

# 15. Main Application Architecture

```text
                         CARESYNC AI
                              │
             ┌────────────────┴────────────────┐
             │                                 │
             ↓                                 ↓
       DOCUMENT FLOW                      QUERY FLOW
             │                                 │
       PDF Upload                         User Question
             │                                 │
             ↓                                 ↓
         PyMuPDF                         Sentence Transformer
             │                                 │
             ↓                                 ↓
         Chunking                         Query Vector
             │                                 │
             ↓                                 │
   Sentence Transformers                       │
             │                                 │
             ↓                                 │
        Embeddings                             │
             │                                 │
             └──────────────┬──────────────────┘
                            ↓
                   SUPABASE + PGVECTOR
                            │
                            ↓
                    Similarity Search
                            │
                            ↓
                    Relevant Chunks
                            │
                            ↓
                       LangChain
                            │
                            ↓
                        GEMINI API
                            │
                            ↓
                    Answer + Citations
                            │
                            ↓
                     STREAMLIT UI
                            │
                            ↓
                          USER
```

---

# 16. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Programming Language | Python | Application and AI/RAG logic |
| UI | Streamlit | Document and chatbot interface |
| RAG Framework | LangChain | Retrieval and generation orchestration |
| LLM | Gemini API | Answer generation |
| Embeddings | Sentence Transformers | Semantic vector representations |
| Vector Database | Supabase + pgvector | Embeddings, chunks, metadata |
| PDF Processing | PyMuPDF | Text extraction |
| Database | PostgreSQL via Supabase | Structured data and metadata |
| Version Control | Git + GitHub | Source control and collaboration |

---

# 17. Team Structure and Responsibilities

## 17.1 Shaswath — AI / RAG Engineer

**Primary ownership:** AI and RAG pipeline

Responsibilities:

- Design RAG architecture.
- Implement document chunking.
- Integrate Sentence Transformers.
- Build LangChain pipeline.
- Integrate Gemini API.
- Design prompts and grounding instructions.
- Implement retrieval logic.
- Implement citation generation.
- Evaluate answer quality and retrieval relevance.
- Test hallucination and grounding behavior.

## 17.2 Akhil — Backend & Database Engineer

**Primary ownership:** Data and Supabase infrastructure

Responsibilities:

- Set up Supabase.
- Configure PostgreSQL and pgvector.
- Design database schema.
- Store chunks, embeddings, and metadata.
- Implement vector similarity search.
- Implement document version management.
- Manage document status and metadata.
- Handle document ingestion/storage.
- Optimize database queries.
- Implement database security policies where applicable.

## 17.3 Karishma — Frontend & Product Engineer

**Primary ownership:** Streamlit UI and user experience

Responsibilities:

- Design Streamlit application.
- Build document upload interface.
- Build chatbot/question interface.
- Display AI responses.
- Display citations and source metadata.
- Display uploaded documents and processing status.
- Implement loading/error states.
- Design field-worker-friendly workflow.
- Perform usability testing.
- Integrate frontend with the RAG pipeline.

---

# 18. Collaboration Flow

```text
Akhil
Supabase + Data
      ↓
Shaswath
RAG + Gemini
      ↓
Karishma
Streamlit UI
      ↓
Integration Testing
      ↓
Final Demo
```

All three members should participate in integration, testing, and the final demo.

---

# 19. Functional Requirements

| ID | Requirement | Description |
|---|---|---|
| FR1 | Upload Documents | Authorized users can upload supported public-health documents. |
| FR2 | Process Documents | Extract and split document content into searchable chunks. |
| FR3 | Generate Embeddings | Generate embeddings for document chunks. |
| FR4 | Store Knowledge | Store chunks, embeddings, and metadata in Supabase. |
| FR5 | Search Knowledge | Retrieve relevant document chunks for user queries. |
| FR6 | Generate Answers | Use Gemini to generate answers based on retrieved context. |
| FR7 | Provide Citations | Provide source information for generated answers. |
| FR8 | Track Versions | Maintain document version and effective-date information. |
| FR9 | Handle Unknown Information | State when available documents do not provide sufficient information. |
| FR10 | Display Sources | Display document title, page number, version, and relevant metadata. |

---

# 20. Non-Functional Requirements

### Accuracy

Answers should be grounded in retrieved official documents.

### Performance

The system should return answers within a reasonable response time under normal usage.

### Reliability

The application should handle invalid documents, failed API requests, retrieval failures, and embedding failures gracefully.

### Security

Only authorized users should be able to upload or modify official documents.

### Traceability

Every generated answer should be traceable to retrieved source material.

### Usability

The interface should be simple enough for field workers during time-sensitive situations.

### Maintainability

The architecture should allow the LLM, embedding model, or vector database to be replaced without rebuilding the entire application.

---

# 21. Hallucination Prevention

Because CareSync AI deals with public-health information, hallucination prevention is critical.

The application should:

- Use RAG rather than relying solely on model knowledge.
- Instruct Gemini to use retrieved context.
- Return citations.
- Avoid unsupported claims.
- Indicate when the knowledge base lacks enough information.
- Prefer active/current document versions.
- Preserve source metadata throughout the pipeline.

---

# 22. Example User Journey

### Step 1 — Upload

Administrator uploads:

```text
Outbreak_Guideline_v3.pdf
```

### Step 2 — Processing

```text
Extract text
     ↓
Split into chunks
     ↓
Generate embeddings
     ↓
Store chunks + embeddings + metadata in Supabase
```

### Step 3 — Ask

Field worker asks:

> What precautions should be followed during the current outbreak?

### Step 4 — Retrieval

The question is embedded and used to search Supabase.

### Step 5 — Context

Relevant sections of the active guideline are retrieved.

### Step 6 — Generation

LangChain sends the retrieved context and question to Gemini.

### Step 7 — Response

```text
Answer
────────────────────────
According to the current outbreak guideline...

Sources
────────────────────────
📄 Outbreak Guideline v3
📑 Page 18
📅 Effective: August 8, 2026
```

---

# 23. MVP Scope

## Must Have

- PDF upload
- PDF text extraction
- Document chunking
- Sentence Transformer embeddings
- Supabase + pgvector
- Semantic retrieval
- LangChain RAG pipeline
- Gemini integration
- Streamlit chatbot
- Source citations
- Document metadata
- Basic version/effective-date handling
- Uploaded PDF list
- Active/superseded document status

## Nice to Have

- Document preview
- Source highlighting
- Conversation history
- Advanced filtering
- Authentication
- Document deletion
- Admin dashboard
- Feedback buttons

---

# 24. Future Enhancements

### Multi-format Support

- DOCX
- TXT
- HTML
- Web pages
- Scanned PDFs using OCR

### Advanced Retrieval

- Hybrid keyword + semantic search
- Reranking
- Query expansion
- Metadata filtering

### Version Intelligence

Automatically detect:

- New versions
- Superseded guidelines
- Conflicting recommendations
- Expired guidance

### Multilingual Support

Allow field workers to ask questions in regional languages.

### Voice Interface

Allow field workers to ask questions using voice.

### Mobile Application

Convert the assistant into a dedicated mobile application.

### Analytics

Track:

- Most frequently asked questions
- Frequently accessed guidelines
- Retrieval failures
- User feedback
- Knowledge gaps

---

# 25. Risks and Mitigation

| Risk | Mitigation |
|---|---|
| AI hallucination | RAG + strict prompting + citations |
| Outdated guidance | Version/effective-date metadata |
| Poor retrieval | Improve chunking, embeddings, filtering, retrieval |
| Conflicting documents | Prioritize active/latest versions and expose conflicts |
| Incorrect citations | Preserve page/document metadata |
| API limitations | Use model abstraction and monitor usage limits |
| Poor PDF extraction | Validate extracted text and add OCR later |
| Sensitive information | Access control and secure storage |

---

# 26. Success Metrics

### Retrieval Accuracy

Whether the correct guideline sections are retrieved.

### Answer Grounding

Whether generated answers match the retrieved source.

### Citation Accuracy

Whether citations point to supporting document content.

### Response Time

How quickly users receive an answer.

### User Satisfaction

Whether users can find required guidance more easily than manual PDF searching.

### Unanswerable Question Rate

Whether the system correctly recognizes when the knowledge base lacks an answer.

---

# 27. Final Product Definition

CareSync AI is not simply a chatbot. It is a **document-grounded public-health knowledge assistant**.

### Core Value Proposition

> **CareSync AI helps public-health field workers quickly find the latest applicable guidance from official documents and verify every answer through citations.**

### Core Architecture

```text
Official Documents
       ↓
Text Extraction
       ↓
Chunking
       ↓
Sentence Transformers
       ↓
Supabase / pgvector
       ↓
Relevant Evidence
       ↓
LangChain
       ↓
Gemini
       ↓
Verified Answer + Citation
       ↓
Streamlit
```

### Final Technology Stack

**Python + Streamlit + LangChain + Gemini + Sentence Transformers + Supabase/pgvector + PyMuPDF**

### Team

- **Shaswath — AI / RAG**
- **Akhil — Backend / Database**
- **Karishma — Frontend / Product**

---

# 28. MVP UI Summary

The final MVP interface should stay focused on the core problem.

```text
┌─────────────────────────────────────────────┐
│              🩺 CareSync AI                 │
│          Ask. Verify. Act.                  │
├──────────────┬──────────────────────────────┤
│              │                              │
│ 💬 Chat      │ Ask a question...            │
│              │                              │
│ 📄 Documents │ [________________________]   │
│              │                              │
│ ⬆️ Upload PDF│ [ Ask ]                      │
│              │                              │
│              │ Answer                       │
│              │ ─────────────────────────    │
│              │ AI-generated response        │
│              │                              │
│              │ Sources                      │
│              │ 📄 Guideline v3 — Page 14   │
│              │ 📅 Effective Aug 8, 2026    │
│              │                              │
└──────────────┴──────────────────────────────┘
```

The MVP follows one simple workflow:

> **Upload → Process → Store → Ask → Retrieve → Answer → Verify**
