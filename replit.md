# LexiSense - AI-Powered Document Analysis System

## Overview

LexiSense is an intelligent document analysis platform that extracts intelligence from PDFs using advanced AI analytics. The system processes domain-specific documents (insurance, legal, HR, compliance) and returns structured, explainable JSON responses. It uses Gemini AI for semantic understanding and provides detailed analysis with source references.

The application accepts PDF documents either by URL or file upload, processes them into searchable chunks, and allows users to query the content using natural language. It returns structured responses with decision logic, confidence scores, and source references.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Technology**: HTML5, Bootstrap 5 (dark theme), Vanilla JavaScript
- **Design Pattern**: Single-page application with modular JavaScript classes
- **UI Components**: Glassmorphism upload interface with drag & drop, AI query interface, animated results display
- **Styling**: Modern glassmorphism design with animated stars background, gradient effects, and interactive elements

### Backend Architecture
- **Framework**: Flask with Blueprint-based modular routing
- **Design Pattern**: Service-oriented architecture with separated concerns
- **Core Services**:
  - `DocumentProcessor`: PDF text extraction and chunking
  - `EmbeddingService`: Text-based analysis with FAISS infrastructure (Gemini-compatible)
  - `QueryAnalyzer`: Gemini AI-powered query understanding and structured response generation
- **Authentication**: Bearer token-based API authentication
- **API Structure**: RESTful design with versioned endpoints (`/api/v1/`)

### Data Storage Solutions
- **Database**: SQLite with SQLAlchemy ORM (configurable to other databases via DATABASE_URL)
- **Schema Design**:
  - `Document`: Stores PDF metadata, content, and file hashes for deduplication
  - `DocumentChunk`: Stores text chunks with page numbers and character positions
  - `Query`: Stores query history with structured JSON responses
- **Vector Storage**: FAISS index for embedding similarity search with local file persistence
- **File Storage**: Local filesystem for FAISS index and metadata caching

### Authentication and Authorization
- **Method**: Bearer token authentication using hardcoded token
- **Implementation**: Decorator-based authentication (`@require_auth`) for API endpoints
- **Security**: Authorization header validation with Bearer token format

### Core Processing Pipeline
1. **Document Ingestion**: PDF download/upload → text extraction → chunking (500-1500 tokens)
2. **Content Analysis**: Text-based search with intelligent ranking and relevance scoring
3. **Query Processing**: Natural language query → semantic search → relevant chunk retrieval
4. **AI Analysis**: Gemini AI processes retrieved chunks → structured decision analysis → JSON response
5. **Domain Intelligence**: Pattern matching for insurance, legal, HR, and compliance domains

## External Dependencies

### AI/ML Services
- **Gemini AI**: Advanced language model for query analysis and document understanding
- **FAISS**: Facebook's similarity search library for vector operations (with text-based fallback)
- **PDF Processing**: pdfplumber (primary) with PyPDF2 fallback for text extraction

### Core Libraries
- **Flask**: Web framework with SQLAlchemy for database operations
- **NumPy**: Numerical operations for embedding processing
- **Requests**: HTTP client for PDF URL downloading

### Frontend Dependencies
- **Bootstrap 5**: UI framework with dark theme support
- **Font Awesome**: Icon library for user interface elements

### Environment Variables
- `GEMINI_API_KEY`: Required for AI analysis and language understanding
- `DATABASE_URL`: Database connection string (defaults to SQLite)
- `SESSION_SECRET`: Flask session security (defaults to development key)

### File System Dependencies
- Local storage for FAISS index persistence (`faiss_index.bin`)
- Metadata caching for chunk information (`chunk_metadata.pkl`)
- SQLite database file (`documents.db`) for structured data storage