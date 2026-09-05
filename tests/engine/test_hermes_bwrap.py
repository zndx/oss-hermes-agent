"""bubblewrap jail helper for devenv engine + dashboard."""
from __future__ import annotations

import os
import stat
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts/lib/hermes-bwrap.sh"
ENGINE = ROOT / "scripts/processes/hermes-engine.sh"
DASHBOARD = ROOT / "scripts/processes/hermes-dashboard.sh"


def _run(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", f"source {LIB} && {script}"],
        cwd=str(ROOT),
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


class HermesBwrapTests(unittest.TestCase):
    def test_scripts_are_executable(self) -> None:
        for path in (ENGINE, DASHBOARD):
            self.assertTrue(path.is_file(), path)
            self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR, path)

    def test_missing_bwrap_denies(self) -> None:
        proc = _run(
            "hermes_bwrap_exec true",
            env={"HERMES_BWRAP_BIN": "/nope/bwrap", "HERMES_BWRAP": "1", "HERMES_ROOT": str(ROOT)},
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("DENY", proc.stderr)
        self.assertIn("bubblewrap", proc.stderr)

    def test_skip_flag_execs_without_jail(self) -> None:
        proc = _run(
            "hermes_bwrap_exec /bin/echo ok",
            env={"HERMES_BWRAP": "0", "HERMES_ROOT": str(ROOT)},
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "ok")

    def test_print_argv_mentions_fake_home(self) -> None:
        bwrap = ROOT / ".devenv/profile/bin/bwrap"
        if not bwrap.is_file():
            self.skipTest("devenv bubblewrap not installed yet")
        proc = _run(
            "hermes_bwrap_exec /bin/true",
            env={
                "HERMES_BWRAP": "1",
                "HERMES_BWRAP_PRINT": "1",
                "HERMES_BWRAP_BIN": str(bwrap),
                "HERMES_ROOT": str(ROOT),
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("/home/hermes", proc.stderr)
        self.assertIn("--setenv HOME", proc.stderr)
        self.assertIn(str(ROOT), proc.stderr)


if __name__ == "__main__":
    unittest.main()
