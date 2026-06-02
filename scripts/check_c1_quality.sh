#!/usr/bin/env bash
# Per-stock C1 quality summary: schema_drift + excerpt_mis_cite counts from
# verify_overlay_closed_loop, scoped to a given stock list (default: all
# AI_COMPUTE A-shares). Copies overlays to a temp dir so an in-flight codex
# edit on an excluded stock can't corrupt the scan.
#
# Usage:
#   scripts/check_c1_quality.sh                       # all A-shares
#   scripts/check_c1_quality.sh 000063.SZ 002463.SZ   # subset
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
SRC="config/stock_overlays/AI_COMPUTE"
TMP="$(mktemp -d)"
mkdir -p "$TMP/AI_COMPUTE" /tmp/nonexistent_ind

if [ $# -gt 0 ]; then
  STOCKS=("$@")
else
  STOCKS=()
  for f in "$SRC"/*.yaml; do
    b=$(basename "$f" .yaml)
    echo "$b" | grep -qE "\.(SH|SZ|BJ)$" && STOCKS+=("$b")
  done
fi

for ts in "${STOCKS[@]}"; do
  cp "$SRC/${ts}.yaml" "$TMP/AI_COMPUTE/" 2>/dev/null || echo "  (missing $ts)"
done

OUT=$($PY scripts/verify_overlay_closed_loop.py \
      --stock-overlays-dir "$TMP" --industry-overlays-dir /tmp/nonexistent_ind \
      --check-schema --check-excerpt 2>/dev/null)

printf "%-12s %12s %14s\n" "stock" "schema_drift" "excerpt_miscite"
for ts in "${STOCKS[@]}"; do
  sd=$(printf '%s\n' "$OUT" | grep "/${ts}.yaml" | grep -c "schema_drift")
  ex=$(printf '%s\n' "$OUT" | grep "/${ts}.yaml" | grep -c "excerpt_mis_cite")
  printf "%-12s %12s %14s\n" "$ts" "$sd" "$ex"
done
echo "---"
printf '%s\n' "$OUT" | grep -E "hard violations|soft violations|schema-violating nodes|excerpt mis-cite nodes"
rm -rf "$TMP"
