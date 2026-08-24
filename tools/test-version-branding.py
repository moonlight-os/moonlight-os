#!/usr/bin/env python3
"""Contracts for user-visible Moonlight OS version branding."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]

system_fastfetch = (
    ROOT / "config/includes.chroot/etc/fastfetch/config.jsonc"
).read_text(encoding="utf-8")
user_fastfetch = (
    ROOT / "config/includes.chroot/etc/skel/.config/fastfetch/config.jsonc"
).read_text(encoding="utf-8")
facts = (
    ROOT / "config/includes.chroot/usr/local/bin/moonlight-facts"
).read_text(encoding="utf-8")
build = (ROOT / "build.sh").read_text(encoding="utf-8")
workflow = (ROOT / ".github/workflows/iso.yml").read_text(encoding="utf-8")
version_formatter = ROOT / "tools/format-iso-version.sh"
menu = (
    ROOT / "config/includes.chroot/usr/local/bin/moonlight-menu"
).read_text(encoding="utf-8")

assert system_fastfetch == user_fastfetch
assert '"key": "Moonlight OS", "text": "moonlight-facts os-version"' in system_fastfetch
assert '"key": "Selene",    "text": "moonlight-facts version"' in system_fastfetch
assert "os-version)" in facts
assert "/etc/moonlight-os/release" in facts
assert "/usr/share/moonlight-os/release" in facts
assert "fastfetch --config /etc/fastfetch/config.jsonc" in menu

assert "ISO_VERSION" not in build
assert "ISO_VERSION" not in workflow
assert "tools/format-iso-version.sh" in build
assert 'moonlight-os-${image_version}-${stamp}.iso' in build

for source, expected in (
    ("0.2.8~beta.2", "0.2.8-beta.2"),
    ("v0.2.8-beta.2", "0.2.8-beta.2"),
    ("0:dev", "0-dev"),
):
    result = subprocess.run(
        [str(version_formatter), source],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == expected

bad = subprocess.run(
    [str(version_formatter), "../../unsafe"],
    check=False,
    capture_output=True,
    text=True,
)
assert bad.returncode != 0

print("Moonlight OS version branding: ok")
