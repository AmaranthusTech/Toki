# RUNBOOK.md — Toki 運用手順書（API / Cache / Precompute / Export）

## ShinToki Release（GitHub Assets配布）

### Asset命名規約
- `shintoki_{version}_{tz}_{window_mode}_{start}_{end}.sqlite3`
- `shintoki_{version}_{tz}_{window_mode}_{start}_{end}.jsonl.gz`（非圧縮は `.jsonl`）
- `SHA256SUMS.txt`

例:
- `shintoki_v0.2.0_Asia-Tokyo_solstice-to-solstice_2000-01-01_2050-12-31.sqlite3`
- `shintoki_v0.2.0_Asia-Tokyo_solstice-to-solstice_2000-01-01_2050-12-31.jsonl.gz`

### 1. データ生成（SQLite/JSONL）
```bash
python -m shintoki export-sqlite \
  --start 2017-01-01 --end 2017-12-31 \
  --tz Asia/Tokyo \
  --out tmp/shintoki_2017.sqlite3

python -m shintoki export-jsonl \
  --start 2017-01-01 --end 2017-12-31 \
  --tz Asia/Tokyo \
  --out tmp/shintoki_2017.jsonl

# preset（任意）
python -m shintoki export-sqlite \
  --preset lite-2000-2050 \
  --tz Asia/Tokyo \
  --out tmp/shintoki_lite.sqlite3
```

### 2. 検証
```bash
python -m shintoki validate-sqlite \
  --sqlite tmp/shintoki_2017.sqlite3 \
  --samples 20 \
  --tz Asia/Tokyo \
  --format json | jq
```

### 3. ハッシュ作成
```bash
shasum -a 256 tmp/shintoki_2017.sqlite3 > tmp/shintoki_2017.sqlite3.sha256
shasum -a 256 tmp/shintoki_2017.jsonl   > tmp/shintoki_2017.jsonl.sha256
```

### 4. Release作成
- タグを `vX.Y.Z` で作成（例: `v0.2.0`）
- `CHANGELOG.md` の当該版を本文に反映
- assets として `sqlite3/jsonl/sha256` を添付
- `de440s.bsp` は同梱しない（利用者が別途取得）

### bloom運用モード（推奨）
- 推奨: SQLite参照を優先（配布DBを読み取り専用で利用）
- optional: miss時のみ計算して埋めるハイブリッド運用
  - ヒット時はDB返却で高速化
  - ミス時は計算結果を返し、非同期/後続でDBへ補完

### bloom 参照API起動（A=404方針）
```bash
python -m shintoki api-db serve \
  --sqlite-path data/cache/shintoki.sqlite3 \
  --host 127.0.0.1 \
  --port 8011
```

DBパス解決順:
1. `--sqlite-path`
2. `SHINTOKI_DB_PATH`
3. `./data/cache/shintoki.sqlite3`

- `/api/v1/day` は欠損時に `404 + missing[]` を返す
- `/api/v1/range?strict=1` は1件でも欠損があれば `404 + missing[]`
- 裏埋めは `export-sqlite` の precompute 運用で実施（HTTP admin は TODO）

### bloom フロント配備（静的HTML）
- フロント資産: [web/index.html](/Users/approximate/project/ShinToki/web/index.html)
- 配備先例: `/opt/homebrew/var/www/bloom/Toki/index.html`
- APIベースURL: `window.location.origin + "/Toki/api"`（同一origin想定）

配備例:
```bash
install -m 0644 web/index.html /opt/homebrew/var/www/bloom/Toki/index.html
# or
rsync -av web/index.html bloom-host:/opt/homebrew/var/www/bloom/Toki/index.html
```

Nginx 前提:
- `/Toki/index.html` を静的配信
- `/Toki/api/` を `http://127.0.0.1:8010/` へ proxy

確認コマンド（zsh 注意: URL は必ずシングルクォート）:
```bash
curl -s 'https://bloom.amaranthus.tech/Toki/api/v1/day?date=2026-03-05&tz=Asia/Tokyo' | jq
curl -s 'https://bloom.amaranthus.tech/Toki/api/v1/range?start=2026-03-05&end=2026-03-15&tz=Asia/Tokyo&strict=0' | jq
```

## 0. 前提
- 配置ディレクトリ（例）: `/opt/homebrew/var/www/bloom/_apps/Toki_Private_`
- ポート: `8010`（固定）
- LaunchAgent label: `com.amaranthus.toki-demo`（固定）
- Python venv: repo直下の `.venv`
- Ephemeris（推奨）: `data/de440s.bsp`（代替: `data/de421.bsp`）

---

## 1. よく使うコマンド（最短）

### サービス再起動（launchctl）
```bash
launchctl kickstart -k gui/$(id -u)/com.amaranthus.toki-demo
```

### ヘルス確認
```bash
curl -s http://127.0.0.1:8010/health | jq
```

### API疎通（例：range）
```bash
curl -sG "http://127.0.0.1:8010/range" \
  --data-urlencode "start=2026-02-01" \
  --data-urlencode "end=2026-03-31" \
  --data-urlencode "items=lunisolar" \
  --data-urlencode "items=rokuyo" \
  --data-urlencode "items=sekki" \
  --data-urlencode "tz=Asia/Tokyo" \
| jq
```

---

## 2. セットアップ（初回だけ）

### 2.1 リポジトリ取得
```bash
cd /opt/homebrew/var/www/bloom/_apps
git clone https://github.com/AmaranthusTech/Toki.git Toki_Private_
cd Toki_Private_
```

### 2.2 venv作成 & 依存導入
```bash
cd /opt/homebrew/var/www/bloom/_apps/Toki_Private_
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel
pip install -e .
```

### 2.3 Ephemeris配置
```bash
cd /opt/homebrew/var/www/bloom/_apps/Toki_Private_
mkdir -p data
cp /path/to/de440s.bsp data/de440s.bsp
# または de421.bsp でも可
ls -lah data/*.bsp
```

---

## 3. 起動（開発 / 手動）

### 3.1 手動起動（foreground）
```bash
cd /opt/homebrew/var/www/bloom/_apps/Toki_Private_
source .venv/bin/activate
uvicorn jcal.api.app:app --app-dir src --host 127.0.0.1 --port 8010 --log-level info
```

### 3.2 /openapi で確認
```bash
curl -s http://127.0.0.1:8010/openapi.json | jq '.info, (.paths | keys)'
```

---

## 4. LaunchAgent（常駐運用）

### 4.1 登録（bootstrap）
```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.amaranthus.toki-demo.plist
```

### 4.2 停止（bootout）
```bash
launchctl bootout gui/$(id -u)/com.amaranthus.toki-demo 2>/dev/null || true
```

### 4.3 再起動（kickstart）
```bash
launchctl kickstart -k gui/$(id -u)/com.amaranthus.toki-demo
```

### 4.4 状態確認
```bash
launchctl print gui/$(id -u) | rg -n "com\.amaranthus\.toki-demo|toki" -n
lsof -i :8010 -nP
```

---

## 5. キャッシュ（SQLite）運用

### 5.1 DB全消し（まっさらに）
```bash
rm -f /opt/homebrew/var/www/bloom/_apps/Toki_Private_/data/cache/toki_cache.sqlite3*
launchctl kickstart -k gui/$(id -u)/com.amaranthus.toki-demo
```

### 5.2 テーブル確認
```bash
sqlite3 /opt/homebrew/var/www/bloom/_apps/Toki_Private_/data/cache/toki_cache.sqlite3 ".tables"
sqlite3 /opt/homebrew/var/www/bloom/_apps/Toki_Private_/data/cache/toki_cache.sqlite3 \
  "select count(*) from day_cache; select count(*) from day_cache_failures;"
```

---

## 6. Precompute（事前生成）

### 6.1 まずは短い期間で温める（推奨）
```bash
cd /opt/homebrew/var/www/bloom/_apps/Toki_Private_
source .venv/bin/activate

python -m demo_api.toki_cache precompute \
  --start 2026-02-01 --end 2026-03-31 \
  --items lunisolar --items rokuyo --items sekki \
  --tz Asia/Tokyo \
  --chunk-days 30 \
  --continue-on-error
```

### 6.2 全期間（時間かかる）
```bash
python -m demo_api.toki_cache precompute \
  --start 1900-01-01 --end 2100-12-31 \
  --items lunisolar --items rokuyo --items sekki \
  --tz Asia/Tokyo \
  --chunk-days 30 \
  --continue-on-error
```

---

## 7. Export（配布物生成）

### 7.1 JSONL（1行=1日）を書き出す
```bash
python -m demo_api.toki_cache export-json \
  --start 2026-01-01 --end 2026-12-31 \
  --items lunisolar --items rokuyo --items sekki \
  --tz Asia/Tokyo \
  --output /tmp/toki_2026.jsonl
```

### 7.2 SQLite を配布用にコピー（必要ならVACUUM）
```bash
python -m demo_api.toki_cache export-sqlite \
  --output /tmp/toki_cache.sqlite3 \
  --vacuum
```

---

## 8. デバッグ（2033などの旧暦例外）

### 8.1 debug env
```bash
export JCAL_DEBUG_LUNISOLAR=1
export JCAL_DEBUG_FROM=2033-06-01
export JCAL_DEBUG_TO=2033-07-01
```

### 8.2 単発再現
```bash
PYTHONPATH=src python - <<'PY'
from datetime import date
from jcal.core.lunisolar import gregorian_to_lunar
print(gregorian_to_lunar(date(2033,6,10)))
PY
```
