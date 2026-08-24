#!/usr/bin/env python3
"""Tests for the privileged Stable/Beta settings boundary."""

import importlib.machinery
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "config/includes.chroot/usr/local/bin/moonlight-helper")
LIB = os.path.join(ROOT, "config/includes.chroot/usr/local/lib/moonlight-os")
sys.path.insert(0, LIB)

loader = importlib.machinery.SourceFileLoader("moonlight_helper_update_channel", HELPER)
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class UpdateChannelSettingsTest(unittest.TestCase):
    def test_stable_is_the_fail_closed_default(self):
        values = dict(helper.SETTING_DEFAULTS)
        self.assertEqual(helper.conf_public(values)["update_channel"], "stable")
        values["UPDATE_CHANNEL"] = "unexpected"
        self.assertEqual(helper.conf_public(values)["update_channel"], "stable")

    def test_beta_is_persisted_by_the_named_setting(self):
        self.assertEqual(
            helper.setting_updates({"values": {"update_channel": "beta"}}),
            {"UPDATE_CHANNEL": "beta"},
        )

    def test_unknown_channel_is_rejected(self):
        with self.assertRaisesRegex(helper.Error, "stable or beta"):
            helper.setting_updates({"values": {"update_channel": "nightly"}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
