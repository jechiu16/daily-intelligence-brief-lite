"""
main.py — 入口點
支援手動觸發和自動排程。
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Daily Intelligence Brief v9-lite"
    )
    parser.add_argument(
        "command",
        choices=["daily", "weekly", "test-data", "test-regime"],
        help="daily=每日報告, weekly=週報, test-data=測試資料收集, test-regime=測試 regime 分類",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="手動指定日期 (YYYY-MM-DD)，預設為今天",
    )

    args = parser.parse_args()

    if args.command == "daily":
        from pipeline import run_daily_pipeline
        report = run_daily_pipeline(manual_date=args.date)
        print("\n" + "=" * 60)
        print("FINAL REPORT")
        print("=" * 60)
        print(report)

    elif args.command == "weekly":
        from pipeline import run_weekly_report
        report = run_weekly_report()
        print("\n" + "=" * 60)
        print("WEEKLY REPORT")
        print("=" * 60)
        print(report)

    elif args.command == "test-data":
        from data_layer import collect_all_data
        import json
        data = collect_all_data()
        # 移除不可序列化的項目
        clean = {k: v for k, v in data.items()
                 if isinstance(v, (str, int, float, bool, list, type(None)))}
        print(json.dumps(clean, indent=2, ensure_ascii=False))

    elif args.command == "test-regime":
        from data_layer import collect_all_data
        from hard_truths import build_hard_truths, format_level_a, format_level_b
        from relational_guardrail import run_relational_guardrail

        data = collect_all_data()
        ht = build_hard_truths(data)
        print(format_level_a(ht))
        print()
        lb = format_level_b(ht)
        if lb:
            print(lb)
        print()

        flags = run_relational_guardrail(ht)
        if flags:
            print("⚡ Relational Flags:")
            for f in flags:
                print(f"  {f}")


if __name__ == "__main__":
    main()
