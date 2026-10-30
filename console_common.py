"""Shared file and metadata helpers for the console conversion commands."""

import re
from pathlib import Path

from convert_ps4topc import SaveError, make_binslot, put_text


FLAT_SAVE_RE = re.compile(r"data(\d{4})\.bin", re.I)


def discover_flat_saves(source):
    """Read a PC remote/ or decrypted Vita directory, case-insensitively."""
    source = Path(source)
    if not source.is_dir():
        raise SaveError(f"save directory does not exist: {source}")
    found = {}
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        match = FLAT_SAVE_RE.fullmatch(path.name)
        if path.name.lower() == "system.bin":
            name = "system.bin"
        elif match:
            number = int(match[1])
            if not 1 <= number <= 16:
                raise SaveError(f"unsupported slot {number}: {path}")
            name = f"data{number:04}.bin"
        else:
            continue
        if name in found:
            raise SaveError(f"duplicate save name: {found[name]} and {path}")
        found[name] = path
    if not any(name.startswith("data") for name in found):
        raise SaveError(f"no data0001.bin..data0016.bin files found in {source}")
    return found


def output_path(source, destination, suffix, protected=()):
    source = Path(source).resolve()
    output = (Path(destination).resolve() if destination is not None
              else source.with_name(source.name + suffix))
    for path in (source, *protected):
        path = Path(path).resolve()
        # A file template protects its containing export too.
        root = path.parent if path.is_file() else path
        if output == root or root in output.parents:
            raise SaveError("output must be outside the input and template directories")
    if output.exists():
        raise SaveError(f"output already exists: {output}; choose a new --output directory")
    return output


def write_prepared(output, prepared):
    """Write the prepared files to a new output directory."""
    output.mkdir(parents=True)
    for relative, data in prepared.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def make_sdslot(saves):
    """Build Vita's 0x40400-byte save list from (name, bytes, mtime) entries."""
    sdslot = bytearray(0x40400)
    sdslot[:4] = b"SDSL"
    sdslot[9] = 1
    for name, data, modified_time in saves:
        number = 0 if name == "system.bin" else int(name[4:8])
        payload = bytearray(make_binslot(data, modified_time, system=number == 0)[0x28:])
        # Remove only the PC language line; retain every other metadata field.
        detail = payload[0xC4:0x2C4].split(b"\0", 1)[0].decode("utf-8")
        lines = [line for line in detail.splitlines(keepends=True)
                 if not re.fullmatch(r"LANG\d+\n?", line)]
        put_text(payload, 0xC4, 0x200, "".join(lines))
        offset = 0x400 + number * 0x400
        sdslot[offset:offset + len(payload)] = payload
        sdslot[0x200 + number] = 1
    return bytes(sdslot)
