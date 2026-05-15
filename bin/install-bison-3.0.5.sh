#!/usr/bin/env bash
# Install bison 3.0.5 to ~/.local/opt/bison-3.0.5 and symlink into ~/.local/bin.
# CUBRID requires bison 3.0.5 specifically for its grammar (csql_grammar.y).
set -euo pipefail

VERSION="3.0.5"
PREFIX="${HOME}/.local/opt/bison-${VERSION}"
BIN_DIR="${HOME}/.local/bin"
BUILD_ROOT="${HOME}/.local/src/bison-build"
TARBALL="bison-${VERSION}.tar.gz"
URL="https://ftp.gnu.org/gnu/bison/${TARBALL}"
JOBS="$(nproc 2>/dev/null || echo 4)"

echo "==> Installing bison ${VERSION} to ${PREFIX}"

if [[ -x "${PREFIX}/bin/bison" ]]; then
  installed_ver="$("${PREFIX}/bin/bison" --version | head -1 | awk '{print $NF}')"
  if [[ "${installed_ver}" == "${VERSION}" ]]; then
    echo "==> Already installed: ${PREFIX}/bin/bison (${installed_ver})"
  fi
else
  mkdir -p "${BUILD_ROOT}" "${BIN_DIR}"
  cd "${BUILD_ROOT}"

  if [[ ! -f "${TARBALL}" ]]; then
    echo "==> Downloading ${URL}"
    curl -fLO "${URL}"
  fi

  if [[ ! -d "bison-${VERSION}" ]]; then
    echo "==> Extracting ${TARBALL}"
    tar xzf "${TARBALL}"
  fi

  cd "bison-${VERSION}"

  if [[ ! -f Makefile ]]; then
    echo "==> Configuring (prefix=${PREFIX})"
    ./configure --prefix="${PREFIX}"
  fi

  echo "==> Building with -j${JOBS}"
  make -j"${JOBS}"

  echo "==> Installing"
  make install
fi

echo "==> Linking binaries into ${BIN_DIR}"
mkdir -p "${BIN_DIR}"
for bin in bison yacc; do
  src="${PREFIX}/bin/${bin}"
  dst="${BIN_DIR}/${bin}"
  if [[ -x "${src}" ]]; then
    ln -sfn "${src}" "${dst}"
    echo "    ${dst} -> ${src}"
  fi
done

echo
echo "==> Done. Verifying:"
hash -r 2>/dev/null || true
"${BIN_DIR}/bison" --version | head -1
echo
echo "If 'bison' on PATH still resolves elsewhere, ensure ${BIN_DIR} is early in PATH"
echo "or remove the stale entry /home/vimkim/temp/bison-install/bin."
