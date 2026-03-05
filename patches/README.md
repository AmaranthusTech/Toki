# jcal patch artifacts

- `jcal-lunisolar.patch`: fixed non-empty patch applied to `jcal/core/lunisolar.py` in site-packages.
- `jcal_lunisolar_clean.py`: clean baseline snapshot used to generate the fixed patch.
- `jcal_lunisolar_patched.py`: patched target snapshot.
- `scripts/apply_patches.sh` verifies marker `SHINTOKI_PATCH: JCAL_LUNISOLAR_V1` after apply and fails if missing.
- `scripts/apply_patches.sh` auto-selects Python (`PYTHON` override > `.venv/bin/python` > `python3`).

Regenerate fixed patch (preferred from upstream source):

```bash
python scripts/make_clean_jcal_snapshot.py --url https://github.com/AmaranthusTech/Toki.git --commit f4789b4b42492a191da88eeb410bc10268c6e52a
```

Offline fallback (explicit clean file path):

```bash
python scripts/make_clean_jcal_snapshot.py --from-file /path/to/clean/lunisolar.py
```
