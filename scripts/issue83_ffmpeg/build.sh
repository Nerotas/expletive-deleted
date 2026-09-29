#!/usr/bin/env bash
set -euo pipefail

# Phase 1A prototype only: these inputs and outputs are not approved release artifacts.
input_root=/inputs
output_root=/output
# Each isolated container gets the same prefix so -buildconf cannot vary by run.
work_root=/tmp/issue83-ffmpeg-build
mkdir -m 0700 "$work_root"
install_root="$work_root/install"
toolchain=x86_64-w64-mingw32
jobs=${ISSUE83_JOBS:-4}
export SOURCE_DATE_EPOCH=0 LC_ALL=C TZ=UTC

on_failure() {
  local status=$?
  if [[ -f "$work_root/ffmpeg-8.1.2/ffbuild/config.log" ]]; then
    cp "$work_root/ffmpeg-8.1.2/ffbuild/config.log" "$output_root/ffmpeg-config-failed.log"
  fi
  exit "$status"
}
trap on_failure ERR

[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'ISSUE83_JOBS must be a positive integer' >&2; exit 2; }

test -d "$input_root" && test -d "$output_root"

# Fail closed if Debian updates any build package under the digest-pinned base.
dpkg-query -W -f='${Package} ${Version}\n' > "$output_root/build-packages.txt"
printf '%s  %s\n' \
  '8cfef7bd587924f96537353a5a69e6bb7dc209c7c4d446a0856c016d58ba2545' "$output_root/build-packages.txt" \
  | sha256sum --check --status
/bin/bash /opt/issue83/record-apt-inputs.sh \
  "$output_root/build-packages.txt" "$output_root/build-package-archives.txt"
printf '%s  %s\n' \
  'cfb9aca689fe62fe970bb835a14b0ad85a53cf0d40704ea48ca2cd80661efb22' "$output_root/build-package-archives.txt" \
  | sha256sum --check --status

printf '%s  %s\n' \
  '464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c' "$input_root/ffmpeg-8.1.2.tar.xz" \
  '6eeb82934e69fd51e043bd8c5b0d152839638d1ce7aa4eea65a3fedcf83ff224' "$input_root/x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55.tar.bz2" \
  'ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e' "$input_root/lame-3.100.tar.gz" \
  | sha256sum --check --status

tar -xC "$work_root" -f "$input_root/x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55.tar.bz2"
tar -xC "$work_root" -f "$input_root/lame-3.100.tar.gz"
tar -xC "$work_root" -f "$input_root/ffmpeg-8.1.2.tar.xz"

cd "$work_root/x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55"
./configure \
  --host="$toolchain" \
  --cross-prefix="$toolchain-" \
  --prefix="$install_root" \
  --enable-static \
  --disable-cli \
  --disable-opencl
make -s -j"$jobs"
make install

cd "$work_root/lame-3.100"
./configure \
  --host="$toolchain" \
  --prefix="$install_root" \
  --enable-static \
  --disable-shared \
  --disable-frontend \
  --disable-decoder
make -s -j"$jobs"
make install

cd "$work_root/ffmpeg-8.1.2"
export PKG_CONFIG_LIBDIR="$install_root/lib/pkgconfig"
export PKG_CONFIG_ALLOW_CROSS=1
./configure \
  --prefix="$install_root" \
  --target-os=mingw32 \
  --arch=x86_64 \
  --enable-cross-compile \
  --cross-prefix="$toolchain-" \
  --pkg-config=pkg-config \
  --pkg-config-flags=--static \
  --extra-cflags="-I$install_root/include" \
  --extra-ldflags="-L$install_root/lib" \
  --extra-ldexeflags='-static' \
  --enable-gpl \
  --enable-version3 \
  --enable-libx264 \
  --enable-libmp3lame \
  --enable-static \
  --disable-shared \
  --disable-autodetect \
  --disable-doc \
  --disable-ffplay \
  --disable-debug
make -s -j"$jobs" ffmpeg.exe ffprobe.exe

install -m 0644 config.h "$output_root/config.h"
install -m 0644 ffbuild/config.mak "$output_root/config.mak"
install -m 0755 ffmpeg.exe "$output_root/ffmpeg.exe"
install -m 0755 ffprobe.exe "$output_root/ffprobe.exe"

# Preserve the exact source/build input hashes and toolchain package versions.
sha256sum \
  "$input_root/ffmpeg-8.1.2.tar.xz" \
  "$input_root/x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55.tar.bz2" \
  "$input_root/lame-3.100.tar.gz" \
  "$output_root/build-packages.txt" \
  "$output_root/build-package-archives.txt" \
  "$output_root/ffmpeg.exe" \
  "$output_root/ffprobe.exe" > "$output_root/checksums.sha256"
