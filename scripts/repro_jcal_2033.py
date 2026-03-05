from __future__ import annotations

from datetime import date
import traceback


def main() -> int:
    try:
        from jcal.core.lunisolar import gregorian_to_lunar
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1

    target = date(2033, 6, 10)
    print(f"target_date={target.isoformat()}")
    try:
        result = gregorian_to_lunar(target)
        print(result)
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
