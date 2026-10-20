"""Faux serveur Ollama (bibliothèque standard) pour tester notre code sans Ollama.

Il suit le format décrit dans la doc officielle (docs.ollama.com) : /api/chat, /api/tags, /api/ps,
erreurs en JSON {"error": ...}. Il ne prouve PAS que le vrai Ollama se comporte pareil.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOllama:
    def __init__(self):
        self.models = ["qwen2.5:3b"]  # modèles « installés »
        self.reply = "Bonjour, je suis le gardien."
        self.eval_count = 20
        self.eval_duration_ns = 2_000_000_000  # 20 tokens en 2 s = 10 tok/s
        self.size = 2_000_000_000
        self.size_vram = 500_000_000
        self.requests: list[dict] = []
        self.force_status: int | None = None
        self.version = "0.31.2"
        # Modèle « sans mode réflexion » qui refuse le champ think (comportement possible d'Ollama, non vérifié).
        self.reject_think = False
        # Modèle « thinking » : sans think=false il épuise son budget à réfléchir et renvoie un contenu vide.
        self.thinking_model = False
        self.unloaded: list[str] = []
        # timing_fn(options) -> dict de champs de la réponse à remplacer (eval_duration, prompt_eval_duration…)
        self.timing_fn = None
        # vram_fn(dernières options) -> octets en VRAM renvoyés par /api/ps
        self.vram_fn = None
        self.last_options: dict = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _send(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/api/tags":
                    self._send(200, {"models": [{"name": m, "model": m, "size": outer.size} for m in outer.models]})
                elif self.path == "/api/version":
                    self._send(200, {"version": outer.version})
                elif self.path == "/api/ps":
                    vram = outer.vram_fn(outer.last_options) if outer.vram_fn else outer.size_vram
                    self._send(
                        200,
                        {"models": [{"name": m, "model": m, "size": outer.size, "size_vram": vram}
                                    for m in outer.models]},
                    )
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path != "/api/chat":
                    return self._send(404, {"error": "not found"})
                outer.requests.append(body)
                if outer.force_status:
                    return self._send(outer.force_status, {"error": "the model failed to generate a response"})
                if body.get("model") not in outer.models:
                    return self._send(404, {"error": f"model '{body.get('model')}' not found"})
                if outer.reject_think and "think" in body:
                    return self._send(400, {"error": f"\"{body['model']}\" does not support thinking"})
                if not body.get("messages") and body.get("keep_alive") == 0:  # demande de déchargement
                    outer.unloaded.append(body["model"])
                    return self._send(200, {"model": body["model"], "done": True, "done_reason": "unload"})
                outer.last_options = body.get("options", {})
                message = {"role": "assistant", "content": outer.reply}
                if outer.thinking_model and body.get("think") is not False:
                    message = {"role": "assistant", "content": "", "thinking": "Hmm, voyons, le mot est…"}
                result = {
                    "model": body["model"],
                    "created_at": "2026-01-01T00:00:00Z",
                    "message": message,
                    "done": True,
                    "total_duration": outer.eval_duration_ns + 1,
                    "load_duration": 1_000_000,
                    "prompt_eval_count": 30,
                    "prompt_eval_duration": 1_000_000,
                    "eval_count": outer.eval_count,
                    "eval_duration": outer.eval_duration_ns,
                }
                if outer.timing_fn:
                    result.update(outer.timing_fn(outer.last_options))
                self._send(200, result)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
