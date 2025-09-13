from __future__ import annotations
import argparse
import base64
import shlex
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, List, Tuple

@dataclass
class VNode:
    name: str
    perms: int = 0o755
    parent: Optional["Dir"] = None
    def path(self) -> str:
        parts: List[str] = []
        node: Optional[VNode] = self
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
    def add(self, node: VNode) -> None:
        self.children[node.name] = node
        node.parent = self
    def get(self, name: str) -> Optional[VNode]:
        return self.children.get(name)

VFS_ZIP: Optional[str] = None
STARTUP: Optional[str] = None
VFS_NAME: str = "no-vfs"
ROOT: Dir = Dir(name="")
CWD: Dir = ROOT
HISTORY: List[str] = []

class ShellError(Exception):
    pass

def _fatal(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(2)

def _ensure_dir(path: str) -> Dir:
    parts = [p for p in path.strip("/").split("/") if p]
    node: Dir = ROOT
    for p in parts:
        nxt = node.get(p)
        if not nxt:
            d = Dir(name=p)
            node.add(d)
            node = d
        else:
            if isinstance(nxt, Dir):
                node = nxt
            else:
                _fatal(f"VFS load error: path component is file: /{'/'.join(parts)}")
    return node

def _write_file(path: str, data: bytes, is_binary: bool) -> None:
    dirname, _, fname = path.strip("/").rpartition("/")
    dirnode = _ensure_dir(dirname) if dirname else ROOT
    f = File(name=fname, content=data, is_binary=is_binary, perms=0o644)
    dirnode.add(f)

def load_vfs(vfs_zip: str) -> None:
    global VFS_NAME
    p = Path(vfs_zip)
    if not p.exists():
        _fatal(f"VFS load error: file not found: {vfs_zip}")
    if not zipfile.is_zipfile(p):
        _fatal(f"VFS load error: not a zip file: {vfs_zip}")
    VFS_NAME = p.stem
    try:
        with zipfile.ZipFile(p, "r") as z:
            for zi in z.infolist():
                if zi.is_dir():
                    _ensure_dir(zi.filename.rstrip("/"))
                    continue
                data = z.read(zi.filename)
                if zi.filename.endswith(".b64"):
                    try:
                        decoded = base64.b64decode(data)
                    except Exception as e:
                        _fatal(f"VFS load error: invalid base64 in {zi.filename}: {e}")
                    _write_file(zi.filename[:-4], decoded, is_binary=True)
                else:
                    _write_file(zi.filename, data, is_binary=False)
    except zipfile.BadZipFile as e:
        _fatal(f"VFS load error: bad zip: {e}")

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

def _fmt_perms(mode: int, is_dir: bool) -> str:
    def triad(bits: int) -> str:
        return "".join(["r" if bits & 4 else "-", "w" if bits & 2 else "-", "x" if bits & 1 else "-"])
    t = "d" if is_dir else "-"
    u = triad((mode >> 6) & 7)
    g = triad((mode >> 3) & 7)
    o = triad(mode & 7)
    return t + u + g + o

def _fmt_long(node: VNode) -> str:
    if isinstance(node, Dir):
        kind = "dir"; size = "-"
    else:
        kind = "bin" if node.is_binary else "txt"
        size = str(len(node.content))
    return f"{_fmt_perms(node.perms, isinstance(node, Dir))}\t{kind}\t{node.name}" + ("" if size == "-" else f"\t{size}B")

def cmd_ls(args: List[str]) -> int:
    path = args[0] if args else ""
    try:
        node = resolve(path)
        if isinstance(node, Dir):
            for name in sorted(node.children):
                print(_fmt_long(node.children[name]))
        else:
            print(_fmt_long(node))
        return 0
    except ShellError as e:
        print(f"ls: {e}", file=sys.stderr)
        return 1

def cmd_cd(args: List[str]) -> int:
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

def cmd_pwd(args: List[str]) -> int:
    if args:
        print("pwd: no arguments expected", file=sys.stderr)
        return 1
    print(CWD.path())
    return 0

def cmd_history(args: List[str]) -> int:
    if args:
        print("history: no arguments expected", file=sys.stderr)
        return 1
    for i, line in enumerate(HISTORY, 1):
        print(f"{i}  {line}")
    return 0

def _print_tree(node: VNode, prefix: str) -> None:
    if isinstance(node, Dir):
        items = list(sorted(node.children.items()))
        for idx, (name, child) in enumerate(items):
            last = (idx == len(items) - 1)
            connector = "└── " if last else "├── "
            print(prefix + connector + name)
            more_prefix = prefix + ("    " if last else "│   ")
            _print_tree(child, more_prefix)

def cmd_tree(args: List[str]) -> int:
    path = args[0] if args else ""
    try:
        node = resolve(path)
        if isinstance(node, Dir):
            _print_tree(node, "")
        else:
            print(node.name)
        return 0
    except ShellError as e:
        print(f"tree: {e}", file=sys.stderr)
        return 1

def cmd_chmod(args: List[str]) -> int:
    if len(args) != 2:
        print("chmod: usage: chmod OCTAL path", file=sys.stderr)
        return 1
    mode_str, path = args
    try:
        mode = int(mode_str, 8)
    except ValueError:
        print("chmod: invalid mode (use octal like 755)", file=sys.stderr)
        return 1
    try:
        node = resolve(path)
        node.perms = mode
        return 0
    except ShellError as e:
        print(f"chmod: {e}", file=sys.stderr)
        return 1

def cmd_mv(args: List[str]) -> int:
    if len(args) != 2:
        print("mv: usage: mv SRC DST", file=sys.stderr)
        return 1
    src, dst = args
    try:
        src_node = resolve(src)
        if not src_node.parent:
            print("mv: cannot move root", file=sys.stderr)
            return 1
        src_parent: Dir = src_node.parent

        if dst.endswith("/"):
            dst = dst[:-1]
        if dst.startswith("/"):
            base = ROOT
            parts = [p for p in dst.split("/") if p]
        else:
            base = CWD
            parts = [p for p in dst.split("/") if p]
        if not parts:
            print("mv: invalid destination", file=sys.stderr)
            return 1
        *dir_parts, new_name = parts

        dest_dir: Dir = base
        for p in dir_parts:
            node = dest_dir.children.get(p) if isinstance(dest_dir, Dir) else None
            if not node:
                print(f"mv: destination path not found: {'/'.join(dir_parts)}", file=sys.stderr)
                return 1
            if not isinstance(node, Dir):
                print("mv: destination component is not a directory", file=sys.stderr)
                return 1
            dest_dir = node

        existing = dest_dir.children.get(new_name)
        if isinstance(existing, Dir):
            new_parent = existing
            new_name_final = src_node.name
        else:
            new_parent = dest_dir
            new_name_final = new_name

        del src_parent.children[src_node.name]
        src_node.name = new_name_final
        new_parent.add(src_node)
        return 0
    except ShellError as e:
        print(f"mv: {e}", file=sys.stderr)
        return 1

def cmd_conf_dump(args: List[str]) -> int:
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
    "ls":         cmd_ls,
    "cd":         cmd_cd,
    "pwd":        cmd_pwd,
    "history":    cmd_history,
    "tree":       cmd_tree,
    "chmod":      cmd_chmod,
    "mv":         cmd_mv,
    "conf-dump":  cmd_conf_dump,
    "exit":       None,
}

def run_line(line: str, echo: bool=False) -> Tuple[bool, int]:
    line = line.rstrip("\n")
    if not line.strip():
        return (False, 0)
    try:
        parts = shlex.split(line)
    except ValueError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return (False, 1)
    HISTORY.append(line)
    cmd, *args = parts
    if cmd == "exit":
        return (True, 0)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return (False, 127)
    if echo:
        print(f"[{VFS_NAME}] {CWD.path()}$ {line}")
    rc = handler(args)
    return (False, rc)

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

def repl() -> None:
    while True:
        try:
            line = input(f"[{VFS_NAME}] {CWD.path()}$ ")
        except EOFError:
            print()
            break
        should_exit, _ = run_line(line)
        if should_exit:
            break

def main(argv=None) -> None:
    global VFS_ZIP, STARTUP, VFS_NAME
    ap = argparse.ArgumentParser(description="Shell emulator with in-memory VFS")
    ap.add_argument("--vfs-zip", default=None, help="Путь к ZIP с VFS")
    ap.add_argument("--startup", default=None, help="Путь к скрипту команд")
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
