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
    old_version = "6.12.101+deb13-amd64"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        payload = root / "target/usr/lib/moonlight-os/boot-payload"
        modules = root / "target/lib/modules"
        boot = root / "shared-boot"
        payload.mkdir(parents=True)
        (modules / version).mkdir(parents=True)
        boot.mkdir()
        expected = b"new signed kernel image\n"
        (payload / f"vmlinuz-{version}").write_bytes(expected)
        (boot / f"vmlinuz-{old_version}").write_bytes(b"old kernel\n")
        (boot / f"initrd.img-{old_version}").write_bytes(b"old initrd\n")
        fake_mkinitramfs = root / "mkinitramfs"
        fake_mkinitramfs.write_text(
            "#!/bin/sh\nset -eu\n"
            "[ \"$1\" = -o ]\n"
            "printf 'generated initrd for %s\\n' \"$3\" > \"$2\"\n",
            encoding="utf-8",
        )
        fake_mkinitramfs.chmod(0o755)

        environment = os.environ.copy()
        environment["MOONLIGHT_KERNEL_PAYLOAD_DIR"] = str(payload)
        environment["MOONLIGHT_KERNEL_BOOT_DIR"] = str(boot)
        environment["MOONLIGHT_KERNEL_MODULES_DIR"] = str(modules)
        environment["MOONLIGHT_MKINITRAMFS"] = str(fake_mkinitramfs)
        # The old updater invokes the hook for its existing .101 initrd. The
        # hook must discover and prepare .105 independently of that argument.
        subprocess.run([str(HANDOFF), old_version], check=True, env=environment)

        assert (boot / f"vmlinuz-{version}").read_bytes() == expected
        assert (boot / f"initrd.img-{version}").read_text(encoding="utf-8") == (
            f"generated initrd for {version}\n"
        )
        assert not (boot / f"vmlinuz-{version}.new").exists()
        assert not (boot / f"initrd.img-{version}.new").exists()


def test_current_updater_copies_before_chroot() -> None:
    validate = UPDATER.index('"$SOURCE_MOUNT/boot/vmlinuz-$kernel_version"')
    bind = UPDATER.index("\n\tbind_target", validate)
    chroot = UPDATER.index('chroot "$TARGET"', bind)
    assert validate < bind < chroot
    assert "/usr/lib/moonlight-os/boot-payload" in BUILD_HOOK
    assert 'update-initramfs "$initramfs_mode"' in UPDATER
    assert "update-initramfs -u -k all" not in UPDATER


if __name__ == "__main__":
    test_old_updater_bootstrap()
    test_current_updater_copies_before_chroot()
    print("Moonlight OS kernel handoff: ok")
