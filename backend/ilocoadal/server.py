"""Local HTTP API for the Flutter app (standard library only, no extra packages).

    python server.py --config config.json

Endpoints (JSON; errors look like {"error": {"code": ..., "message": ...}}):

    GET    /health
    GET    /config                         settings the app may show (no secrets)
    POST   /jobs                           {"paths"?: [...], "options"?: {...}, "start"?: bool} -> draft job
    GET    /jobs/{id}                      job status (poll this)
    GET    /jobs/{id}/files                the "Ready to Process" list
    POST   /jobs/{id}/files                {"path": "..."}  add a document (name, format, size, pages)
    DELETE /jobs/{id}/files/{file_id}      remove a document
    POST   /jobs/{id}/start                Start Processing
    POST   /jobs/{id}/retry                after state "offline": Try again
    POST   /jobs/{id}/skip_online          after state "offline": Continue without definitions
    POST   /jobs/{id}/cancel
    DELETE /jobs/{id}
    GET    /jobs/{id}/terms                for the Review screen
    POST   /jobs/{id}/terms                {"word": "..."}   add a term
    PATCH  /jobs/{id}/terms/{term_id}      {"selected": true|false}
    POST   /jobs/{id}/continue             start definitions, translation, build
    GET    /jobs/{id}/document             the finished .docx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from .config import Config
from .errors import IlocoAdalError
from .service import JobService, ServiceError

API_VERSION = "1"
MAX_BODY = 1_000_000
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    service: JobService
    config: Config

    def log_message(self, *args) -> None:  # keep the console quiet
        pass

    # -- plumbing ------------------------------------------------------------
    def _cors(self) -> None:
        origin = self.config.server.allow_origin
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")

    def _json(self, status: int, payload=None) -> None:
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", DOCX)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ServiceError(413, "too_large", "The request is too large.")
        if length == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            raise ServiceError(400, "bad_request", "The request body must be JSON.") from None
        if not isinstance(data, dict):
            raise ServiceError(400, "bad_request", "The request body must be a JSON object.")
        return data

    def _authorize(self) -> None:
        token = self.config.server.auth_token
        if token and self.headers.get("Authorization") != f"Bearer {token}":
            raise ServiceError(401, "unauthorized", "Missing or wrong access token.")

    # -- dispatch ----------------------------------------------------------------
    def _handle(self, method: str) -> None:
        try:
            path = self.path.split("?", 1)[0]
            if method == "OPTIONS":
                self.send_response(204)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if method == "GET" and path == "/health":
                return self._json(200, {"status": "ok", "api_version": API_VERSION})
            self._authorize()
            self._route(method, path)
        except ServiceError as exc:
            self._json(exc.status, {"error": {"code": exc.code, "message": exc.message}})
        except IlocoAdalError as exc:
            self._json(400, {"error": {"code": exc.code, "message": str(exc)}})
        except Exception:  # noqa: BLE001
            self._json(500, {"error": {"code": "unknown",
                                       "message": "Something went wrong. Please try again."}})

    def _route(self, method: str, path: str) -> None:
        svc = self.service
        if method == "GET" and path == "/config":
            return self._json(200, self.config.public_dict())
        if method == "POST" and path == "/jobs":
            body = self._body()
            paths = body.get("paths", [])
            if isinstance(body.get("path"), str):          # shortcut for one file
                paths = [body["path"]]
            if not isinstance(paths, list) or not all(isinstance(x, str) for x in paths):
                raise ServiceError(400, "bad_request", "'paths' must be a list of file paths.")
            start = body.get("start", False)
            if not isinstance(start, bool):
                raise ServiceError(400, "bad_request", "'start' must be true or false.")
            job = svc.create_job(body.get("options") or {}, paths, start)
            return self._json(201, job.status())

        m = re.fullmatch(r"/jobs/([0-9a-f]+)(?:/(\w+)(?:/([^/]+))?)?", path)
        if not m:
            raise ServiceError(404, "not_found", "Unknown address.")
        job = svc.get(m.group(1))
        part, sub = m.group(2), (unquote(m.group(3)) if m.group(3) else None)

        if part is None:
            if method == "GET":
                return self._json(200, job.status())
            if method == "DELETE":
                svc.delete(job)
                return self._json(204)
        elif part == "cancel" and method == "POST" and sub is None:
            svc.cancel(job)
            return self._json(200, job.status())
        elif part == "start" and method == "POST" and sub is None:
            svc.start(job)
            return self._json(202, job.status())
        elif part == "retry" and method == "POST" and sub is None:
            svc.retry(job)
            return self._json(202, job.status())
        elif part == "skip_online" and method == "POST" and sub is None:
            svc.skip_online(job)
            return self._json(202, job.status())
        elif part == "files":
            if method == "GET" and sub is None:
                return self._json(200, {"files": svc.files(job)})
            if method == "POST" and sub is None:
                file_path = self._body().get("path")
                if not isinstance(file_path, str) or not file_path:
                    raise ServiceError(400, "bad_request", "'path' is required.")
                return self._json(201, svc.add_file(job, file_path))
            if method == "DELETE" and sub:
                svc.remove_file(job, sub)
                return self._json(204)
        elif part == "continue" and method == "POST" and sub is None:
            svc.continue_job(job)
            return self._json(202, job.status())
        elif part == "document" and method == "GET" and sub is None:
            return self._file(svc.document(job))
        elif part == "terms":
            if method == "GET" and sub is None:
                return self._json(200, {"terms": svc.terms(job)})
            if method == "POST" and sub is None:
                word = self._body().get("word")
                if not isinstance(word, str) or not word.strip():
                    raise ServiceError(400, "bad_request", "'word' is required.")
                return self._json(201, svc.add_term(job, word))
            if method == "PATCH" and sub:
                selected = self._body().get("selected")
                if not isinstance(selected, bool):
                    raise ServiceError(400, "bad_request", "'selected' must be true or false.")
                return self._json(200, svc.set_selected(job, sub, selected))
        raise ServiceError(405, "method_not_allowed", "That action isn't supported here.")

    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PATCH(self): self._handle("PATCH")
    def do_DELETE(self): self._handle("DELETE")
    def do_OPTIONS(self): self._handle("OPTIONS")


def make_server(config: Config, service: Optional[JobService] = None) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {
        "service": service or JobService(config), "config": config,
    })
    server = ThreadingHTTPServer((config.server.host, config.server.port), handler)
    server.daemon_threads = True
    return server


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="IlocoAdal local API server")
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("--host", help="overrides server.host")
    parser.add_argument("--port", type=int, help="overrides server.port (0 = free port)")
    args = parser.parse_args(argv)
    try:
        config = Config.load(args.config)
        if args.host:
            config.server.host = args.host
        if args.port is not None:
            config.server.port = args.port
        config.validate()
    except IlocoAdalError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1
    server = make_server(config)
    host, port = server.server_address[:2]
    # One JSON line so the app that launched us can read the real port.
    print(json.dumps({"event": "listening", "host": host, "port": port}), flush=True)
    print(f"IlocoAdal engine running at http://{host}:{port}  (Ctrl+C to stop)", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
