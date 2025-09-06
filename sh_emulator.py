import argparse
import base64
import shlex
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, List

@dataclass
class VNode:
    name: str
    perms: int = 0o755
    parent: Optional["Dir"] = None

    def path(self) -> str:
        parts = []
        node = self
        while node and node.parent is not None:
            parts.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(parts))

@dataclass
class File(VNode):
    content: bytes = b""
    is_binary: bool = False

@dataclass
class Dir(VNode):
    children: Dict[str, VNode] = field(default_factory=dict)
    def add(self, node: VNode):
        self.children[node.name] = node
        node.parent = self
    def get(self, name: str):
        return self.children.get(name)

VFS_ZIP: Optional[str] = None
STARTUP: Optional[str] = None
VFS_NAME = "no-vfs"
CWD: Dir = Dir(name="")
ROOT: Dir = CWD
HISTORY: List[str] = []

class ShellError(Exception):
    pass

def ensure_dir(path: str) -> Dir:
    parts = [p for p in path.strip("/").split("/") if p]
    node = ROOT
    for p in parts:
        nxt = isinstance(node, Dir) and node.get(p)
        if not nxt:
            newd = Dir(name=p)
            node.add(newd)
            node = newd
        else:
            if isinstance(nxt, Dir):
                node = nxt
            else:
                raise ShellError(f"Path component is file: /{'/'.join(parts)}")
    return node

def write_file(path: str, data: bytes, is_binary: bool):
    dirname, _, fname = path.strip("/").rpartition("/")
    dirnode = ensure_dir(dirname) if dirname else ROOT
    f = File(name=fname, content=data, is_binary=is_binary, perms=0o644)
    dirnode.add(f)

def load_vfs(vfs_zip: str):
    global VFS_NAME
    p = Path(vfs_zip)
    if not p.exists():
        fatal(f"VFS load error: file not found: {vfs_zip}")
    if not zipfile.is_zipfile(p):
        fatal(f"VFS load error: not a zip file: {vfs_zip}")
    VFS_NAME = p.stem
    try:
        with zipfile.ZipFile(p, "r") as z:
            for zi in z.infolist():
                if zi.is_dir():
                    ensure_dir(zi.filename.rstrip("/"))
                    continue
                data = z.read(zi.filename)
                is_b64 = zi.filename.endswith(".b64")
                if is_b64:
                    try:
                        decoded = base64.b64decode(data)
                    except Exception as e:
                        fatal(f"VFS load error: invalid base64 in {zi.filename}: {e}")
                    write_file(zi.filename[:-4], decoded, is_binary=True)
                else:
                    write_file(zi.filename, data, is_binary=False)
    except zipfile.BadZipFile as e:
        fatal(f"VFS load error: bad zip: {e}")

def fatal(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(2)

def resolve(path: str) -> VNode:
    if not path or path == ".":
        return CWD
    if path.startswith("/"):
        node: VNode = ROOT
        parts = [p for p in path.split("/") if p]
    else:
        node = CWD
        parts = [p for p in path.split("/") if p]
    for p in parts:
        if p == ".":
            continue
        if p == "..":
            if node.parent is not None:
                node = node.parent
            continue
        if isinstance(node, Dir) and p in node.children:
            node = node.children[p]
        else:
            raise ShellError(f"No such file or directory: {path}")
    return node

def fmt_perms(mode: int, is_dir: bool) -> str:
    def triad(bits): return "".join(["r" if bits & 4 else "-", "w" if bits & 2 else "-", "x" if bits & 1 else "-"])
    t = "d" if is_dir else "-"
    u = triad((mode >> 6) & 7); g = triad((mode >> 3) & 7); o = triad(mode & 7)
    return t + u + g + o

def fmt_long(node: VNode) -> str:
    if isinstance(node, Dir):
        kind = "dir"; size = "-"
    else:
        kind = "bin" if node.is_binary else "txt"
        size = str(len(node.content))
    return f"{fmt_perms(node.perms, isinstance(node, Dir))}\t{kind}\t{node.name}" + ("" if size == "-" else f"\t{size}B")

def cmd_ls(args):
    path = args[0] if args else ""
    try:
        node = resolve(path)
        if isinstance(node, Dir):
            for name in sorted(node.children):
                print(fmt_long(node.children[name]))
        else:
            print(fmt_long(node))
        return 0
    except ShellError as e:
        print(f"ls: {e}", file=sys.stderr)
        return 1

def cmd_cd(args):
    global CWD
    if len(args) != 1:
        print("cd: expected exactly one argument", file=sys.stderr)
        return 1
    try:
        node = resolve(args[0])
        if not isinstance(node, Dir):
            print("cd: not a directory", file=sys.stderr)
            return 1
        CWD = node
        return 0
    except ShellError as e:
        print(f"cd: {e}", file=sys.stderr)
        return 1

def cmd_conf_dump(args):
    if args:
        print("conf-dump: no arguments expected", file=sys.stderr)
        return 1
    print(f"vfs_zip={VFS_ZIP or ''}")
    print(f"startup={STARTUP or ''}")
    print(f"vfs_loaded={'yes' if VFS_ZIP else 'no'}")
    print(f"vfs_name={VFS_NAME}")
    print(f"cwd={CWD.path()}")
    return 0

COMMANDS = {
    "ls": cmd_ls,
    "cd": cmd_cd,
    "conf-dump": cmd_conf_dump,
    "exit": None,
}

def run_line(line: str, echo: bool = False):
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
        print(f"[{VFS_NAME}] {CWD.path()}$ {line}")
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
    while True:
        try:
            line = input(f"[{VFS_NAME}] {CWD.path()}$ ")
        except EOFError:
            print()
            break
        should_exit, _ = run_line(line)
        if should_exit:
            break

def main(argv=None):
    global VFS_ZIP, STARTUP, VFS_NAME
    ap = argparse.ArgumentParser(description="Shell emulator (stage 3)")
    ap.add_argument("--vfs-zip", default=None)
    ap.add_argument("--startup", default=None)
    args = ap.parse_args(argv)
    VFS_ZIP = args.vfs_zip
    STARTUP = args.startup
    if VFS_ZIP:
        load_vfs(VFS_ZIP)
    else:
        VFS_NAME = "no-vfs"
    if STARTUP:
        rc = run_startup(STARTUP)
        if rc != 0:
            sys.exit(rc)
    repl()

if __name__ == "__main__":
    main()
