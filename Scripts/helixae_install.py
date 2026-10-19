"""Validated, recoverable CEP installation (stdlib only)."""
import hashlib
import os
import shutil
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile


REQUIRED_FILES = {"index.html", "CSXS/manifest.xml", "js/main.js"}
SIGNATURE_MEMBER = "META-INF/signatures.xml"


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


def _local_name(tag):
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def signature_state(data):
    """Classify signature metadata without claiming cryptographic verification."""
    if data is None:
        return "unsigned"
    if not data.strip():
        return "empty"
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return "malformed"
    if _local_name(root.tag) != "signatures":
        return "malformed"
    signatures = [child for child in root if _local_name(child.tag) == "Signature"]
    if not signatures:
        return "empty"
    for signature in signatures:
        if len(signature) or signature.attrib or (signature.text and signature.text.strip()):
            return "signed"
    return "empty"


def signature_state_from_files(files):
    return signature_state(files.get(SIGNATURE_MEMBER))


def archive_signature_state(archive):
    with zipfile.ZipFile(archive) as package:
        try:
            data = package.read(SIGNATURE_MEMBER)
        except KeyError:
            data = None
    return signature_state(data)


def enable_cep_debug_mode(winreg_module=None):
    """Allow unsigned CEP extensions on this Windows account (development only)."""
    if winreg_module is None:
        import winreg as winreg_module

    base = "Software\\Adobe"
    keys = set()
    try:
        root = winreg_module.OpenKey(
            winreg_module.HKEY_CURRENT_USER, base, 0, winreg_module.KEY_READ
        )
    except OSError:
        root = None
    if root is not None:
        try:
            index = 0
            while True:
                try:
                    name = winreg_module.EnumKey(root, index)
                except OSError:
                    break
                if name.startswith("CSXS."):
                    keys.add(name)
                index += 1
        finally:
            winreg_module.CloseKey(root)

    keys.add("CSXS.12")
    for name in sorted(keys):
        path = "%s\\%s" % (base, name)
        try:
            key = winreg_module.CreateKeyEx(
                winreg_module.HKEY_CURRENT_USER, path, 0, winreg_module.KEY_SET_VALUE
            )
        except AttributeError:
            key = winreg_module.CreateKey(winreg_module.HKEY_CURRENT_USER, path)
        try:
            winreg_module.SetValueEx(
                key, "PlayerDebugMode", 0, winreg_module.REG_SZ, "1"
            )
        finally:
            winreg_module.CloseKey(key)
    return sorted(keys)


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
