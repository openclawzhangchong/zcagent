#!/usr/bin/env bash
# Download python-build-standalone into desktop/portable/runtimes/<plat>
# and the matching Node.js distribution into runtimes/<plat>-node.
#
# Usage:
#   bash desktop/portable/bootstrap-runtime.sh              # host platform
#   bash desktop/portable/bootstrap-runtime.sh darwin-arm64
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=desktop/portable/_common.sh
source "${REPO_ROOT}/desktop/portable/_common.sh"

download() {
  local url="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [[ -f "$dest" && -s "$dest" ]]; then
    echo "[bootstrap] cache hit ${dest}" >&2
    return 0
  fi
  echo "[bootstrap] downloading ${url}" >&2
  curl -fL --retry 3 --retry-delay 2 -o "${dest}.partial" "$url"
  mv "${dest}.partial" "$dest"
}

flatten_pbs_install() {
  local extract_dir="$1"
  local dest="$2"
  rm -rf "$dest"
  mkdir -p "$(dirname "$dest")"
  if [[ -d "${extract_dir}/python" ]]; then
    mv "${extract_dir}/python" "$dest"
  elif [[ -d "${extract_dir}/install" ]]; then
    mv "${extract_dir}/install" "$dest"
  else
    echo "[bootstrap] unexpected PBS layout under ${extract_dir}" >&2
    find "$extract_dir" -maxdepth 2 -print >&2 || true
    exit 1
  fi
}

bootstrap_one() {
  local plat="$1"
  local triple archive url cache dest
  triple="$(plat_triple "$plat")" || {
    echo "unknown platform: $plat" >&2
    exit 1
  }
  archive="$(pbs_archive_name "$plat")"
  url="${PBS_BASE_URL}/${archive}"
  cache="${GREEN_CACHE}/${archive}"
  dest="${GREEN_RUNTIMES}/${plat}"

  mkdir -p "$GREEN_RUNTIMES" "$GREEN_CACHE"
  if [[ -x "$(runtime_python "$dest")" || -f "${dest}/python.exe" ]]; then
    echo "[bootstrap] ${plat}: runtime already present → ${dest}" >&2
    return 0
  fi

  download "$url" "$cache"
  local tmp
  tmp="$(mktemp -d "${GREEN_CACHE}/extract.XXXXXX")"
  tar -xzf "$cache" -C "$tmp"
  flatten_pbs_install "$tmp" "$dest"
  rm -rf "$tmp"

  local py
  py="$(runtime_python "$dest")"
  if [[ ! -x "$py" && ! -f "$py" ]]; then
    echo "[bootstrap] python missing after extract: ${py}" >&2
    exit 1
  fi
  echo "[bootstrap] ${plat}: ${py}" >&2
  "$py" -c "import sys; print(sys.version)" >&2 || true
}

bootstrap_node() {
  local plat="$1"
  local archive url cache dest top slug
  slug="$(node_slug "$plat")" || {
    echo "unknown platform: $plat" >&2
    exit 1
  }
  archive="$(node_archive_name "$plat")"
  url="${NODE_BASE_URL}/${archive}"
  cache="${GREEN_CACHE}/${archive}"
  dest="$(node_runtime_dir "$plat")"
  top="$(node_top_dir "$plat")"

  mkdir -p "$GREEN_RUNTIMES" "$GREEN_CACHE"
  if [[ -f "${dest}/node.exe" || -x "${dest}/bin/node" ]]; then
    echo "[bootstrap] ${plat}: node already present → ${dest}" >&2
    return 0
  fi

  download "$url" "$cache"
  local tmp
  tmp="$(mktemp -d "${GREEN_CACHE}/extract-node.XXXXXX")"
  case "$archive" in
    *.zip)
      if command -v unzip >/dev/null 2>&1; then
        unzip -q "$cache" -d "$tmp"
      elif command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -NoProfile -Command \
          "Expand-Archive -LiteralPath '${cache//\'/\'\'}' -DestinationPath '$tmp'" >/dev/null
      else
        echo "[bootstrap] need unzip (or PowerShell) for ${archive}" >&2
        exit 1
      fi
      ;;
    *.tar.xz) tar -xJf "$cache" -C "$tmp" ;;
    *) tar -xzf "$cache" -C "$tmp" ;;
  esac
  if [[ ! -d "${tmp}/${top}" ]]; then
    echo "[bootstrap] unexpected node layout under ${tmp}" >&2
    find "$tmp" -maxdepth 2 -print >&2 || true
    exit 1
  fi
  rm -rf "$dest"
  mkdir -p "$(dirname "$dest")"
  mv "${tmp}/${top}" "$dest"
  rm -rf "$tmp"

  local node_dir node_exe
  node_dir="$(node_bin_dir "$dest")"
  node_exe="${node_dir}/node"
  [[ -f "${node_dir}/node.exe" ]] && node_exe="${node_dir}/node.exe"
  if [[ ! -f "$node_exe" ]]; then
    echo "[bootstrap] node missing after extract: ${node_exe}" >&2
    exit 1
  fi
  # npm ships as node_modules/npm plus an npm.cmd shim next to node.exe; the shim is
  # what the connector installer invokes, so check the payload behind it, not the shim.
  if [[ ! -d "${dest}/node_modules/npm" ]]; then
    echo "[bootstrap] bundled npm payload missing under ${dest}/node_modules/npm" >&2
    exit 1
  fi
  echo "[bootstrap] ${plat}: $("$node_exe" -v 2>/dev/null || echo "$node_exe") → ${node_dir}" >&2
}

main() {
  local plat="${1:-}"
  if [[ -z "$plat" ]]; then
    plat="$(host_plat)"
  fi
  if ! is_known_plat "$plat"; then
    echo "unknown platform: $plat (known: ${ALL_PLATS[*]})" >&2
    exit 1
  fi
  bootstrap_one "$plat"
  bootstrap_node "$plat"
}

main "${1:-}"
