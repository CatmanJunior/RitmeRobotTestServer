"""Check that the test-server bundle uses its own output and excludes secrets."""

from pathlib import Path
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("pwsh") and shutil.which("tar.exe") and shutil.which("git"),
                     "Requires PowerShell, Git and Windows tar.exe")
class TestBundle(unittest.TestCase):
    def test_local_deployment_secrets_and_data_are_ignored(self):
        for name in ("deployment/.env", "deployment/backend.env", "deployment/data/backup.json",
                     "deployment/traefik/routes.yml", "deployment/frontend/dist/index.html"):
            with self.subTest(path=name):
                result = subprocess.run(["git", "check-ignore", "--no-index", "--quiet", name], cwd=ROOT)
                self.assertEqual(result.returncode, 0, f"{name} must stay out of Git")

    def prepare_fixture(self, root):
        server = root / "frontend" / "RitmeRobotTestServer"
        frontend = root / "frontend" / "ritmerobot-frontend"
        backend = root / "backend" / "ritmerobot-backend"
        frontend.mkdir(parents=True)
        backend.mkdir(parents=True)
        (server / "scripts").mkdir(parents=True)
        shutil.copy2(ROOT / "scripts/package-vps-test.ps1", server / "scripts")
        shutil.copytree(ROOT / "deployment", server / "deployment")
        (server / "deployment/.env").write_text("local environment", encoding="utf-8")
        (server / "deployment/traefik/routes.yml").write_text("local routes", encoding="utf-8")
        for name, contents in {
            "index.html": "player", "manifest.webmanifest": "{}", "service-worker.js": "worker",
            "legacy-service-worker.js": "old worker", "admin/index.html": "admin",
            "play/build-version.txt": "0123456789abcdef0123", "play/game.pck": "game fixture",
        }.items():
            path = server / "dist" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        for name in ("main.py", "dockerfile", ".env", "data/private.sqlite3"):
            path = backend / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture", encoding="utf-8")
        subprocess.run(["git", "init", "--quiet", str(backend)], check=True)
        subprocess.run(["git", "-C", str(backend), "add", "-f", "main.py", "dockerfile", ".env",
                        "data/private.sqlite3"], check=True)
        return server, frontend

    def test_bundle_uses_server_dist_and_excludes_backend_secrets(self):
        with tempfile.TemporaryDirectory(prefix="ritmerobot-bundle-test-") as temporary:
            server, frontend = self.prepare_fixture(Path(temporary))
            result = subprocess.run(["pwsh", "-NoProfile", "-File", str(server / "scripts/package-vps-test.ps1"),
                                     "-SkipBuild"], cwd=server, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            archives = list((server / "work").glob("ritmerobot-vps-test-*.tar.gz"))
            self.assertEqual(len(archives), 1)
            with tarfile.open(archives[0], "r:gz") as bundle:
                names = {name.removeprefix("./") for name in bundle.getnames()}
            self.assertIn("frontend/dist/play/game.pck", names)
            self.assertIn("frontend/nginx.conf", names)
            self.assertIn("traefik/routes.yml.template", names)
            self.assertIn(".env.example", names)
            self.assertIn("backend/main.py", names)
            self.assertIn("backend/dockerfile", names)
            self.assertNotIn("backend/.env", names)
            self.assertNotIn("backend/data/private.sqlite3", names)
            self.assertNotIn(".env", names)
            self.assertNotIn("traefik/routes.yml", names)
            self.assertFalse((frontend / "dist").exists())

    def test_default_build_uses_server_export_and_output(self):
        with tempfile.TemporaryDirectory(prefix="ritmerobot-bundle-build-") as temporary:
            root = Path(temporary)
            server, frontend = self.prepare_fixture(root)
            (server / ".godot-export").mkdir()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            (bin_dir / "npm.cmd").write_text(
                '@echo off\n'
                f'if /I not "%CD%"=="{frontend}" exit /b 11\n'
                f'if /I not "%GODOT_EXPORT_DIR%"=="{server / ".godot-export"}" exit /b 12\n'
                f'if /I not "%FRONTEND_DIST_DIR%"=="{server / "dist"}" exit /b 13\n'
                'echo invoked > "%FRONTEND_DIST_DIR%\\npm-invoked.txt"\n'
                'exit /b 0\n', encoding="utf-8"
            )
            env = os.environ.copy()
            env.pop("GODOT_EXPORT_DIR", None)
            env.pop("FRONTEND_DIST_DIR", None)
            env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
            result = subprocess.run(["pwsh", "-NoProfile", "-File", str(server / "scripts/package-vps-test.ps1")],
                                    cwd=server, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((server / "dist/npm-invoked.txt").exists())
            self.assertTrue(list((server / "work").glob("ritmerobot-vps-test-*.tar.gz")))
            self.assertFalse((frontend / "dist").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
