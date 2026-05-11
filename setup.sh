#!/usr/bin/env bash
# Prepare PepperBox for physical-robot use by ensuring the SoftBank Robotics
# pynaoqi SDK is available locally. The SDK is proprietary and never built into
# the image; it lives under $HOME/.pepperbox on the user's machine and is
# bind-mounted into the container at runtime.
#
# Sim-only users do not need this script; qibullet is already in the image.
#
# Idempotent: re-running after success is a no-op.

set -euo pipefail

readonly PYNAOQI_FILENAME="pynaoqi-python2.7-2.5.7.1-linux64.tar.gz"
readonly PYNAOQI_DIR_NAME="pynaoqi-python2.7-2.5.7.1-linux64"
readonly PYNAOQI_SHA256="d2060ad69f87481f0dda82ede6c70c3b65afa6f1bf06e2c107c2e373d26d92c2"
readonly PYNAOQI_SIZE=51743305
readonly PRIMARY_URL="https://community-static.aldebaran.com/resources/2.5.10/Python%20SDK/${PYNAOQI_FILENAME}"
readonly WAYBACK_URL="https://web.archive.org/web/20240301010123if_/${PRIMARY_URL}"

PEPPERBOX_HOME="${PEPPERBOX_HOME:-$HOME/.pepperbox}"
readonly TARBALL_PATH="${PEPPERBOX_HOME}/${PYNAOQI_FILENAME}"
readonly SDK_DIR="${PEPPERBOX_HOME}/${PYNAOQI_DIR_NAME}"
readonly NAOQI_PY_PATH="${SDK_DIR}/lib/python2.7/site-packages/naoqi.py"

require() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "[!!] required command not found: $1" >&2
        exit 1
    }
}
require curl
require sha256sum
require tar

mkdir -p "${PEPPERBOX_HOME}"

echo "PepperBox setup"
echo "==============="
echo "SDK home: ${PEPPERBOX_HOME}"
echo

if [[ -f "${NAOQI_PY_PATH}" ]]; then
    echo "[ok] pynaoqi already extracted at ${SDK_DIR}"
    echo "[ok] nothing to do"
    exit 0
fi

verify_sha() {
    local file="$1"
    local actual
    actual=$(sha256sum "${file}" | awk '{print $1}')
    [[ "${actual}" == "${PYNAOQI_SHA256}" ]]
}

if [[ -f "${TARBALL_PATH}" ]]; then
    echo "[..] found existing tarball at ${TARBALL_PATH}; verifying SHA256..."
    if verify_sha "${TARBALL_PATH}"; then
        echo "[ok] hash matches"
    else
        echo "[!!] hash mismatch on local tarball"
        echo "    expected: ${PYNAOQI_SHA256}"
        echo "    got:      $(sha256sum "${TARBALL_PATH}" | awk '{print $1}')"
        echo "    delete or replace ${TARBALL_PATH} and re-run."
        exit 1
    fi
else
    echo "[..] downloading pynaoqi from Aldebaran CDN..."
    if curl --fail --location --show-error --max-time 300 \
            -o "${TARBALL_PATH}.tmp" "${PRIMARY_URL}"; then
        mv "${TARBALL_PATH}.tmp" "${TARBALL_PATH}"
        echo "[ok] download complete (primary)"
    else
        rm -f "${TARBALL_PATH}.tmp"
        echo "[!!] primary CDN unreachable; trying Wayback Machine snapshot..."
        if curl --fail --location --show-error --max-time 300 \
                -o "${TARBALL_PATH}.tmp" "${WAYBACK_URL}"; then
            mv "${TARBALL_PATH}.tmp" "${TARBALL_PATH}"
            echo "[ok] download complete (wayback)"
        else
            rm -f "${TARBALL_PATH}.tmp"
            cat <<EOF >&2

[!!] both canonical sources are unreachable.

    The pynaoqi SDK this script needs:
      filename: ${PYNAOQI_FILENAME}
      size:     ${PYNAOQI_SIZE} bytes
      sha256:   ${PYNAOQI_SHA256}

    Obtain it from any source that produces a byte-identical file
    (verifiable against the SHA256 above), place it at:
      ${TARBALL_PATH}
    and re-run this script.
EOF
            exit 1
        fi
    fi

    echo "[..] verifying SHA256..."
    if verify_sha "${TARBALL_PATH}"; then
        echo "[ok] hash matches"
    else
        echo "[!!] downloaded file failed hash check; refusing to extract"
        echo "    expected: ${PYNAOQI_SHA256}"
        echo "    got:      $(sha256sum "${TARBALL_PATH}" | awk '{print $1}')"
        rm -f "${TARBALL_PATH}"
        exit 1
    fi
fi

echo "[..] extracting to ${SDK_DIR}..."
tar -xzf "${TARBALL_PATH}" -C "${PEPPERBOX_HOME}"

if [[ ! -f "${NAOQI_PY_PATH}" ]]; then
    echo "[!!] extraction completed but expected layout is missing"
    echo "    looked for: ${NAOQI_PY_PATH}"
    exit 1
fi

echo "[ok] pynaoqi extracted; physical-robot bridge ready"
echo
echo "Next steps:"
echo "  Sim:       NAOQI_IP=127.0.0.1 ./run.sh"
echo "  Physical:  NAOQI_IP=<robot.ip> NAOQI_PORT=9559 ./run.sh"
