import datetime as real_datetime
import unittest
from unittest.mock import patch

import date_utils


class DateUtilsTest(unittest.TestCase):
    def test_taipei_today_uses_taipei_timezone(self):
        class FixedDateTime(real_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 5, 21, 0, 30, tzinfo=tz)

        with patch.object(date_utils.dt, "datetime", FixedDateTime):
            self.assertEqual(date_utils.taipei_today(), real_datetime.date(2026, 5, 21))


if __name__ == "__main__":
    unittest.main()

