#!/usr/bin/env python3
"""Exercise the test frontend's Nginx routing with a small backend fixture."""

import http.client
import http.server
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT.parent / "ritmerobot-frontend/nginx.conf"
NGINX_BIN = os.environ.get("NGINX_BIN", "nginx")
MIME_TYPES = os.environ.get("NGINX_MIME_TYPES", "/etc/nginx/mime.types")


class Backend(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/auth/validate":
            self.send_response(404)
        elif self.headers.get("Cookie") == "access_token=valid":
            self.send_response(200)
        elif self.headers.get("Cookie") == "access_token=expired":
            self.send_response(400)
        else:
            self.send_response(403)
        self.end_headers()

    def do_POST(self):
        if self.path not in ("/api/auth/login", "/api/auth/verify"):
            self.send_response(404)
        elif self.headers.get("Cookie"):
            self.send_response(400)
        else:
            self.send_response(200)
            self.send_header("Set-Cookie", "access_token=valid; Path=/; HttpOnly")
            self.send_header("Set-Cookie", "license_vendor=fixture; Path=/")
        self.end_headers()

    def log_message(self, *_args):
        pass


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestFrontendNginx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template = CONFIG.read_text(encoding="utf-8")
        if "${BACKEND_UPSTREAM}" not in template or "listen 5173;" not in template:
            raise AssertionError("Test frontend Nginx must use the container configuration template")
        if not shutil.which(NGINX_BIN):
            raise RuntimeError("Nginx is required; set NGINX_BIN to the executable")
        if not Path(MIME_TYPES).is_file():
            raise RuntimeError("Set NGINX_MIME_TYPES to Nginx's mime.types file")

        cls.tmp = tempfile.TemporaryDirectory(prefix="ritmerobot-nginx-test-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        assets = root / "dist"
        for name, contents in {
            "index.html": "PLAYER SHELL",
            "admin/index.html": "ADMIN SHELL",
            "admin/assets/app.js": "ADMIN JS",
            "play/player.js": "PLAYER JS",
            "play/ritme_robot.js": "ENGINE JS",
            "play/ritme_robot.audio.worklet.js": "AUDIO JS",
            "play/ritme_robot.wasm": "WASM",
            "play/soundfont.wasm": "SOUNDFONT",
            "play/ritme_robot.pck": "PACK",
            "manifest.webmanifest": "{}",
            "service-worker.js": "CURRENT WORKER",
            "legacy-service-worker.js": "OLD WORKER",
        }.items():
            path = assets / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")

        cls.backend = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        threading.Thread(target=cls.backend.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.backend.server_close)
        cls.addClassCleanup(cls.backend.shutdown)
        cls.port = free_port()

        config = template.replace("${BACKEND_UPSTREAM}", f"127.0.0.1:{cls.backend.server_port}")
        config = config.replace("listen 5173;", f"listen 127.0.0.1:{cls.port};")
        config = config.replace("/usr/share/nginx/html", str(assets))
        temp_dirs = "\n".join(
            f"{name} {root / name};"
            for name in (
                "client_body_temp_path", "proxy_temp_path", "fastcgi_temp_path",
                "uwsgi_temp_path", "scgi_temp_path",
            )
        )
        full_config = (
            f"pid {root / 'nginx.pid'};\nerror_log stderr;\nevents {{}}\nhttp {{\n"
            f"include {MIME_TYPES};\ndefault_type application/octet-stream;\n"
            f"access_log off;\n{temp_dirs}\n{config}\n}}\n"
        )
        config_file = root / "nginx.conf"
        config_file.write_text(full_config, encoding="utf-8")
        command = [NGINX_BIN, "-p", str(root) + "/", "-c", str(config_file)]
        subprocess.run(command + ["-t"], check=True)
        cls.log_file = (root / "nginx.log").open("w+", encoding="utf-8")
        cls.addClassCleanup(cls.log_file.close)
        cls.nginx = subprocess.Popen(command + ["-g", "daemon off;"], stderr=cls.log_file)
        cls.addClassCleanup(cls.stop_nginx)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cls.nginx.poll() is not None:
                cls.log_file.flush()
                raise RuntimeError(f"Nginx stopped during startup: {(root / 'nginx.log').read_text()}")
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("Nginx did not start")

    @classmethod
    def stop_nginx(cls):
        if cls.nginx.poll() is None:
            cls.nginx.terminate()
            cls.nginx.wait(timeout=5)

    def request(self, path, cookie=None, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, headers={"Cookie": cookie} if cookie else {})
            response = connection.getresponse()
            return response.status, response.msg, response.read()
        finally:
            connection.close()

    def test_player_admin_and_missing_assets(self):
        status, headers, body = self.request("/")
        self.assertEqual((status, body), (200, b"PLAYER SHELL"))
        self.assertEqual(headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertEqual(headers.get("Cross-Origin-Embedder-Policy"), "require-corp")
        self.assertEqual(headers.get("Cache-Control"), "no-cache")
        for path in ("/admin/", "/admin/login", "/admin/licenses/3"):
            self.assertEqual(self.request(path)[::2], (200, b"ADMIN SHELL"))
        self.assertEqual(self.request("/admin/assets/app.js")[::2], (200, b"ADMIN JS"))
        status, headers, _ = self.request("/admin/assets/missing.js")
        self.assertEqual(status, 404)
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertEqual(self.request("/play/player.js")[::2], (200, b"PLAYER JS"))

    def test_redirects_remain_on_the_public_proxy_origin(self):
        for path, expected_status, expected_location in (
            ("/admin", 308, "/admin/"), ("/play", 302, "/"), ("/play/", 302, "/"),
        ):
            status, headers, _ = self.request(path)
            self.assertEqual((status, headers.get("Location")), (expected_status, expected_location))

    def test_game_files_require_a_valid_backend_session(self):
        for path in ("/play/ritme_robot.js", "/play/ritme_robot.audio.worklet.js",
                     "/play/ritme_robot.wasm", "/play/soundfont.wasm", "/play/ritme_robot.pck"):
            self.assertEqual(self.request(path)[0], 403, path)
            self.assertEqual(self.request(path, "access_token=expired")[0], 401, path)
            self.assertEqual(self.request(path, "access_token=valid")[0], 200, path)
        status, headers, _ = self.request("/play/ritme_robot.wasm", "access_token=valid")
        self.assertEqual((status, headers.get("Content-Type")), (200, "application/wasm"))
        status, headers, _ = self.request("/play/missing.wasm", "access_token=valid")
        self.assertEqual((status, headers.get("Cache-Control")), (404, "no-store"))

    def test_api_is_for_traefik_and_auth_subrequest_is_internal(self):
        self.assertEqual(self.request("/api/auth/validate", "access_token=valid")[0], 404)
        self.assertEqual(self.request("/_ritmerobot_license_check", "access_token=valid")[0], 404)

    def test_login_and_verify_clear_stale_cookies_and_secure_session_cookie(self):
        for path in ("/api/auth/login", "/api/auth/verify"):
            status, headers, _ = self.request(path, "access_token=expired", method="POST")
            self.assertEqual(status, 200, path)
            cookies = headers.get_all("Set-Cookie") or []
            session = next((cookie for cookie in cookies if cookie.startswith("access_token=")), "")
            self.assertIn("Secure", session)
            self.assertIn("HttpOnly", session)
            self.assertTrue(any(cookie.startswith("license_vendor=") for cookie in cookies))

    def test_manifest_and_legacy_service_worker(self):
        status, headers, _ = self.request("/manifest.webmanifest")
        self.assertEqual((status, headers.get("Content-Type")), (200, "application/manifest+json"))
        status, headers, body = self.request("/play/service-worker.js")
        self.assertEqual((status, body), (200, b"OLD WORKER"))
        self.assertEqual(headers.get("Service-Worker-Allowed"), "/")
        self.assertEqual(headers.get("Cross-Origin-Embedder-Policy"), "require-corp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
