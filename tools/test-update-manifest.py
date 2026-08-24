#!/usr/bin/env python3
"""Regression tests for stable/bootstrap and beta update metadata."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools/render-update-manifest.sh"


def render(version: str, tag: str) -> str:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "manifest"
        subprocess.run(
            [
                str(RENDERER),
                version,
                tag,
                "moonlight.iso",
                "a" * 64,
                "1234",
                str(output),
            ],
            check=True,
        )
        return output.read_text(encoding="utf-8")


stable = render("0.2.7.1", "v0.2.7.1")
assert stable == (
    "format=1\n"
    "version=0.2.7.1\n"
    "iso=moonlight.iso\n"
    f"sha256={'a' * 64}\n"
    "size=1234\n"
)
# This is the format gate used by the updater shipped in Moonlight OS 0.2.6.
assert stable.count("format=") == 1
assert dict(line.split("=", 1) for line in stable.splitlines())["format"] == "1"

beta = render("0.2.8~beta.1", "v0.2.8-beta.1")
assert beta == (
    "format=2\n"
    "version=0.2.8~beta.1\n"
    "tag=v0.2.8-beta.1\n"
    "iso=moonlight.iso\n"
    f"sha256={'a' * 64}\n"
    "size=1234\n"
)

print("Moonlight OS update manifest compatibility: ok")
