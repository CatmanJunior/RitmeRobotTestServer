#!/usr/bin/env python3
"""Check generation of the test server's Traefik routing configuration."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TraefikConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ritmerobot-traefik-config-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "traefik").mkdir()
        shutil.copy2(ROOT / "deployment/scripts/configure-traefik.sh", self.root / "scripts")
        shutil.copy2(ROOT / "deployment/traefik/routes.yml.template", self.root / "traefik")
        self.script = self.root / "scripts/configure-traefik.sh"
        self.output = self.root / "traefik/routes.yml"

    def run_setup(self, domain):
        return subprocess.run(["bash", str(self.script), domain], cwd=self.root,
                              text=True, capture_output=True)

    def test_creates_routing_for_the_given_domain(self):
        result = self.run_setup("test.example.com")
        self.assertEqual(result.returncode, 0, result.stderr)
        contents = self.output.read_text(encoding="utf-8")
        self.assertIn("Host(`test.example.com`)", contents)
        self.assertNotIn("__TEST_DOMAIN__", contents)
        self.assertIn("http://frontend:8080", contents)
        self.assertIn("http://backend:8000", contents)
        self.assertIn("certResolver: letsencrypt", contents)

    def test_rejects_invalid_domains_without_writing_routes(self):
        for domain in ("", "localhost", "-bad.example", "example..com", "https://example.com",
                       "test.example.com;echo bad", "x" * 64 + ".example"):
            with self.subTest(domain=domain):
                self.assertNotEqual(self.run_setup(domain).returncode, 0)
                self.assertFalse(self.output.exists())

    def test_does_not_overwrite_existing_routes(self):
        self.output.write_text("existing routes", encoding="utf-8")
        self.assertNotEqual(self.run_setup("test.example.com").returncode, 0)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "existing routes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
