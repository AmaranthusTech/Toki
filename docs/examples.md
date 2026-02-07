# Examples (UTC)

This project treats astronomical computations as **UTC-based**.  
All datetime inputs must be **timezone-aware UTC** (`tzinfo=timezone.utc`).

## Note on daily sampling (Phase 1)

Some APIs (e.g. daily lunar date series) sample at **00:00 UTC** for each day.  
If a new moon occurs during the day (e.g. at 12:01 UTC), the “day=1” transition  
will appear on the **next UTC date** in the daily series. This is expected behavior.

---

## New moons (UTC)

```python
from datetime import datetime, timezone

from jcal.core.astronomy import AstronomyEngine
from jcal.core.providers.skyfield_provider import SkyfieldProvider
from jcal.core.config import NewMoonConfig
from jcal.core.newmoon import new_moons_between

# SkyfieldProvider requires an ephemeris file (e.g. data/de421.bsp)
p = SkyfieldProvider()
eng = AstronomyEngine(provider=p)

cfg = NewMoonConfig(scan_step_hours=3)

start_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
end_utc   = datetime(2026, 3, 1, tzinfo=timezone.utc)

moons = new_moons_between(eng, start_utc, end_utc, config=cfg)
for t in moons:
    print(t.isoformat())
```

---

## Solar longitude crossing (UTC)

```python
from datetime import datetime, timezone

from jcal.core.astronomy import AstronomyEngine
from jcal.core.providers.skyfield_provider import SkyfieldProvider
from jcal.core.config import SolarTermConfig
from jcal.core.solarterms import solar_longitude_crossings

p = SkyfieldProvider()
eng = AstronomyEngine(provider=p)

cfg = SolarTermConfig(scan_step_hours=3)

start_utc = datetime(2025, 12, 1, tzinfo=timezone.utc)
end_utc   = datetime(2026, 2, 1, tzinfo=timezone.utc)

# Example: 270° (winter solstice longitude)
ts = solar_longitude_crossings(
    eng,
    start_utc,
    end_utc,
    target_deg=270.0,
    config=cfg,
)
for t in ts:
    print(t.isoformat())
```

---

## Daily lunar day series (UTC midnight sampling)

```python
from datetime import datetime, timezone

from jcal.core.astronomy import AstronomyEngine
from jcal.core.providers.skyfield_provider import SkyfieldProvider
from jcal.core.config import NewMoonConfig
from jcal.core.luni_solar import lunar_days_between

p = SkyfieldProvider()
eng = AstronomyEngine(provider=p)

cfg = NewMoonConfig(scan_step_hours=3)

start_utc = datetime(2026, 2, 10, tzinfo=timezone.utc)
end_utc   = datetime(2026, 2, 25, tzinfo=timezone.utc)

xs = lunar_days_between(eng, start_utc, end_utc, config=cfg)
for x in xs:
    print(x.date_utc.date(), x.lunar.day, x.lunar.span.new_moon_utc.isoformat())
```
