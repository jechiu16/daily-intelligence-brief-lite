import os

import httpx


class PreflightError(RuntimeError):
    pass


REQUIRED_DAILY_ENV = (
    "GOOGLE_API_KEY",
    "FRED_API_KEY",
    "NOTION_TOKEN",
    "NOTION_DATABASE_ID",
)


def _missing_required_env(env: dict[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    return [name for name in REQUIRED_DAILY_ENV if not source.get(name)]


def validate_fred_key(api_key: str, timeout: int = 10) -> None:
    try:
        resp = httpx.get(
            "https://api.stlouisfed.org/fred/series",
            params={
                "series_id": "DFF",
                "api_key": api_key,
                "file_type": "json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
    except Exception:
        raise PreflightError(
            "FRED_API_KEY validation failed. Check that the key is present, active, "
            "and allowed to call the FRED API."
        ) from None


def run_preflight(env: dict[str, str] | None = None) -> None:
    source = os.environ if env is None else env
    missing = _missing_required_env(source)
    if missing:
        names = ", ".join(missing)
        raise PreflightError(f"Missing required environment variables: {names}")

    validate_fred_key(source["FRED_API_KEY"])


def main() -> None:
    run_preflight()
    print("Preflight OK")


if __name__ == "__main__":
    main()
