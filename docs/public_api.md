# Public Calendar API (JSON)

本ドキュメントは、`jcal/api/public.py` に追加した「暦情報JSON API（関数/HTTP両対応）」の仕様メモです。

## 方針
- 日付帰属は **JST日付境界** を正とする（UTC基準に戻さない）。
- 旧暦・中気・閏月の参照一致を維持する。
- 表記ゆれは **正規化ルール** として固定する。

## 正規化ルール
- 旧暦の表示: `閏` + 2桁月 + `/` + 2桁日
  - 例: `閏05/01`, `05/07`
- 月ラベル: `閏` + 2桁月（or 非閏）
  - 例: `閏05`, `06`
- 月名:
  - 非閏: `一月, 二月, …, 十二月`
  - 閏月: `閏一月, 閏二月, …, 閏十二月`
- 六曜: `先勝/友引/先負/仏滅/大安/赤口` のみ

## Function API
```py
get_calendar_day(date: str|date, *, tz="Asia/Tokyo", ephemeris="de440s.bsp", day_basis="jst", lat: float|None=None, lon: float|None=None) -> dict
get_calendar_range(start: str|date, end: str|date, *, tz="Asia/Tokyo", ephemeris="de440s.bsp", day_basis="jst", lat: float|None=None, lon: float|None=None) -> dict
```
`lat/lon` は観測地点（任意）。省略時は東京駅付近（lat=35.681236, lon=139.767125）。

## Day JSON Schema (stable)
```json
{
  "meta": {
    "tz": "Asia/Tokyo",
    "day_basis": "jst",
    "ephemeris": "de440s.bsp"
  },
  "date": "2017-06-24",
  "lunisolar": {
    "year": 2017,
    "month": 5,
    "day": 1,
    "leap": true,
    "month_label": "閏05",
    "label": "閏05/01",
    "month_name": "閏五月"
  },
  "rokuyo": "大安",
  "sekki": {
    "primary": {
      "name": "夏至",
      "degree": 90,
      "at_jst": "2017-06-21T13:24:08+09:00",
      "date_jst": "2017-06-21"
    },
    "events": [
      {
        "name": "夏至",
        "degree": 90,
        "at_jst": "2017-06-21T13:24:08+09:00",
        "date_jst": "2017-06-21"
      }
    ]
  },
  "astronomy": {
    "moon_age": 0.123456,
    "phase_event": {"type": "new_moon", "at_jst": "...", "date_jst": "..."},
    "sunrise": "2017-06-24T04:26:12+09:00",
    "sunset": "2017-06-24T19:00:14+09:00"
  }
}
```
- `sekki` がない日は `null`。
- `phase_event` は当日にイベントがある場合のみ、`new_moon` を返す（拡張余地あり）。
  day / range の `days[]` で同一日なら同じ判定になる。
- `sunrise` / `sunset` は ISO8601（UTC offset付き）。
  高緯度で検出できない場合や収束しない場合は `null`。

## Range JSON Schema (stable)
```json
{
  "meta": {"tz": "Asia/Tokyo", "day_basis": "jst", "ephemeris": "de440s.bsp"},
  "range": {"start": "2017-06-01", "end": "2017-09-30"},
  "days": [ {"date": "...", "lunisolar": {...}, "rokuyo": "...", "sekki": null, "astronomy": {...}} ],
  "events": {
    "sekki": [ {"name": "夏至", "degree": 90, "at_jst": "...", "date_jst": "..."} ],
    "moon_phases": [ {"type": "new_moon", "at_jst": "...", "date_jst": "..."} ]
  }
}
```

## 参照データ突合（pytest）
- 参照ファイル: `mnt/data/高精度計算サイト_2016_2034.txt`
- 主要比較: 旧暦（年月日/閏）、六曜、節気(JST日付)

### 実行例
```bash
python tests/compare_sekki_greg_range.py --ref mnt/data/高精度計算サイト_2016_2034.txt --greg-start 2017/06/01 --greg-end 2017/09/30 --day-basis jst --ephemeris de440s.bsp --sample-policy end
pytest tests/test_public_api_calendar.py -q
```
