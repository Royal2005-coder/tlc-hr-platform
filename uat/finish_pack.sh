#!/bin/sh
# Đóng gói MỘT lượt UAT thành bộ bàn giao offline: video journey nối theo vai trò, deck proposal (font đã nhúng),
# gói bằng chứng, và bản sao vào ~/tlc-hr/deliverables.
# Dùng: ~/tlc-hr/tlc-hr-platform/uat/finish_pack.sh <RUN_ID>
set -eu
RUN=${1:?thieu RUN_ID}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/out/$RUN"
[ -d "$OUT" ] || { echo "khong co $OUT"; exit 1; }
THEME=${THEME:-$HOME/tlc-hr/proposal_assets/deck.html}
DIAG=${DIAG:-$HOME/tlc-hr/proposal_assets/assets/diagrams}
UNIT=${UNIT:-147}
INTEG=${INTEG:-69}
WORKFLOWS=$(ls ~/tlc-hr/tlc_hr/tlc_hr/customizing/workflows/*.yaml | wc -l)

# 1. một video liền mạch cho mỗi vai trò (cần có clip R1..R6 của lượt này)
if ls "$OUT"/videos/*_R[0-9]-*_*.mp4 >/dev/null 2>&1; then
  "$HERE/roles_stitch.sh" "$RUN"
else
  echo "bo qua noi video vai tro: khong co clip R1..R6 trong $OUT/videos"
fi

# 2. deck proposal, rồi nhúng font để mở được khi không có mạng
python3 "$HERE/proposal_html.py" "$OUT" --theme "$THEME" --diagrams "$DIAG" \
  --tests "unit=$UNIT,integration=$INTEG,workflows=$WORKFLOWS"
DECK=$(ls -t "$OUT"/TLC_HRM_Proposal_UAT_*.html | head -1)
python3 "$HERE/inline_fonts.py" "$DECK"

# 3. gói bằng chứng một tệp
python3 "$HERE/offline_html.py" "$OUT"

# 4. bản bàn giao
D=$HOME/tlc-hr/deliverables
mkdir -p "$D"
cp "$DECK" "$OUT/UAT_TLC_HRM_${RUN}_offline.html" "$OUT/UAT_TLC_HRM_${RUN}.xlsx" "$OUT/results.json" "$D"/
cp "$OUT/results.json" "$D/results_${RUN}.json"   # giu bang ket qua cua tung luot, khong de luot sau ghi de luot truoc
echo "== $D"
ls -la "$D" | awk 'NR>2 {print $5, $9}'
grep -c "fonts.googleapis\|fonts.gstatic" "$DECK" | sed 's/^/lien ket mang con lai trong deck: /'
