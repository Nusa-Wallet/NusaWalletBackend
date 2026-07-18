import unittest
from datetime import datetime, timedelta, timezone

from app.core.datetime import utc_isoformat


class UtcIsoformatTest(unittest.TestCase):
    def test_treats_sqlite_naive_datetime_as_utc(self):
        value = datetime(2026, 7, 18, 7, 30, 0)

        self.assertEqual(utc_isoformat(value), "2026-07-18T07:30:00Z")

    def test_converts_aware_datetime_to_utc(self):
        jakarta = timezone(timedelta(hours=7))
        value = datetime(2026, 7, 18, 14, 30, 0, tzinfo=jakarta)

        self.assertEqual(utc_isoformat(value), "2026-07-18T07:30:00Z")


if __name__ == "__main__":
    unittest.main()
