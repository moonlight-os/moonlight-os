#!/usr/bin/env python3
"""Regression checks for kernel-changing A/B updates."""

from pathlib import Path
import os
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
UPDATER = (ROOT / "config/includes.chroot/usr/local/sbin/moonlight-update").read_text(
    encoding="utf-8"
)
HANDOFF = (
    ROOT
    / "config/includes.chroot/etc/initramfs/post-update.d/zz-moonlight-kernel-handoff"
)
BUILD_HOOK = (
    ROOT / "config/hooks/normal/9100-moonlight-initramfs.hook.chroot"
).read_text(encoding="utf-8")


def test_old_updater_bootstrap() -> None:
    version = "6.12.105+deb13-amd64"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        payload = root / "target/usr/lib/moonlight-os/boot-payload"
        boot = root / "shared-boot"
        payload.mkdir(parents=True)
        boot.mkdir()
        expected = b"new signed kernel image\n"
        (payload / f"vmlinuz-{version}").write_bytes(expected)
        (boot / "vmlinuz-6.12.101+deb13-amd64").write_bytes(b"old kernel\n")

        environment = os.environ.copy()
        environment["MOONLIGHT_KERNEL_PAYLOAD_DIR"] = str(payload)
        environment["MOONLIGHT_KERNEL_BOOT_DIR"] = str(boot)
        subprocess.run([str(HANDOFF), version], check=True, env=environment)

        assert (boot / f"vmlinuz-{version}").read_bytes() == expected
        assert not (boot / f"vmlinuz-{version}.new").exists()


def test_current_updater_copies_before_chroot() -> None:
    validate = UPDATER.index('"$SOURCE_MOUNT/boot/vmlinuz-$kernel_version"')
    bind = UPDATER.index("\n\tbind_target", validate)
    chroot = UPDATER.index('chroot "$TARGET"', bind)
    assert validate < bind < chroot
    assert "/usr/lib/moonlight-os/boot-payload" in BUILD_HOOK


if __name__ == "__main__":
    test_old_updater_bootstrap()
    test_current_updater_copies_before_chroot()
    print("Moonlight OS kernel handoff: ok")
