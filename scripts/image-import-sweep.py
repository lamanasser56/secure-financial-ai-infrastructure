#!/usr/bin/env python3
"""Find imports an image cannot satisfy, starting from its declared entry modules (stdlib only; runs inside the image).

Every module reachable from the entry modules through the image's own code is parsed (imports inside functions
included, since lazy imports fail only when first used). Modules are resolved on the filesystem along sys.path,
never imported, so no image code runs. Third-party modules are checked for presence, not followed. An import
guarded by `except ImportError`/`ModuleNotFoundError` is reported as optional, not as a failure.
"""
import ast
import json
from pathlib import Path
import sys
import sysconfig

STDLIB = set(sys.stdlib_module_names) | {'__future__'}
SITE = {str(Path(p).resolve()) for p in (sysconfig.get_paths()['purelib'], sysconfig.get_paths()['platlib'])}
STDLIB_DIR = str(Path(sysconfig.get_paths()['stdlib']).resolve())
SUFFIXES = ('.py', '.pyc', '.so', '.pyd')


def locate(name):
    """Filesystem location of a module or package along sys.path, or None (namespace packages included)."""
    parts = name.split('.')
    for entry in sys.path:
        base = Path(entry or '.')
        if not base.is_dir():
            continue
        found = base
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            directory = found / part
            if directory.is_dir() and (not last or (directory / '__init__.py').exists()
                                       or any(directory.iterdir())):
                found = directory
                continue
            if last and any(p.name.split('.')[0] == part and p.name.endswith(SUFFIXES) and p.is_file()
                            for p in found.glob(part + '.*')):
                found = next(p for p in sorted(found.glob(part + '.*'))
                             if p.name.split('.')[0] == part and p.name.endswith(SUFFIXES))
                continue
            found = None
            break
        if found is not None:
            return found
    return None


def origin(path):
    """'local' for the image's own code, 'third' for site-packages, 'stdlib' for the standard library."""
    resolved = str(path.resolve())
    if any(resolved.startswith(s + '/') or resolved == s for s in SITE):
        return 'third'
    if resolved.startswith(STDLIB_DIR + '/'):
        return 'stdlib'
    return 'local'


def source_of(path):
    if path.is_dir():
        init = path / '__init__.py'
        return init if init.exists() else None
    return path if path.suffix == '.py' else None


def guarded(node, parents):
    """True when the import sits in a try whose handlers catch ImportError or ModuleNotFoundError."""
    child = node
    for parent in reversed(parents):
        if isinstance(parent, ast.Try) and child in parent.body:
            for handler in parent.handlers:
                names = []
                if handler.type is None:
                    return True
                for item in (handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]):
                    if isinstance(item, ast.Name):
                        names.append(item.id)
                if {'ImportError', 'ModuleNotFoundError', 'Exception', 'BaseException'} & set(names):
                    return True
        child = parent
    return False


def imports(tree, module, is_package):
    """(imported name, line, guarded) for every import statement, relative imports resolved."""
    found = []

    def visit(node, parents):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno, guarded(node, parents)))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = module.split('.') if is_package else module.split('.')[:-1]
                package = package[:len(package) - (node.level - 1)] if node.level > 1 else package
                base = '.'.join(package + ([node.module] if node.module else []))
            else:
                base = node.module or ''
            found.append((base, node.lineno, guarded(node, parents)))
            for alias in node.names:
                if alias.name != '*':
                    found.append((base + '.' + alias.name, node.lineno, 'submodule'))
        for child in ast.iter_child_nodes(node):
            visit(child, parents + [node])
    visit(tree, [])
    return found


def sweep(entries):
    queue, seen, missing, optional, third = list(entries), set(), [], [], set()
    for entry in entries:
        if locate(entry) is None:
            missing.append({'module': entry, 'imported_by': '<entry>', 'line': 0})
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        path = locate(module)
        if path is None or origin(path) != 'local':
            continue
        source = source_of(path)
        if source is None:
            continue
        tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
        for name, line, guard in imports(tree, module, path.is_dir()):
            if not name or name.split('.')[0] in STDLIB:
                continue
            target = locate(name)
            if target is None:
                if guard == 'submodule':
                    continue  # `from package import attribute`: an attribute, not necessarily a submodule
                record = {'module': name, 'imported_by': str(source), 'line': line}
                (optional if guard else missing).append(record)
                continue
            kind = origin(target)
            if kind == 'third':
                third.add(name.split('.')[0])
            elif kind == 'local':
                queue.append(name)
    return {'entries': sorted(entries), 'local_modules': len([m for m in seen if (p := locate(m)) and origin(p) == 'local']),
            'third_party': sorted(third), 'missing': missing, 'optional_missing': optional}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('usage: image-import-sweep.py ENTRY_MODULE...')
    result = sweep(sys.argv[1:])
    print(json.dumps(result, indent=1, sort_keys=True))
    raise SystemExit(1 if result['missing'] else 0)
