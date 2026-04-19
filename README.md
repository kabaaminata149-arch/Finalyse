# Finalyse — Intelligent Invoice Analysis Platform

AI-powered invoice analysis SaaS application.
Local AI processing via Ollama — 100% secure, no data sent to external servers.

---

## Quick Start

### 1. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```bash
pip install PyQt6
```

### 3. Install Ollama (optional but recommended)

Download from https://ollama.ai then run:

```bash
ollama pull mistral        # For text analysis
ollama pull llava          # For vision/image analysis (recommended)
```

### 4. Launch the application

```bash
python GO.py
```

This starts the backend on port 8000 and opens the desktop UI.

---

## Architecture

```
Finalyse/
├── GO.py                      # Main launcher
├── backend/
│   ├── main.py                # FastAPI application
│   ├── config.py              # Centralised configuration
│   ├── .env                   # Environment variables
│   ├── requirements.txt
│   ├── auth/
│   │   └── jwt_handler.py     # JWT authentication
│   ├── database/
│   │   └── db.py              # SQLite thread-safe layer (WAL)
│   ├── routes/
│   │   ├── auth.py            # Register, login, password reset
│   │   ├── factures.py        # Invoice upload and management
│   │   ├── dossiers.py        # Folder management
│   │   ├── dashboard.py       # Statistics
│   │   ├── export.py          # CSV/PDF export
│   │   └── chatbot.py         # AI assistant
│   └── services/
│       ├── processor.py       # Background AI processing pipeline
│       ├── ollama.py          # Ollama API client
│       └── export_service.py  # Export generation
└── frontend/
    ├── main.py                # PyQt6 application entry point
    ├── api_client.py          # HTTP client
    ├── theme.py               # Design system
    ├── assets/
    │   └── logo.png           # Application logo (replace with yours)
    ├── pages/
    │   ├── splash.py          # Loading screen
    │   ├── login.py           # Authentication
    │   ├── dashboard.py       # Main dashboard
    │   ├── import_page.py     # Invoice import
    │   ├── analyse.py         # AI analysis view
    │   ├── rapports.py        # Reports and exports
    │   ├── historique.py      # Invoice history
    │   └── chatbot.py         # AI assistant chat
    └── widgets/
        └── sidebar.py         # Navigation sidebar
```

---

## Key Design Decisions

### Timeout Architecture
Invoices are uploaded and immediately acknowledged (`{"status": "processing"}`).
AI analysis (OCR, LLM, vision) runs in a **background thread pool** via FastAPI's
`BackgroundTasks`. The HTTP event loop is never blocked.

### Processing Pipeline
1. **Ping Ollama** (3s timeout) — detect availability
2. **Vision AI** (90s timeout) — analyze image directly with llava/moondream
3. **Text LLM** (60s timeout) — analyze extracted text with mistral (PDF only)
4. **Regex fallback** (< 1s) — always available, extracts key fields with patterns

### Database
SQLite with WAL (Write-Ahead Logging) mode and thread-local connections.
Concurrent reads and writes without blocking between background processing and API requests.

### PyQt6 Safety
All pages use `self._alive` guards before updating UI from signals.
Workers check aliveness before emitting to prevent `RuntimeError: wrapped C/C++ object deleted`.

---

## Configuration (.env)

```env
JWT_SECRET=your-secret-key-here
JWT_EXPIRE_H=24

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral
OLLAMA_MODEL_VISION=llava

OLLAMA_PING_TIMEOUT=3
OLLAMA_TEXT_TIMEOUT=60
OLLAMA_VISION_TIMEOUT=90

MAX_MB=20
```

---

## Logo Integration

Place your logo file at:
```
frontend/assets/logo.png
```

The logo is automatically displayed in:
- Splash/loading screen
- Login page (left panel)
- Sidebar navigation header
- Application window icon

---

## Default Credentials

```
Email:    admin@finalyse.com
Password: admin123
```

Change these immediately in production.
