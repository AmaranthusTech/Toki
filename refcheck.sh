set -euo pipefail

ts="$(date +%Y%m%d-%H%M%S)"
log="rokuyo_verify_${ts}.log"

for y in {2016..2027}; do
  echo "===== $y =====" | tee -a "$log"
  python tests/check_rokuyo_ref.py "refer/rokuyo/${y}.dat" --basis 23:59:59 --progress | tee -a "$log"
done

echo "ALL OK (2016..2027)" | tee -a "$log"

