#!/usr/bin/env python3
"""Synthetic regression tests for M9's read-only system-disk lease."""

import importlib.machinery
import importlib.util
import json
import os
import socket
import stat
import tempfile
import threading
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "config/includes.chroot/usr/local/bin/moonlight-helper")


def load_helper():
    loader = importlib.machinery.SourceFileLoader("moonlight_helper_disk", HELPER)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


helper = load_helper()


class DiskSessionLeaseTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_state = helper.DISK_SESSION_STATE
        helper.DISK_SESSION_STATE = os.path.join(self.temporary.name, "disk-owned")
        helper.DISK_SESSION_REFS = 0
        helper.DISK_SESSION_INFO = None

    def tearDown(self):
        helper.DISK_SESSION_STATE = self.old_state
        helper.DISK_SESSION_REFS = 0
        helper.DISK_SESSION_INFO = None
        self.temporary.cleanup()

    def info(self):
        return {"device": "/dev/moonlight/root-a", "size": 8 * 1024 * 1024 * 1024,
                "sector_size": 512, "root_source": "/dev/mapper/moonlight-root--a",
                "vg_name": "moonlight", "lv_name": "root-a",
                "snapshot_lv": "session-snapshot-0123456789ab",
                "snapshot_path": "/dev/moonlight/session-snapshot-0123456789ab",
                "backend": "lvm", "vg_free": 3 * 1024 * 1024 * 1024,
                "cow_size": 2 * 1024 * 1024 * 1024,
                "iqn": helper.DISK_TARGET_IQN_PREFIX + "0123456789abcdef",
                "username": "mlos0123456789ab", "password": "0123456789abcdef"}

    def ready(self, info):
        del info
        return {"state": "ready", "cow_used": 4096,
                "cow_capacity": 2 * 1024 * 1024 * 1024}

    def test_discovers_parent_disk_and_geometry_without_caller_path(self):
        answers = {
            "findmnt": ("/dev/mapper/moonlight-root--a\n", None),
            "lvs": (" moonlight|root-a|/dev/moonlight/root-a|8589934592|3221225472\n", None),
            "blockdev-sector": ("512\n", None),
        }

        def fake_run(argv, timeout=30, input_text=None):
            del timeout, input_text
            if argv[0] == "findmnt": return answers["findmnt"]
            if argv[0] == "lvs": return answers["lvs"]
            if argv[:2] == ["blockdev", "--getss"]: return answers["blockdev-sector"]
            raise AssertionError(argv)

        block = mock.Mock(st_mode=stat.S_IFBLK)
        with mock.patch.object(helper, "run", side_effect=fake_run), \
             mock.patch.object(helper.os, "stat", return_value=block):
            info = helper.disk_backing_info()
        self.assertEqual(info["device"], "/dev/moonlight/root-a")
        self.assertEqual(info["size"], 8589934592)
        self.assertEqual(info["cow_size"], 2147483648)
        self.assertEqual(info["sector_size"], 512)

    def test_lease_is_shared_and_last_disconnect_removes_exact_target(self):
        created = []
        removed = []
        first, second = [False], [False]
        def remove(info=None):
            del info
            removed.append(True)
            return True

        with mock.patch.object(helper, "disk_backing_info", side_effect=self.info), \
             mock.patch.object(helper, "disk_target_create", side_effect=lambda info: created.append(info)), \
             mock.patch.object(helper, "disk_target_remove", side_effect=remove), \
             mock.patch.object(helper, "disk_snapshot_status", side_effect=self.ready):
            one = helper.op_disk_session_acquire({}, lambda message: None, first)
            two = helper.op_disk_session_acquire({}, lambda message: None, second)
            self.assertTrue(one["readonly"])
            self.assertEqual(one, two)
            self.assertEqual(len(created), 1)
            self.assertEqual(helper.DISK_SESSION_REFS, 2)
            helper.disk_session_release(first)
            self.assertFalse(removed)
            helper.disk_session_release(second)
            self.assertEqual(removed, [True])
            self.assertEqual(helper.DISK_SESSION_REFS, 0)

    def test_helper_connection_owns_and_releases_disk(self):
        created = []
        removed = []
        client, server = socket.socketpair()
        def remove(info=None):
            del info
            removed.append(True)
            return True

        with mock.patch.object(helper, "disk_backing_info", side_effect=self.info), \
             mock.patch.object(helper, "disk_target_create", side_effect=lambda info: created.append(info)), \
             mock.patch.object(helper, "disk_target_remove", side_effect=remove), \
             mock.patch.object(helper, "disk_snapshot_status", side_effect=self.ready):
            thread = threading.Thread(target=helper.handle_client, args=(server,))
            thread.start()
            stream = client.makefile("rwb")
            stream.write(json.dumps({"id": 1, "op": "disk.session.acquire"}).encode() + b"\n")
            stream.flush()
            reply = json.loads(stream.readline())
            self.assertTrue(reply["ok"])
            self.assertTrue(reply["result"]["iqn"].startswith(helper.DISK_TARGET_IQN_PREFIX))
            self.assertTrue(reply["result"]["snapshot"])
            self.assertEqual(reply["result"]["snapshot_state"], "ready")
            self.assertEqual(reply["result"]["username"], "mlos0123456789ab")
            stream.close()
            client.close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(created), 1)
            self.assertEqual(removed, [True])

    def test_failed_create_clears_journal_and_does_not_take_lease(self):
        owned = [False]
        with mock.patch.object(helper, "disk_backing_info", side_effect=self.info), \
             mock.patch.object(helper, "disk_target_create", side_effect=helper.Error(helper.E_FAILED, "nope")), \
             mock.patch.object(helper, "disk_target_remove", return_value=True):
            with self.assertRaises(helper.Error):
                helper.op_disk_session_acquire({}, lambda message: None, owned)
        self.assertFalse(owned[0])
        self.assertEqual(helper.DISK_SESSION_REFS, 0)
        self.assertFalse(os.path.exists(helper.DISK_SESSION_STATE))

    def test_restart_recovery_is_scoped_to_its_journal(self):
        removed = []
        helper.persist_disk_session(True)
        def remove(info=None):
            del info
            removed.append(True)
            return True

        with mock.patch.object(helper, "disk_target_remove", side_effect=remove):
            helper.recover_disk_session()
        self.assertEqual(removed, [True])
        self.assertFalse(os.path.exists(helper.DISK_SESSION_STATE))

    def test_failed_release_keeps_recovery_journal(self):
        helper.persist_disk_session(True)
        helper.DISK_SESSION_REFS = 1
        helper.DISK_SESSION_INFO = self.info()
        owned = [True]
        with mock.patch.object(helper, "disk_target_remove", return_value=False):
            helper.disk_session_release(owned)
        self.assertFalse(owned[0])
        self.assertTrue(os.path.exists(helper.DISK_SESSION_STATE))

    def test_snapshot_overflow_withdraws_io_and_keeps_cleanup_interlock(self):
        owned = [True]
        helper.DISK_SESSION_REFS = 1
        helper.DISK_SESSION_INFO = self.info()
        withdrawn = []
        with mock.patch.object(helper, "disk_snapshot_status", return_value={
                "state": "overflow", "message": "snapshot copy-on-write storage is full"}), \
             mock.patch.object(helper, "disk_target_withdraw",
                               side_effect=lambda info: withdrawn.append(info) or True):
            with self.assertRaises(helper.Error) as raised:
                helper.op_disk_session_acquire({}, lambda message: None, owned)
        self.assertEqual(raised.exception.code, helper.E_UNAVAILABLE)
        self.assertTrue(owned[0])
        self.assertEqual(helper.DISK_SESSION_REFS, 1)
        self.assertEqual(len(withdrawn), 1)

    def test_raw_partition_installation_is_refused_instead_of_exported_live(self):
        def fake_run(argv, timeout=30, input_text=None):
            del timeout, input_text
            if argv[0] == "findmnt": return ("/dev/mmcblk1p4\n", None)
            if argv[0] == "lvs": return (None, "not an LVM logical volume")
            raise AssertionError(argv)

        with mock.patch.object(helper, "run", side_effect=fake_run):
            with self.assertRaises(helper.Error) as raised:
                helper.disk_backing_info()
        self.assertEqual(raised.exception.code, helper.E_UNAVAILABLE)
        self.assertIn("reinstall", raised.exception.message)

    def test_snapshot_status_reports_usage_and_overflow(self):
        calls = []
        def ready_run(argv, timeout=30, input_text=None):
            del timeout, input_text
            calls.append(argv)
            return " 25.00|swi-a-s---\n", None

        with mock.patch.object(helper, "run", side_effect=ready_run):
            status = helper.disk_snapshot_status(self.info())
        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["cow_used"], 512 * 1024 * 1024)
        self.assertIn("snap_percent,lv_attr", calls[0])
        self.assertNotIn("data_percent,lv_attr", calls[0])
        self.assertNotIn("--readonly", calls[0])

        with mock.patch.object(helper, "run", return_value=(" 100.00|swi-I-s---\n", None)):
            status = helper.disk_snapshot_status(self.info())
        self.assertEqual(status["state"], "overflow")

    def test_journal_never_persists_chap_password(self):
        info = self.info()
        helper.disk_session_journal(info)
        with open(helper.DISK_SESSION_STATE, "r", encoding="utf-8") as stream:
            journal = json.load(stream)
        self.assertEqual(journal["username"], info["username"])
        self.assertNotIn("password", journal)

    def test_unfreeze_retries_and_refuses_to_export(self):
        calls = []

        def fake_run(argv, timeout=30, input_text=None):
            del timeout, input_text
            calls.append(argv)
            if argv[:2] == ["fsfreeze", "--unfreeze"]:
                return None, "filesystem stayed frozen"
            return "", None

        with mock.patch.object(helper, "run", side_effect=fake_run), \
             mock.patch.object(helper.time, "sleep"):
            with self.assertRaises(helper.Error) as raised:
                helper.disk_target_create(self.info())
        self.assertEqual(raised.exception.code, helper.E_FAILED)
        self.assertEqual(sum(argv[:2] == ["fsfreeze", "--unfreeze"] for argv in calls), 3)

    def test_snapshot_is_created_then_made_read_only(self):
        calls = []

        def fake_run(argv, timeout=30, input_text=None):
            del timeout, input_text
            calls.append(argv)
            return "", None

        real_import = __import__
        def fake_import(name, *args, **kwargs):
            if name == "rtslib_fb":
                raise ImportError("stop after LVM setup")
            return real_import(name, *args, **kwargs)

        info = self.info()
        with mock.patch.object(helper, "run", side_effect=fake_run), \
             mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(helper.Error):
                helper.disk_target_create(info)

        lvcreate = next(argv for argv in calls if argv[0] == "lvcreate")
        lvchange = next(argv for argv in calls if argv[0] == "lvchange")
        self.assertNotIn("--permission", lvcreate)
        self.assertIn("backup { backup=0 archive=0 }", lvcreate)
        self.assertEqual(lvcreate[lvcreate.index("--size") + 1], "2048M")
        self.assertEqual(lvchange, [
            "lvchange", "--permission", "r", info["snapshot_path"],
        ])
        self.assertLess(calls.index(["fsfreeze", "--unfreeze", "/"]),
                        calls.index(lvchange))

    def test_rtslib_lock_stays_in_the_helper_runtime_directory(self):
        with open(HELPER, "r", encoding="utf-8") as stream:
            source = stream.read()
        self.assertEqual(helper.DISK_RTSLIB_LOCK,
                         "/run/moonlight-os/rtslib_backstore.lock")
        lock_at = source.index("rtslib_tcm.lock_file = DISK_RTSLIB_LOCK")
        storage_at = source.index("storage = BlockStorageObject(", lock_at)
        self.assertLess(lock_at, storage_at)

    def test_missing_snapshot_is_successful_cleanup(self):
        info = self.info()
        with mock.patch.object(helper, "disk_target_withdraw", return_value=True), \
             mock.patch.object(helper, "run", return_value=(
                 None, 'Failed to find logical volume "moonlight/session-snapshot"')):
            self.assertTrue(helper.disk_target_remove(info))


if __name__ == "__main__":
    unittest.main()
