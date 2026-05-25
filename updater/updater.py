"""Updater service: listens for update requests and runs git pull + docker compose rebuild."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json
import os

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/project")


class UpdateHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/update":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                # Git pull
                r1 = subprocess.run(["git", "pull"], cwd=PROJECT_DIR,
                                    capture_output=True, text=True, timeout=30)
                git_out = (r1.stdout + r1.stderr).strip()

                # Rebuild and restart
                r2 = subprocess.run(["docker", "compose", "up", "-d", "--build"],
                                    cwd=PROJECT_DIR, capture_output=True, text=True, timeout=600)
                compose_out = (r2.stdout + r2.stderr).strip()

                result = {"status": "ok", "git": git_out, "compose": compose_out}
            except Exception as e:
                result = {"status": "error", "error": str(e)}

            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[updater] {args[0]}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 9090), UpdateHandler)
    print("[updater] Listening on :9090")
    server.serve_forever()
