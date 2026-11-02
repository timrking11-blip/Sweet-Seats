"""Static guard: server-only configuration never reaches the web client.

Standard library only. The server-only variable list comes from .env.example, so a
new provider key is covered as soon as it is documented there.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
SKIP_DIRS = {"node_modules", ".next", "out"}
SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".css"}
# next.config.ts runs on the build/server host, never in the browser.
SERVER_CONFIG = {"next.config.ts"}
ALLOWED_SERVER_ENV = {"SWEET_SEATS_API_ORIGIN"}
ALLOWED_PUBLIC_ENV = {"NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"}


def documented_variables() -> set[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, re.MULTILINE))


def server_only_variables() -> set[str]:
    names = documented_variables()
    return {n for n in names if not n.startswith("NEXT_PUBLIC_")} - ALLOWED_SERVER_ENV


def web_sources():
    for path in sorted(WEB.rglob("*")):
        relative = path.relative_to(WEB)
        if (path.is_file() and path.suffix in SOURCE_SUFFIXES
                and not SKIP_DIRS & set(relative.parts) and path.name != "package-lock.json"):
            yield relative.as_posix(), path.read_text(encoding="utf-8")


class FrontendSecretBoundaryTests(unittest.TestCase):
    def test_server_only_variables_never_appear_in_web_sources(self):
        secrets = server_only_variables()
        self.assertTrue({"TICKETMASTER_API_KEY", "SUPABASE_SERVICE_ROLE_KEY"} <= secrets)
        scanned = 0
        for relative, text in web_sources():
            scanned += 1
            for name in secrets:
                self.assertNotIn(name, text, f"{name} referenced in apps/web/{relative}")
        self.assertGreater(scanned, 5)

    def test_environment_is_read_only_by_server_config_and_only_allowlisted(self):
        for relative, text in web_sources():
            # Dynamic process.env[...] access yields "" and therefore fails the allowlist.
            reads = set(re.findall(r"process\.env(?:\.([A-Za-z0-9_]+)|\[)", text))
            if reads:
                self.assertIn(relative, SERVER_CONFIG, f"apps/web/{relative} reads process.env")
                self.assertLessEqual(reads, ALLOWED_SERVER_ENV, f"apps/web/{relative}")

    def test_only_allowlisted_variables_use_the_public_prefix(self):
        public = {n for n in documented_variables() if n.startswith("NEXT_PUBLIC_")}
        self.assertLessEqual(public, ALLOWED_PUBLIC_ENV)
        for relative, text in web_sources():
            exposed = set(re.findall(r"NEXT_PUBLIC_[A-Z0-9_]+", text)) - ALLOWED_PUBLIC_ENV
            self.assertFalse(exposed, f"apps/web/{relative} exposes {sorted(exposed)}")

    def test_built_client_bundle_has_no_server_only_names(self):
        static = WEB / ".next" / "static"
        if not static.is_dir():
            self.skipTest("apps/web has not been built")
        secrets = server_only_variables() | ALLOWED_SERVER_ENV
        for path in static.rglob("*.js"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in secrets:
                self.assertNotIn(name, text, f"{name} in client bundle {path.name}")


if __name__ == "__main__":
    unittest.main()
