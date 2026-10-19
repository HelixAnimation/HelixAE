"""Validated, recoverable CEP installation (stdlib only)."""
import hashlib
import os
import shutil
import stat
import tempfile
import zipfile


REQUIRED_FILES = {"index.html", "CSXS/manifest.xml", "js/main.js"}


def archive_files(archive):
    """Read and validate the complete payload before touching an installation."""
    files = {}
    seen = set()
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            name = entry.filename
            parts = name.rstrip("/").split("/")
            if (not name or "\\" in name or ":" in name
                    or any(part in ("", ".", "..") for part in parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("Unsafe panel archive member: %s" % name)
            key = name.rstrip("/").casefold()
            if key in seen:
                raise ValueError("Duplicate panel archive member: %s" % name)
            seen.add(key)
            if not entry.is_dir():
                files[name] = package.read(entry)  # includes CRC verification
    if not REQUIRED_FILES.issubset(files):
        raise ValueError("Panel archive is missing required files")
    return files


def expanded_launcher(template, prism_root, plugin_root):
    for root in (prism_root, plugin_root):
        if not isinstance(root, str) or not root or any(c in root for c in '\r\n"%'):
            raise ValueError("Unsupported launcher path: %r" % root)
    runtime = os.path.join(prism_root, "Python313", "python.exe")
    script = os.path.join(plugin_root, "Scripts", "HelixAE_MenuTools.py")
    for path in (runtime, script):
        if not os.path.isfile(path):
            raise ValueError("Installation prerequisite missing: %s" % path)
    with open(template, encoding="utf-8") as handle:
        text = handle.read()
    if "PRISMROOT" not in text or "PLUGINROOT" not in text:
        raise ValueError("Launcher template is missing path placeholders")
    text = text.replace("PRISMROOT", prism_root.replace("\\", "/"))
    text = text.replace("PLUGINROOT", plugin_root.replace("\\", "/"))
    # No delayed expansion: literal exclamation marks in paths must survive.
    if "setlocal DisableDelayedExpansion" not in text:
        text = text.replace("@echo off", "@echo off\nsetlocal DisableDelayedExpansion", 1)
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def verify_files(folder, files):
    for name, expected in files.items():
        with open(os.path.join(folder, *name.split("/")), "rb") as handle:
            actual = handle.read()
        if hashlib.sha256(actual).digest() != hashlib.sha256(expected).digest():
            raise IOError("Installed file verification failed: %s" % name)


def install(archive, template, destination, prism_root, plugin_root):
    files = archive_files(archive)
    launcher = expanded_launcher(template, prism_root, plugin_root)
    os.makedirs(destination, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".helixae-install-", dir=destination)
    moved = []
    published = []
    keep_stage = False
    try:
        panel = os.path.join(stage, "panel")
        for name, data in files.items():
            path = os.path.join(panel, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        staged_cmd = os.path.join(stage, "launcher.cmd")
        with open(staged_cmd, "wb") as handle:
            handle.write(launcher)
        verify_files(panel, files)
        targets = [(panel, os.path.join(destination, "helixae")),
                   (staged_cmd, os.path.join(destination, "helixae.cmd"))]
        try:
            for index, (source, target) in enumerate(targets):
                if os.path.lexists(target):
                    backup = os.path.join(stage, "previous-%d" % index)
                    os.replace(target, backup)
                    moved.append((backup, target))
                os.replace(source, target)
                published.append(target)
            verify_files(targets[0][1], files)
            with open(targets[1][1], "rb") as handle:
                if handle.read() != launcher:
                    raise IOError("Installed launcher verification failed")
        except Exception as failure:
            recovery_errors = []
            for target in reversed(published):
                try:
                    if os.path.isdir(target):
                        shutil.rmtree(target)
                    else:
                        os.remove(target)
                except OSError as error:
                    recovery_errors.append(str(error))
            for backup, target in reversed(moved):
                try:
                    os.replace(backup, target)
                except OSError as error:
                    recovery_errors.append(str(error))
            if recovery_errors:
                keep_stage = True
                raise RuntimeError("%s; recovery incomplete; backups retained at %s: %s"
                                   % (failure, stage, "; ".join(recovery_errors))) from failure
            raise RuntimeError("%s; previous integration restored" % failure) from failure
        return True
    finally:
        if not keep_stage:
            shutil.rmtree(stage, ignore_errors=True)
