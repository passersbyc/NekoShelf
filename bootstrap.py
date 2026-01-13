import os
import sys
import subprocess
import venv
from pathlib import Path


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(cmd, env=None):
    subprocess.check_call(cmd, env=env)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parent
    venv_dir = root / ".venv"

    env = os.environ.copy()
    if os.name == "nt":
        env.setdefault("PYTHONUTF8", "1")

    if ("--install-only" in argv) and ("--run" in argv):
        raise SystemExit("--install-only 与 --run 不能同时使用")

    if not venv_dir.exists():
        venv.create(venv_dir, with_pip=True)

    py = _venv_python(venv_dir)
    if not py.exists():
        raise SystemExit(f"虚拟环境 Python 不存在: {py}")

    _run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], env=env)
    _run([str(py), "-m", "pip", "install", "-e", str(root)], env=env)

    if "--test" in argv:
        _run([str(py), "-m", "unittest", "discover", "-s", "tests", "-p", "test*.py", "-v"], env=env)

    if ("--install-only" in argv) and ("--test" not in argv):
        return 0

    if ("--run" in argv) or ("--install-only" not in argv):
        return subprocess.call([str(py), str(root / "main.py")], env=env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

