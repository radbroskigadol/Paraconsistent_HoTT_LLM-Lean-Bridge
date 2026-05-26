# Lean worker stub for demos. Production builders should replace this with a
# real Lean/lake image pinned by digest and run it with a no-network sandbox.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --shell /usr/sbin/nologin shadowproof
COPY <<'PY' /app/worker.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        if length < 0 or length > 1_000_000:
            self.send_response(413)
            self.end_headers()
            return
        _ = self.rfile.read(length)
        body = json.dumps({
            "status": "unchecked",
            "lean_status": "not_available",
            "stdout": "",
            "stderr": "lean toolchain is not installed in this stub image",
            "elapsed_ms": 0,
            "exit_code": None,
            "diagnostics": [{
                "severity": "error",
                "kind": "lean_not_available",
                "message": "stub lean worker; replace with real image",
                "source": "lean_worker_stub"
            }]
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

HTTPServer(("0.0.0.0", 9001), H).serve_forever()
PY
RUN chown -R shadowproof:shadowproof /app
USER shadowproof
EXPOSE 9001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9001', timeout=2).read()" || exit 1
CMD ["python", "/app/worker.py"]
