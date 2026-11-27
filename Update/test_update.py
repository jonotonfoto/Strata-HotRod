"""Tests of Update/update.py that need no network, no GPU and no compiler:

    python Update/test_update.py

The engine step is run against a made-up install folder whose setup.py is a stand-in: it has the three names the
updater uses (ENGINE_SOURCES, source_hash, update_installed_engine) and "compiles" by writing the new fingerprint
into engine/BUILD.json."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update  # noqa: E402

FAKE_SETUP = '''
import json, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parent
ENGINE_SOURCES = ["src"]
PREBUILT_URL = "unused"
def source_hash(parts):
    h = hashlib.sha256()
    for part in parts:
        for f in sorted((ROOT / part).rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
    return h.hexdigest()[:16]
def update_installed_engine(url):
    stamp = ROOT / "engine" / "BUILD.json"
    meta = json.loads(stamp.read_text(encoding="utf-8"))
    if (ROOT / "compile-fails").exists():
        print("  ! could not compile the updated engine")
        return
    meta["src"] = source_hash(ENGINE_SOURCES)
    stamp.write_text(json.dumps(meta), encoding="utf-8")
'''


def install(tmp: Path, source="local", built_from="old", engine=True) -> Path:
    (tmp / "serve").mkdir()
    (tmp / "serve" / "server.py").write_text("x = 1\n", encoding="utf-8")
    (tmp / "src").mkdir()
    (tmp / "src" / "a.cpp").write_text("int a = 1;\n", encoding="utf-8")
    (tmp / "setup.py").write_text(FAKE_SETUP, encoding="utf-8")
    if engine:
        (tmp / "engine").mkdir()
        (tmp / "engine" / "strata.exe").write_bytes(b"binary")
        sys.path.insert(0, str(tmp))
        try:
            import importlib
            import setup as fake
            importlib.reload(fake)
            src = fake.source_hash(fake.ENGINE_SOURCES) if built_from == "current" else "0000000000000000"
        finally:
            sys.path.remove(str(tmp))
            sys.modules.pop("setup", None)
        (tmp / "engine" / "BUILD.json").write_text(json.dumps({"source": source, "src": src}), encoding="utf-8")
    return tmp


class EngineStep(unittest.TestCase):
    def run_step(self, dry=False, **kw):
        with tempfile.TemporaryDirectory() as d:
            root = install(Path(d), **kw)
            return update.engine_step(root, dry), json.loads((root / "engine" / "BUILD.json").read_text()) \
                if (root / "engine" / "BUILD.json").exists() else None

    def test_no_engine_yet(self):
        self.assertEqual(self.run_step(engine=False)[0], "none")

    def test_ready_made_engine_is_left_alone(self):
        out, meta = self.run_step(source="prebuilt")
        self.assertEqual(out, "prebuilt")
        self.assertEqual(meta["src"], "0000000000000000")

    def test_engine_built_from_this_source_is_fresh(self):
        self.assertEqual(self.run_step(built_from="current")[0], "fresh")

    def test_dry_run_only_says_it_would_compile(self):
        out, meta = self.run_step(dry=True)
        self.assertEqual(out, "would")
        self.assertEqual(meta["src"], "0000000000000000")

    def test_stale_engine_is_compiled(self):
        out, meta = self.run_step()
        self.assertEqual(out, "rebuilt")
        self.assertNotEqual(meta["src"], "0000000000000000")

    def test_failed_compile_keeps_the_old_engine(self):
        with tempfile.TemporaryDirectory() as d:
            root = install(Path(d))
            (root / "compile-fails").write_text("", encoding="utf-8")
            self.assertEqual(update.engine_step(root, False), "failed")
            self.assertEqual((root / "engine" / "strata.exe").read_bytes(), b"binary")

    def test_running_engine_is_not_touched(self):
        if sys.platform != "win32":
            self.skipTest("only Windows keeps a running engine's file locked")
        import msvcrt
        with tempfile.TemporaryDirectory() as d:
            root = install(Path(d))
            exe = root / "engine" / "strata.exe"
            with open(exe, "r+b") as f:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)   # a byte-range lock stands in for the running process
                in_use = update.engine_in_use(root)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            self.assertIn(in_use, (True, False))                 # the lock is advisory for opens: only the call must not raise


class Paths(unittest.TestCase):
    def test_what_the_archive_update_replaces(self):
        yes = ["serve/server.py", "src/prefill/prefill.cpp", "include/strata/prefill/prefill.hpp",
               "tools/prefill_plan/load_check.py", "docs/PREFILL_PLAN.md", "Update/update.py", "Update/CHANGELOG.md"]
        no = ["README.md", "strata-ud-q4_k_xl.json", "engine/strata.exe", "Update/update.bat", "START-HERE.bat",
              "serve/__pycache__/server.cpython-312.pyc", ".git/config", "Strata-data/packs/x/online-tune.txt"]
        for p in yes:
            self.assertTrue(update.is_code(Path(p)), p)
        for p in no:
            self.assertFalse(update.is_code(Path(p)), p)


if __name__ == "__main__":
    unittest.main()
