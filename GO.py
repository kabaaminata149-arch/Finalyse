"""
GO.py — Finalyse Launcher
Starts the backend (FastAPI) then the desktop UI (PyQt6).

Fixes:
  - Frontend sys.path is isolated: backend/main.py never shadows frontend/main.py.
  - --reload removed: causes WinError 10013 on Windows (file-watcher socket
    permission denied by the OS). Not needed; production mode is stable.
  - Port conflict: detected before starting; reuses an already-running backend.
"""
import subprocess
import sys
import os
import time
import threading
import signal
import socket
import importlib.util

# ── Chemin de base — fonctionne en mode script ET en mode .exe ────────────
if getattr(sys, "frozen", False):
    # Mode .exe PyInstaller — les fichiers sont extraits dans _MEIPASS
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR  = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
PORT         = 8000

# En mode .exe, les données persistantes vont dans AppData
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Finalyse")
    os.makedirs(DATA_DIR, exist_ok=True)
    # Copier le .env si absent
    env_src = os.path.join(BACKEND_DIR, ".env")
    env_dst = os.path.join(DATA_DIR, ".env")
    if not os.path.exists(env_dst) and os.path.exists(env_src):
        import shutil
        shutil.copy2(env_src, env_dst)
    # Pointer le backend vers DATA_DIR pour DB/uploads/exports
    os.environ["FINALYSE_DATA_DIR"] = DATA_DIR
else:
    DATA_DIR = BASE_DIR

_backend_proc = None
_lock_sock    = None


# ── Port helpers ──────────────────────────────────────────────────────────

def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _backend_already_up() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/health", timeout=2
        ) as r:
            return r.status == 200
    except Exception:
        return False


def _check_port() -> bool:
    """Return True if we should skip starting a new backend (one already runs)."""
    if _port_free(PORT):
        return False          # Port free — start fresh
    if _backend_already_up():
        # Toujours tuer l'ancien backend pour charger le nouveau code
        print(f"[Finalyse] Ancien backend detecte — redemarrage force...")
        import subprocess
        # Tuer le process qui occupe le port
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if f":{PORT}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True)
                    print(f"[Finalyse] Process {pid} arrete.")
                    import time; time.sleep(1)
                    break
        except Exception as e:
            print(f"[Finalyse] Impossible d'arreter l'ancien backend: {e}")
        return False  # Demarrer un nouveau backend
    print(
        f"[Finalyse] ERROR: Port {PORT} is occupied by another application.\n"
        f"           Close it and retry, or change PORT in GO.py."
    )
    sys.exit(1)


# ── Backend (subprocess) ──────────────────────────────────────────────────

def start_backend():
    global _backend_proc
    print("[Finalyse] Starting backend server...")

    env = os.environ.copy()
    env["PYTHONPATH"] = BACKEND_DIR   # backend sees its own modules

    # Charger le .env dans l'environnement du subprocess
    env_file = os.path.join(BACKEND_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    env[key] = val

    _backend_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "127.0.0.1",
            "--port", str(PORT),
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    def _stream():
        for line in _backend_proc.stdout:
            print("[Backend]", line.decode("utf-8", errors="replace").rstrip())

    threading.Thread(target=_stream, daemon=True).start()
    return _backend_proc


def wait_for_backend(max_seconds: int = 25) -> bool:
    import urllib.request
    print("[Finalyse] Waiting for backend to be ready...")
    for i in range(max_seconds):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/health", timeout=2
            ) as r:
                if r.status == 200:
                    print(f"[Finalyse] Backend ready ({i + 1}s)")
                    return True
        except Exception:
            pass
        time.sleep(1)
    print("[Finalyse] WARNING: Backend did not respond in time — continuing anyway.")
    return False


# ── Frontend (in-process) ─────────────────────────────────────────────────

def start_frontend():
    """
    Launch the PyQt6 UI in the current process.

    PATH ISOLATION — critical on Windows:
      backend/main.py and frontend/main.py share the same module name.
      The backend runs as a *subprocess* and must never appear in sys.path.
      We use importlib to load frontend/main.py by file path, bypassing
      the module name lookup entirely.
    """
    print("[Finalyse] Starting desktop UI...")

    # Scrub any backend path that may have leaked into sys.path.
    norm_backend = os.path.normpath(BACKEND_DIR)
    sys.path[:] = [p for p in sys.path
                   if os.path.normpath(p) != norm_backend]

    # Frontend directory first so its local imports resolve correctly.
    if FRONTEND_DIR not in sys.path:
        sys.path.insert(0, FRONTEND_DIR)

    os.chdir(FRONTEND_DIR)

    # Load frontend/main.py by absolute path — avoids any name collision.
    spec   = importlib.util.spec_from_file_location(
        "finalyse_frontend",
        os.path.join(FRONTEND_DIR, "main.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["finalyse_frontend"] = module
    spec.loader.exec_module(module)
    module.main()


# ── Shutdown ──────────────────────────────────────────────────────────────

def _shutdown(sig=None, frame=None):
    global _backend_proc
    print("\n[Finalyse] Shutting down...")
    if _backend_proc and _backend_proc.poll() is None:
        _backend_proc.terminate()
        try:
            _backend_proc.wait(timeout=5)
        except Exception:
            _backend_proc.kill()
    # Libérer le verrou d'instance
    try:
        _lock_sock.close()
    except Exception:
        pass
    sys.exit(0)


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Instance unique ───────────────────────────────────────────────────
    # Empêcher deux instances de l'app de tourner simultanément
    import socket as _sock
    _lock_sock = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
    try:
        _lock_sock.bind(("127.0.0.1", 19876))  # port verrou interne
    except OSError:
        print("[Finalyse] Une instance est deja en cours d'execution.")
        # Ramener la fenetre existante au premier plan via le port health
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print("=" * 55)
    print("  Finalyse — Intelligent Invoice Analysis")
    print("  v1.0.0")
    print("=" * 55)

    reusing = _check_port()

    if not reusing:
        start_backend()

    wait_for_backend(max_seconds=25)
    start_frontend()

    # Reached only when the UI window closes normally.
    _shutdown()
