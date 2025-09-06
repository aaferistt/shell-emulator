import shlex
import sys

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

def cmd_history(args):
    print("history: not implemented")
    return 0

COMMANDS = {
    "ls": cmd_ls,
    "cd": cmd_cd,
    "exit": None,
}

def run_line(line: str):
    line = line.strip()
    if not line:
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
    rc = handler(args)
    return False, rc

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

if __name__ == "__main__":
    repl()
