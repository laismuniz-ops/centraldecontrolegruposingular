"""
GRUPO SINGULAR — Servidor unificado para Easypanel
===================================================
Serve o index.html na raiz, faz proxy da Saipos em /api/saipos/
e persiste dados compartilhados em /api/store (arquivo JSON no servidor).

Variáveis de ambiente:
  PORT          → porta HTTP (padrão 8080)
  SAIPOS_TOKEN  → token da API Saipos
  DATA_FILE     → caminho do arquivo de dados (padrão /data/store.json)
"""

import http.server
import urllib.request
import json
import os
import sys
import threading

PORT         = int(os.environ.get("PORT", 8080))
SAIPOS_TOKEN = os.environ.get("SAIPOS_TOKEN", "")
SAIPOS_BASE  = "https://data.saipos.io/v1"
STATIC_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_FILE    = os.environ.get("DATA_FILE", "/data/store.json")

# Lock para acesso seguro ao arquivo
_file_lock = threading.Lock()

def read_store():
    try:
        with _file_lock:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return {}

def write_store(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with _file_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[server] {fmt % args}", flush=True)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Accept, Content-Type")

    def _json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]

        # Store compartilhado → retorna todos os dados
        if path == "/api/store":
            self._json(200, read_store())
            return

        # Proxy Saipos
        if path.startswith("/api/saipos/"):
            self._proxy_saipos()
            return

        # Health-check
        if path == "/health":
            self._json(200, {"ok": True})
            return

        # Arquivo estático (index.html)
        filepath = os.path.join(STATIC_DIR, path.lstrip("/"))
        if path in ("/", "") or not os.path.isfile(filepath):
            filepath = os.path.join(STATIC_DIR, "index.html")

        try:
            with open(filepath, "rb") as f:
                body = f.read()
            ctype = "text/html; charset=utf-8" if filepath.endswith(".html") else "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(404)
            self.end_headers()

    # ── POST ──────────────────────────────────────────────────────
    def do_POST(self):
        path = self.path.split("?")[0]

        # Store compartilhado → { key, value }
        if path == "/api/store":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = json.loads(self.rfile.read(length).decode("utf-8"))
                key    = body.get("key")
                value  = body.get("value")
                if not key:
                    self._json(400, {"error": "key obrigatório"})
                    return
                store = read_store()
                store[key] = value
                write_store(store)
                self._json(200, {"ok": True})
            except Exception as e:
                self._json(500, {"error": str(e)})
            return

        self._json(404, {"error": "not found"})

    # ── Proxy Saipos ──────────────────────────────────────────────
    def _proxy_saipos(self):
        if not SAIPOS_TOKEN:
            self._json(500, {"error": "SAIPOS_TOKEN não configurado no servidor"})
            return

        saipos_path = self.path[len("/api/saipos"):]
        if saipos_path == "/ping":
            self._json(200, {"ok": True, "proxy": "Saipos", "version": "2.0"})
            return

        target = f"{SAIPOS_BASE}{saipos_path}"
        print(f"[proxy] GET {target}", flush=True)

        req = urllib.request.Request(
            target,
            headers={
                "Authorization": f"Bearer {SAIPOS_TOKEN}",
                "Accept":        "application/json",
                "User-Agent":    "SING-Dashboard/2.0",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body   = resp.read()
                status = resp.status
                ctype  = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            body   = e.read()
            status = e.code
            ctype  = "application/json"
        except Exception as e:
            body   = json.dumps({"error": str(e)}).encode()
            status = 502
            ctype  = "application/json"

        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(f"[proxy] ← {status} ({len(body)} bytes)", flush=True)


if __name__ == "__main__":
    if not SAIPOS_TOKEN:
        print("  AVISO: SAIPOS_TOKEN não definido — proxy Saipos retornará erro 500", flush=True)

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n  ██████ GRUPO SINGULAR — Servidor unificado", flush=True)
    print(f"  Porta     : {PORT}", flush=True)
    print(f"  Dados em  : {DATA_FILE}", flush=True)
    print(f"  Token     : {'✓ configurado' if SAIPOS_TOKEN else '✗ ausente'}", flush=True)
    print(flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Servidor encerrado.")
        sys.exit(0)
