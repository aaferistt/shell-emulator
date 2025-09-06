import argparse
import shlex
import sys
from pathlib import Path

VFS_ZIP = None
STARTUP = None
VFS_NAME = "no-vfs"
CWD = "/"
HISTORY = []

def cmd_ls(args):
    print("ls", *args)
    return 0

def cmd_cd(args):
    if len(args) != 1:
        print("cd: expected exactly one argument", file=sys.stderr)
        return 1
    print("cd", args[0])
    return 0

def cmd_conf_dump(args):
    if args:
        print("conf-dump: no arguments expected", file=sys.stderr)
        return 1
    print(f"vfs_zip={VFS_ZIP or ''}")
    print(f"startup={STARTUP or ''}")
    print(f"vfs_loaded=no")
    print(f"vfs_name={VFS_NAME}")
    print(f"cwd={CWD}")
    return 0

COMMANDS = {
    "ls": cmd_ls,
    "cd": cmd_cd,
    "conf-dump": cmd_conf_dump,
    "exit": None,
}

def run_line(line: str, echo: bool = False):
    global CWD
    line = line.rstrip("\n")
    if not line.strip():
        return False, 0
    try:
        parts = shlex.split(line)
    except ValueError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return False, 1

    HISTORY.append(line)
    cmd, *args = parts
    if cmd == "exit":
        return True, 0
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return False, 127

    if echo:
        print(f"[{VFS_NAME}] {CWD}$ {line}")
    rc = handler(args)
    return False, rc

def run_startup(script_path: str) -> int:
    p = Path(script_path)
    if not p.exists():
        print(f"Startup error: file not found: {script_path}", file=sys.stderr)
        return 2
    with p.open("r", encoding="utf-8") as f:
        for raw in f:
            should_exit, rc = run_line(raw, echo=True)
            if rc != 0:
                print(f"Startup halted due to error (rc={rc}).", file=sys.stderr)
                return rc
            if should_exit:
                return 0
    return 0

def repl():
    global CWD
    while True:
        try:
            line = input(f"[{VFS_NAME}] {CWD}$ ")
        except EOFError:
            print()
            break
        should_exit, _ = run_line(line)
        if should_exit:
            break

def main(argv=None):
    global VFS_ZIP, STARTUP, VFS_NAME
    ap = argparse.ArgumentParser(description="Shell emulator (stage 2)")
    ap.add_argument("--vfs-zip", default=None)
    ap.add_argument("--startup", default=None)
    args = ap.parse_args(argv)

    VFS_ZIP = args.vfs_zip
    STARTUP = args.startup
    if VFS_ZIP:
        VFS_NAME = Path(VFS_ZIP).stem

    if STARTUP:
        rc = run_startup(STARTUP)
        if rc != 0:
            sys.exit(rc)

    repl()

if __name__ == "__main__":
    main()
