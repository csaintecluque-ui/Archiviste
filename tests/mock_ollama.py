"""Faux serveur Ollama pour tester Archiviste sans GPU."""
import json, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11434


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def j(self, obj, status=200):
        d = json.dumps(obj).encode()
        self.send_response(status)
        self.cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def do_GET(self):
        if self.path == "/api/version":
            return self.j({"version": "0.13.0-mock"})
        if self.path == "/api/tags":
            return self.j({"models": [
                {"name": "qwen3.5:4b", "size": 3400000000, "details": {"parameter_size": "4.7B", "quantization_level": "Q4_K_M"}},
                {"name": "llama3.2:3b", "size": 2000000000, "details": {"parameter_size": "3.2B", "quantization_level": "Q4_K_M"}}]})
        self.j({"error": "not found"}, 404)

    def stream(self, chunks):
        self.send_response(200)
        self.cors()
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            for c in chunks:
                self.wfile.write((json.dumps(c) + "\n").encode())
                self.wfile.flush()
                time.sleep(0.02)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Archiviste a abandonné cette réponse (discussion reprise par une autre requête)

    def do_POST(self):
        p = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with open("/tmp/mock_requests.jsonl", "a") as f:
            f.write(json.dumps({k: v for k, v in p.items() if k != "messages"}) + "\n")
        model = p.get("model")
        if model not in ("qwen3.5:4b", "llama3.2:3b"):
            return self.j({"error": f"model '{model}' not found"}, 404)
        if p.get("think") and model == "llama3.2:3b":
            return self.j({"error": f'"{model}" does not support thinking'}, 400)
        msgs = p["messages"]
        last = msgs[-1]
        if "[lent]" in (last.get("content") or ""):  # modèle qui met du temps à répondre
            time.sleep(1.5)
        if "format" in p:
            lines = re.findall(r"^(\d+)\. (\S+)", last["content"], re.M)
            out = []
            for n, name in lines:
                ext = name.rsplit(".", 1)[-1].lower()
                folder = {"pdf": "Administratif/Factures", "jpg": "Photos", "png": "Photos", "txt": "Notes",
                          "deb": "Logiciels"}.get(ext, "À trier")
                out.append({"n": int(n), "dossier": folder, "raison": f"extension {ext}"})
            return self.j({"message": {"role": "assistant", "content": json.dumps({"classement": out})}, "done": True})
        chunks = []
        names = [t["function"]["name"] for t in p.get("tools") or []]
        libre = "ouvrir_application" in names and "creer_dossier" not in names
        if libre and last["role"] == "user" and last.get("content", "").lower().startswith("ouvre "):
            nom = last["content"].split(" ", 1)[1]
            tc = [{"function": {"name": "ouvrir_application", "arguments": {"nom": nom}}}]
            chunks = [{"message": {"role": "assistant", "content": "", "tool_calls": tc}, "done": False}]
        elif libre and last["role"] == "tool":
            chunks = [{"message": {"role": "assistant", "content": "C'est ouvert."}, "done": False}]
        elif p.get("tools") and not libre:
            if last["role"] == "user":
                tc = [{"function": {"name": "lister_dossier", "arguments": {}}}]
                chunks = [{"message": {"role": "assistant", "content": "Je regarde le dossier.", "tool_calls": tc}, "done": False}]
            elif last["role"] == "tool" and last.get("tool_name") == "lister_dossier" and "creer_dossier" in names:
                tc = [{"function": {"name": "creer_dossier", "arguments": {"chemin": "Rangement-test"}}},
                      {"function": {"name": "lire_fichier", "arguments": {"chemin": "note.txt"}}}]
                chunks = [{"message": {"role": "assistant", "content": "", "tool_calls": tc}, "done": False}]
            else:
                chunks = [{"message": {"role": "assistant", "content": w}, "done": False}
                          for w in ["C'est ", "fait : ", "dossier ", "traité."]]
        else:
            if p.get("think"):
                chunks += [{"message": {"role": "assistant", "content": "", "thinking": t}, "done": False}
                           for t in ["Je réfléchis ", "à la question…"]]
            text = "Bonjour **Cyril** ! Voici une liste :\n\n- un\n- deux\n\n```python\nprint('ok')\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
            if last.get("images"):
                text = f"Je vois {len(last['images'])} image(s). "
            for i in range(0, len(text), 12):
                chunks.append({"message": {"role": "assistant", "content": text[i:i + 12]}, "done": False})
        chunks.append({"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 42,
                       "eval_duration": 700000000, "done_reason": "stop"})
        self.stream(chunks)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
