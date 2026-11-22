#!/usr/bin/env bash
# 사용법: bash sync.sh [--check] [저장소 ...]
set -uo pipefail

src="${BRIEF_COMMON_SRC:-/workspace/brief-common/common}"
check=0
if [ "${1:-}" = --check ]; then
  check=1
  shift
fi
if [ "$#" -eq 0 ]; then
  set -- kg-tj-brief hu-eu-brief eu-trade-brief
fi
if [ ! -d "$src" ]; then
  echo "공통 모듈 정본 폴더가 없음: $src" >&2
  exit 1
fi

status=0
shopt -s dotglob nullglob
for repo in "$@"; do
  case "$repo" in
    -*) echo "알 수 없는 옵션: $repo" >&2; status=1; continue ;;
    .|..|/*|*/*) path="$repo" ;;
    *) path="/workspace/$repo" ;;
  esac
  if ! target=$(realpath -e -- "$path") || [ ! -d "$target/tools" ]; then
    echo "저장소의 tools 폴더가 없음: $repo" >&2
    status=1
    continue
  fi
  if [ "${target##*/}" = trade-brief ]; then
    echo "공통 모듈 적용 대상이 아님: $repo" >&2
    status=1
    continue
  fi
  dest="$target/tools/common"
  if [ "$check" -eq 1 ]; then
    diff -r -x __pycache__ -- "$src" "$dest" || status=1
  elif mkdir -p -- "$dest"; then
    for file in "$src"/*; do
      [ "${file##*/}" = __pycache__ ] && continue
      cp -a -- "$file" "$dest/" || status=1
    done
  else
    status=1
  fi
done
exit "$status"
