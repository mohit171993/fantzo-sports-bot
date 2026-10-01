"""@Liveline_proadmin (8860632140) has full admin rights alongside ADMIN_USER_ID."""

import unittest

import bot as core

PROADMIN = 8860632140


class ExtraAdminTests(unittest.TestCase):
    def test_proadmin_and_main_admin_are_admins(self):
        self.assertIn(PROADMIN, core.EXTRA_ADMIN_USER_IDS)
        self.assertTrue(core.is_admin_user(PROADMIN))
        self.assertTrue(core.is_admin_user(str(PROADMIN)))
        self.assertTrue(core.is_admin_user(core.ADMIN_USER_ID))
        self.assertFalse(core.is_admin_user(5))
        self.assertFalse(core.is_admin_user(None))

    def test_report_center_and_mode_accept_proadmin(self):
        import ibetin_reports
        self.assertTrue(ibetin_reports.is_authorized_admin(PROADMIN))
        import bot_mode_runtime
        self.assertTrue(bot_mode_runtime._is_mode_admin(PROADMIN))
        self.assertFalse(bot_mode_runtime._is_mode_admin(5))


if __name__ == "__main__":
    unittest.main()
