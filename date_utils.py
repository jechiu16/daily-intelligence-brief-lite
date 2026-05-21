import datetime as dt
from zoneinfo import ZoneInfo


try:
    TAIPEI_TZ = ZoneInfo("Asia/Taipei")
except Exception:
    TAIPEI_TZ = dt.timezone(dt.timedelta(hours=8), name="Asia/Taipei")


def taipei_today() -> dt.date:
    return dt.datetime.now(TAIPEI_TZ).date()
