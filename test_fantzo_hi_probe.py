"""The authorized reachability probe must never send twice."""

import asyncio
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot as core
import fantzo_hi_probe as probe


class FantzoHiProbeTests(unittest.TestCase):
    def test_success_is_claimed_before_send_and_never_repeated(self):
        conn = sqlite3.connect(":memory:")
        bot = SimpleNamespace(
            send_message=AsyncMock(
                return_value=SimpleNamespace(
                    chat=SimpleNamespace(id=probe.TARGET_USER_ID),
                    message_id=77,
                )
            )
        )
        try:
            with patch.object(core, "db", return_value=conn):
                self.assertEqual(asyncio.run(probe.send_once(bot)), "sent")
                self.assertEqual(asyncio.run(probe.send_once(bot)), "already_claimed")
                self.assertEqual(
                    conn.execute(
                        "SELECT user_id FROM fantzo_one_time_outbound_probes "
                        "WHERE probe_key=?",
                        (probe.PROBE_KEY,),
                    ).fetchone()[0],
                    probe.TARGET_USER_ID,
                )
            bot.send_message.assert_awaited_once_with(
                chat_id=probe.TARGET_USER_ID,
                text="hi",
            )
        finally:
            conn.close()

    def test_failed_send_is_not_retried_after_restart(self):
        conn = sqlite3.connect(":memory:")
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("unavailable")))
        try:
            with patch.object(core, "db", return_value=conn):
                self.assertEqual(asyncio.run(probe.send_once(bot)), "failed")
                self.assertEqual(asyncio.run(probe.send_once(bot)), "already_claimed")
            self.assertEqual(bot.send_message.await_count, 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
