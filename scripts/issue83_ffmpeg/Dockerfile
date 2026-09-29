FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

# Keep binary/source indexes at one immutable date. APT verifies signed Release
# metadata and package hashes even when the local Docker TLS chain is unavailable.
RUN printf '%s\n' \
    'Types: deb deb-src' \
    'URIs: http://snapshot.debian.org/archive/debian/20260928T000000Z/' \
    'Suites: bookworm bookworm-updates' \
    'Components: main' \
    'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
    'Check-Valid-Until: no' \
    '' \
    'Types: deb deb-src' \
    'URIs: http://snapshot.debian.org/archive/debian-security/20260928T000000Z/' \
    'Suites: bookworm-security' \
    'Components: main' \
    'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
    'Check-Valid-Until: no' \
    > /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    binutils-mingw-w64-x86-64 \
    bzip2 \
    gcc \
    gcc-mingw-w64-x86-64 \
    g++-mingw-w64-x86-64 \
    libc6-dev \
    make \
    nasm \
    pkg-config \
    tar \
    xz-utils

COPY build.sh /opt/issue83/build.sh
COPY record-apt-inputs.sh /opt/issue83/record-apt-inputs.sh
ENTRYPOINT ["/bin/bash", "/opt/issue83/build.sh"]
