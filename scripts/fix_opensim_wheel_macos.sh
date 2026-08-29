#!/bin/bash
# The opensim 4.6 macOS wheel bundles the gfortran runtime (libgfortran,
# libquadmath, libgcc_s) but its IPOPT/MUMPS dylibs reference them via
# absolute /opt/homebrew paths, so Moco's ipopt plugin fails to load unless
# Homebrew gcc happens to be installed. Rewrite the references to
# @loader_path so the bundled copies are used. Re-run after any pip
# reinstall/upgrade of opensim.
set -euo pipefail

PKG_DIR="$(.venv/bin/python -c 'import opensim, pathlib; print(pathlib.Path(opensim.__file__).parent)')"
cd "$PKG_DIR"
BREW_GCC=/opt/homebrew/opt/gcc/lib/gcc/current

for f in libcoinmumps.3.dylib libcoinmumps.dylib libipopt.3.dylib libipopt.dylib; do
  install_name_tool \
    -change "$BREW_GCC/libgfortran.5.dylib" @loader_path/libgfortran.5.dylib \
    -change "$BREW_GCC/libquadmath.0.dylib" @loader_path/libquadmath.0.dylib "$f"
  codesign -f -s - "$f"
done

install_name_tool -id @loader_path/libgfortran.5.dylib \
  -change "$BREW_GCC/libquadmath.0.dylib" @loader_path/libquadmath.0.dylib \
  -change "$BREW_GCC/libgcc_s.1.1.dylib" @loader_path/libgcc_s.1.1.dylib \
  libgfortran.5.dylib
install_name_tool -id @loader_path/libquadmath.0.dylib libquadmath.0.dylib
install_name_tool -id @loader_path/libgcc_s.1.1.dylib libgcc_s.1.1.dylib
codesign -f -s - libgfortran.5.dylib libquadmath.0.dylib libgcc_s.1.1.dylib

echo "Patched opensim wheel in $PKG_DIR"
