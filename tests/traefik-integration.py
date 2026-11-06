#!/usr/bin/env python3
"""Run Traefik, the test frontend and a mock backend on an isolated Docker network."""

import http.client
import shutil
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT.parent / "ritmerobot-frontend"
DOMAIN = "ritmerobot-test.local"


def docker(*args):
    result = subprocess.run(["docker", *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Docker command failed: {' '.join(args)}\n{result.stderr}")
    return result.stdout.strip()


def cleanup_docker(*args):
    subprocess.run(["docker", *args], capture_output=True, check=False)


class TraefikIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise RuntimeError("Docker is required for the Traefik integration test")
        docker("info", "--format", "{{.ServerVersion}}")
        cls.tmp = tempfile.TemporaryDirectory(prefix="ritmerobot-traefik-integration-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        suffix = uuid.uuid4().hex[:10]
        cls.network = "ritmerobot-test-check-" + suffix
        cls.backend = "ritmerobot-test-backend-" + suffix
        cls.frontend = "ritmerobot-test-frontend-" + suffix
        cls.proxy = "ritmerobot-test-proxy-" + suffix
        image = "ritmerobot-test-frontend:integration-" + suffix

        docker("network", "create", cls.network)
        cls.addClassCleanup(cleanup_docker, "network", "rm", cls.network)

        context = root / "frontend"
        context.mkdir()
        shutil.copy2(FRONTEND_ROOT / "nginx.conf", context / "nginx.conf")
        (context / "dockerfile").write_text(
            "FROM nginx:1.28-alpine\n"
            "ENV NGINX_ENVSUBST_FILTER=\"^BACKEND_UPSTREAM$\"\n"
            "COPY nginx.conf /etc/nginx/templates/default.conf.template\n"
            "COPY dist/ /usr/share/nginx/html/\n"
            "EXPOSE 5173\n",
            encoding="utf-8",
        )
        for name, contents in {
            "index.html": "PLAYER", "admin/index.html": "ADMIN",
            "play/ritme_robot.js": "ENGINE", "play/ritme_robot.wasm": "WASM",
            "play/ritme_robot.pck": "PACK", "play/player.js": "PLAYER JS",
            "legacy-service-worker.js": "LEGACY WORKER",
        }.items():
            path = context / "dist" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        docker("build", "--quiet", "-t", image, str(context))
        cls.addClassCleanup(cleanup_docker, "image", "rm", image)

        docker("run", "-d", "--rm", "--name", cls.backend, "--network", cls.network,
               "--network-alias", "backend", "nginx:1.28-alpine")
        cls.addClassCleanup(cleanup_docker, "rm", "-f", cls.backend)
        backend_config = root / "backend.conf"
        backend_config.write_text(
            'server { listen 8000; '
            'location = /api/auth/validate { if ($http_cookie = "access_token=valid") { return 200 "VALID"; } return 403; } '
            'location ~ ^/api/auth/(login|verify)$ { if ($http_cookie != "") { return 400; } '
            'add_header Set-Cookie "access_token=valid; Path=/; HttpOnly" always; '
            'add_header Set-Cookie "license_vendor=fixture; Path=/" always; return 200 "LOGIN"; } '
            'location = /api/health { return 200 "HEALTH"; } }\n', encoding="utf-8"
        )
        docker("cp", str(backend_config), cls.backend + ":/etc/nginx/conf.d/default.conf")
        docker("exec", cls.backend, "nginx", "-s", "reload")

        docker("run", "-d", "--rm", "--name", cls.frontend, "--network", cls.network,
               "--network-alias", "frontend", "-e", "BACKEND_UPSTREAM=backend:8000", image)
        cls.addClassCleanup(cleanup_docker, "rm", "-f", cls.frontend)

        routes = (ROOT / "deployment/traefik/routes.yml.template").read_text(encoding="utf-8")
        if routes.count("tls: {certResolver: letsencrypt}") != 3:
            raise AssertionError("Expected three TLS routers using the Let's Encrypt resolver")
        # Local test uses Traefik's temporary self-signed certificate; no ACME request is made.
        routes = routes.replace("__TEST_DOMAIN__", DOMAIN).replace("tls: {certResolver: letsencrypt}", "tls: {}")
        route_file = root / "routes.yml"
        route_file.write_text(routes, encoding="utf-8")
        docker("create", "--name", cls.proxy, "--network", cls.network,
               "-p", "127.0.0.1::8080", "-p", "127.0.0.1::8443", "traefik:v3.6",
               "--providers.file.filename=/tmp/routes.yml", "--providers.file.watch=false",
               "--entrypoints.web.address=:8080", "--entrypoints.web.http.redirections.entrypoint.to=websecure",
               "--entrypoints.web.http.redirections.entrypoint.scheme=https",
               "--entrypoints.websecure.address=:8443", "--log.level=ERROR")
        cls.addClassCleanup(cleanup_docker, "rm", "-f", cls.proxy)
        docker("cp", str(route_file), cls.proxy + ":/tmp/routes.yml")
        docker("start", cls.proxy)
        cls.https_port = int(docker("port", cls.proxy, "8443/tcp").splitlines()[0].rsplit(":", 1)[1])
        cls.http_port = int(docker("port", cls.proxy, "8080/tcp").splitlines()[0].rsplit(":", 1)[1])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if cls.request("/")[0] == 200 and cls.request("/api/health")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.2)
        raise RuntimeError("Traefik routes did not become ready: " + docker("logs", cls.proxy))

    @classmethod
    def request(cls, path, cookie=None, method="GET", host=DOMAIN, secure=True):
        port = cls.https_port if secure else cls.http_port
        if secure:
            connection = http.client.HTTPSConnection("127.0.0.1", port, timeout=5,
                                                    context=ssl._create_unverified_context())
        else:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            headers = {"Host": host}
            if cookie:
                headers["Cookie"] = cookie
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, response.msg, response.read()
        finally:
            connection.close()

    def test_frontend_and_backend_routes(self):
        status, headers, body = self.request("/")
        self.assertEqual((status, body), (200, b"PLAYER"))
        self.assertEqual(headers.get("Cross-Origin-Embedder-Policy"), "require-corp")
        self.assertEqual(self.request("/admin/login")[::2], (200, b"ADMIN"))
        self.assertEqual(self.request("/api/health")[::2], (200, b"HEALTH"))
        self.assertEqual(self.request("/", host="other.example")[0], 404)
        status, headers, _ = self.request("/", secure=False)
        self.assertIn(status, (301, 302, 307, 308))
        self.assertTrue(headers.get("Location", "").startswith("https://"))

    def test_login_clears_expired_cookie_and_preserves_secure_session(self):
        for path in ("/api/auth/login", "/api/auth/verify"):
            status, headers, body = self.request(path, "access_token=expired", method="POST")
            self.assertEqual((status, body), (200, b"LOGIN"))
            self.assertEqual(headers.get("Cache-Control"), "no-store")
            cookies = headers.get_all("Set-Cookie") or []
            session = next((cookie for cookie in cookies if cookie.startswith("access_token=")), "")
            self.assertIn("Secure", session)
            self.assertIn("HttpOnly", session)
            self.assertTrue(any(cookie.startswith("license_vendor=") for cookie in cookies))

    def test_game_downloads_require_a_valid_backend_session(self):
        for path in ("/play/ritme_robot.js", "/play/ritme_robot.wasm", "/play/ritme_robot.pck"):
            self.assertEqual(self.request(path)[0], 403, path)
            self.assertEqual(self.request(path, "access_token=valid")[0], 200, path)
        self.assertEqual(self.request("/api/auth/validate", "access_token=valid")[::2], (200, b"VALID"))
        self.assertEqual(self.request("/play/missing.wasm", "access_token=valid")[0], 404)
        self.assertEqual(self.request("/_ritmerobot_license_check", "access_token=valid")[0], 404)


class ComposeIntegrationTest(unittest.TestCase):
    def test_compose_routes_the_test_stack(self):
        if not shutil.which("docker"):
            self.fail("Docker and Docker Compose are required for this test")
        project = "rrtest" + uuid.uuid4().hex[:10]
        with tempfile.TemporaryDirectory(prefix="ritmerobot-compose-test-") as temporary:
            root = Path(temporary)
            frontend = root / "frontend"
            frontend.mkdir()
            shutil.copy2(FRONTEND_ROOT / "nginx.conf", frontend / "nginx.conf")
            (frontend / "dockerfile").write_text(
                "FROM nginx:1.28-alpine\n"
                "ENV NGINX_ENVSUBST_FILTER=\"^BACKEND_UPSTREAM$\"\n"
                "COPY nginx.conf /etc/nginx/templates/default.conf.template\n"
                "COPY dist/ /usr/share/nginx/html/\n"
                "EXPOSE 5173\n",
                encoding="utf-8",
            )
            for name, contents in {"index.html": "PLAYER", "admin/index.html": "ADMIN",
                                   "play/ritme_robot.wasm": "WASM"}.items():
                target = frontend / "dist" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents, encoding="utf-8")
            (root / "game-export").mkdir()
            (root / "game-shell").mkdir()

            backend = root / "backend"
            backend.mkdir()
            (backend / "dockerfile").write_text(
                "FROM nginx:1.28-alpine\nRUN mkdir -p /app\nCOPY nginx.conf /etc/nginx/conf.d/default.conf\n",
                encoding="utf-8"
            )
            (backend / "nginx.conf").write_text(
                'server { listen 8000; '
                'location = /api/auth/validate { if ($http_cookie = "access_token=valid") { return 200; } return 403; } '
                'location ~ ^/api/auth/(login|verify)$ { if ($http_cookie != "") { return 400; } '
                'add_header Set-Cookie "access_token=valid; Path=/; HttpOnly" always; return 200 "LOGIN"; } '
                'location = /api/health { return 200 "HEALTH"; } }\n', encoding="utf-8"
            )
            (root / "backend.env").write_text("fixture\n", encoding="utf-8")
            (root / ".env").write_text("ACME_EMAIL=fixture@example.invalid\n", encoding="utf-8")
            routes = (ROOT / "deployment/traefik/routes.yml.template").read_text(encoding="utf-8")
            routes = routes.replace("__TEST_DOMAIN__", DOMAIN).replace("tls: {certResolver: letsencrypt}", "tls: {}")
            (root / "traefik").mkdir()
            (root / "traefik/routes.yml").write_text(routes, encoding="utf-8")
            compose = (ROOT / "deployment/compose.yaml").read_text(encoding="utf-8")
            compose = compose.replace('"80:80"', '"127.0.0.1::80"').replace('"443:443"', '"127.0.0.1::443"')
            # Real certificate issuance is tested on the VPS; local tests use Traefik's temporary certificate.
            compose = "\n".join(line for line in compose.splitlines() if "--certificatesresolvers." not in line) + "\n"
            (root / "compose.yaml").write_text(compose, encoding="utf-8")
            command = ["compose", "--project-name", project, "--env-file", str(root / ".env"),
                       "-f", str(root / "compose.yaml")]
            try:
                docker(*command, "up", "-d", "--build")
                port = int(docker(*command, "port", "traefik", "443").splitlines()[0].rsplit(":", 1)[1])

                def request(path, cookie=None, method="GET"):
                    connection = http.client.HTTPSConnection("127.0.0.1", port, timeout=5,
                                                            context=ssl._create_unverified_context())
                    try:
                        headers = {"Host": DOMAIN}
                        if cookie:
                            headers["Cookie"] = cookie
                        connection.request(method, path, headers=headers)
                        response = connection.getresponse()
                        return response.status, response.msg, response.read()
                    finally:
                        connection.close()

                deadline = time.monotonic() + 30
                while True:
                    try:
                        if request("/")[0] == 200 and request("/api/health")[0] == 200:
                            break
                    except OSError:
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Compose test routes did not become ready")
                    time.sleep(0.2)
                self.assertEqual(request("/")[::2], (200, b"PLAYER"))
                self.assertEqual(request("/api/health")[::2], (200, b"HEALTH"))
                status, headers, _ = request("/api/auth/login", "access_token=expired", method="POST")
                self.assertEqual(status, 200)
                self.assertIn("Secure", headers.get("Set-Cookie", ""))
                self.assertEqual(request("/play/ritme_robot.wasm")[0], 403)
                self.assertEqual(request("/play/ritme_robot.wasm", "access_token=valid")[0], 200)
            finally:
                cleanup_docker(*command, "down", "--volumes", "--remove-orphans")
                cleanup_docker("image", "rm", project + "-frontend", project + "-backend")


if __name__ == "__main__":
    unittest.main(verbosity=2)
