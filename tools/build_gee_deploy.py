"""Write the Earth Engine Code Editor copies of the GEE app, ready to paste.

Git is the source of truth; the Code Editor holds generated copies. Layout
(mirrors the two git repos, so no algorithm code lands in the app's repo):

    users/<user>/BULC-D_rebuild          bulcd       <- ../BULC-D_rebuild/gee/bulcd.js
    users/<user>/bulcd-early-detection   app, config, outputs, inspector  <- gee/*.js

Each copy starts with a header naming its source file and commit. app gets
the two module paths for <user>. Re-run and re-paste after any change.

usage: python tools/build_gee_deploy.py <ee-username> [--out dist/gee]
"""

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BULCD_ROOT = ROOT.parent / "BULC-D_rebuild"
ENGINE_REPO, APP_REPO = "BULC-D_rebuild", "bulcd-early-detection"
APP_FILES = ("app", "config", "outputs", "inspector")


def source_version(repo: Path, path: str) -> str:
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], text=True).strip()
    dirty = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--", path]).returncode != 0
    return f"{repo.name}@{commit}{' (UNCOMMITTED CHANGES)' if dirty else ''}"


def header(repo: Path, path: str) -> str:
    return (f"// GENERATED copy of {repo.name}/{path} from {source_version(repo, path)}.\n"
            f"// Edit it in git and re-run tools/build_gee_deploy.py, not here.\n\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("user", help="Earth Engine username (the <user> in users/<user>/...)")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "gee")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.user):
        parser.error(f"not a plausible Earth Engine username: {args.user!r}")

    engine_path = f"users/{args.user}/{ENGINE_REPO}:bulcd"
    app_root = f"users/{args.user}/{APP_REPO}:"
    written = []

    out = args.out / ENGINE_REPO
    out.mkdir(parents=True, exist_ok=True)
    (out / "bulcd").write_text(header(BULCD_ROOT, "gee/bulcd.js") + (BULCD_ROOT / "gee" / "bulcd.js").read_text())
    written.append(out / "bulcd")

    out = args.out / APP_REPO
    out.mkdir(parents=True, exist_ok=True)
    for name in APP_FILES:
        text = (ROOT / "gee" / f"{name}.js").read_text()
        if name == "app":
            text, n1 = re.subn(r"^var BULCD_MODULE = '[^']*';", f"var BULCD_MODULE = '{engine_path}';", text,
                               flags=re.M)
            text, n2 = re.subn(r"^var APP_MODULE_ROOT = '[^']*';", f"var APP_MODULE_ROOT = '{app_root}';", text,
                               flags=re.M)
            if (n1, n2) != (1, 1):
                raise SystemExit("app.js: could not find the BULCD_MODULE / APP_MODULE_ROOT lines")
        (out / name).write_text(header(ROOT, f"gee/{name}.js") + text)
        written.append(out / name)

    for path in written:
        print(f"{path.relative_to(args.out)}  ->  users/{args.user}/{path.parent.name}:{path.name}")


if __name__ == "__main__":
    main()
