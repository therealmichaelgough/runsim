"""Windows counterpart of fix_opensim_wheel_macos.sh.

CasADi loads its solver plugins (casadi_nlpsol_ipopt.dll etc.) at runtime via
LoadLibrary, which searches CASADIPATH/PATH -- not Python's DLL directories.
The opensim wheel puts those DLLs inside the package dir, so Moco fails with
"Plugin 'ipopt' is not found" unless that dir is on PATH.

This script writes a sitecustomize.py into the venv that prepends the opensim
package dir to PATH at interpreter startup. Run it once after every
pip install/upgrade of opensim (recreating the venv wipes it too):

    .venv\\Scripts\\python.exe scripts\\fix_opensim_dlls_windows.py
"""
import os
import site
import sysconfig

SITECUSTOMIZE = '''\
# Written by scripts/fix_opensim_dlls_windows.py -- see that file for why.
import os

_opensim_dir = os.path.join(os.path.dirname(__file__), "opensim")
if os.path.isdir(_opensim_dir):
    os.environ["PATH"] = _opensim_dir + os.pathsep + os.environ.get("PATH", "")
    os.add_dll_directory(_opensim_dir)
'''


def main() -> None:
    site_packages = sysconfig.get_paths()["purelib"]
    opensim_dir = os.path.join(site_packages, "opensim")
    if not os.path.isdir(opensim_dir):
        raise SystemExit(f"opensim package not found at {opensim_dir}; install it first")

    target = os.path.join(site_packages, "sitecustomize.py")
    with open(target, "w") as f:
        f.write(SITECUSTOMIZE)
    print(f"wrote {target}")
    print("verify with: .venv\\Scripts\\python.exe scripts\\smoke_test_moco.py")


if __name__ == "__main__":
    main()
