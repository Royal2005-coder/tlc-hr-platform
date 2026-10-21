#!/bin/sh
# Nối các clip một lượt UAT vai trò thành MỘT video liền mạch cho mỗi vai trò
# (một vai trò có thể cần nhiều tài khoản: HR = chuyên viên + trưởng phòng + tính lương).
# Dùng: ~/tlc-hr/tlc-hr-platform/uat/roles_stitch.sh <RUN_ID>   -> out/<RUN_ID>/videos/ROLE-<vai tro>.mp4
set -eu
RUN=${1:?thieu RUN_ID}
HERE=$(cd "$(dirname "$0")" && pwd)
V="$HERE/out/$RUN/videos"
[ -d "$V" ] || { echo "khong co $V"; exit 1; }

# tên video ra : các clip vào (theo thứ tự kể)
GROUPS="ROLE-CONG_NHAN:R1-CONGNHAN
ROLE-NHAN_VIEN_VP:R2-VANPHONG
ROLE-TRUONG_NHA_MAY:R3-TRUONGNM
ROLE-HR:R4-HR-OFFICER:R4-HR-LEAD:R4-HR-PAYROLL
ROLE-CEO:R5-CEO
ROLE-KE_TOAN_QUAN_LY:R6-MANAGER:R6-ACCOUNTANT"

LIST="$V/.roles-list"
: > "$LIST"
for spec in $GROUPS; do
  out=$(echo "$spec" | cut -d: -f1)
  clips=$(echo "$spec" | cut -d: -f2-)
  : > "$LIST"
  found=0
  # clip được đặt tên <NN>_<MA PHIEN>_<tai khoan>.mp4
  for code in $(echo "$clips" | tr ':' ' '); do
    for f in "$V"/*"_$code"_*.mp4; do
      [ -f "$f" ] || continue
      echo "file '$(basename "$f")'" >> "$LIST"
      found=$((found + 1))
      break
    done
  done
  [ "$found" -gt 0 ] || { echo "bo qua $out: khong tim clip cua $clips"; continue; }
  docker run --rm --user "$(id -u):$(id -g)" -v "$V:/v" --entrypoint sh jrottenberg/ffmpeg:6.1-ubuntu -c \
    "cd /v && ffmpeg -loglevel error -y -f concat -safe 0 -i .roles-list -c copy $out.mp4 && ffprobe -v error -show_entries format=duration -of csv=p=0 $out.mp4" \
    | sed "s|^|$out: |"
done
rm -f "$LIST"
echo "xong: $V"
