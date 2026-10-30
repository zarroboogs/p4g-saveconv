"""Convert decrypted Persona 4 Golden PS4 exports to PC .bin/.binslot files.

Only Python's standard library is required. See README.md for format notes.
The legacy target matches convert_vita2pc.py; extended preserves the PS4 layout.
"""

import argparse
import hashlib
import re
import struct
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from remotecache import write_remcache


HEADER_SIZE = 0x38
HEADER_CHECKSUM_OFFSET = 0x36
RETRY_CAPACITY = 0x1B000
SLOT_DATA_SIZE = 0x34C
SLOT_MAGIC = b"SAVE0001"
SLOT_SALT = b"P4GOLDEN"
# Segment order is significant (0x0E precedes 0x08).
COMMON_LAYOUT = (
    (0x01, 0x10), (0x02, 0xC74), (0x03, 0x528), (0x04, 0x340),
    (0x05, 0x400), (0x06, 0x0C), (0x07, 0x178), (0x0E, 0xB0),
    (0x08, 0xA00), (0x09, 0x3000), (0x0A, 0x20), (0x0B, 0xC8),
    (0x0C, 0x174), (0x0D, 0xF8FC), (0x0F, 0x3FA4),
    (0x10, 0x80), (0x11, 0x100), (0x12, 0xA7C), (0x13, 0x28),
)
EXTRA_LAYOUT = ((0x14, 4), (0x15, 0x600))
RETRY_LAYOUT = ((0x10000001, 4), (0x10000002, 4),
                (0x10000003, RETRY_CAPACITY))
SAVE_DIR_RE = re.compile(r"(?:CUSA\d+_)?(SAVELIST\d{4}|CHANNELSAVE|SYSTEMSAVE)", re.I)


class SaveError(ValueError):
    """A save conversion could not be completed."""


def pack_segment(kind, payload):
    return struct.pack("<II", kind, len(payload)) + payload


def finish_save(data, checksum_start=HEADER_SIZE):
    return bytes(data) + struct.pack(
        "<IIBI", 0x2000, 1, sum(data[checksum_start:]) & 0xFF, 0xFFFFFFFF
    )


def parse_save(data, pc_format="extended", has_retry=True):
    """Extract segment payloads using the selected save layout."""
    layout = COMMON_LAYOUT
    if pc_format == "extended":
        layout += EXTRA_LAYOUT
    if has_retry:
        layout += RETRY_LAYOUT
    offset = HEADER_SIZE
    segments = {}
    for kind, size in layout:
        end = offset + 8 + size
        segments[kind] = data[offset + 8:end]
        offset = end
    return segments


def convert_bin(data, pc_format="legacy", custom_diff=None, has_retry=True):
    """Convert main and embedded retry saves without borrowing another save's state."""
    segments = parse_save(data, "extended", has_retry)
    if has_retry:
        retry_size = struct.unpack("<I", segments[0x10000002])[0]
        if retry_size:
            retry = convert_bin(segments[0x10000003][:retry_size],
                                pc_format, custom_diff, has_retry=False)
            segments[0x10000002] = struct.pack("<I", len(retry))
            # Extended/no-edit mode preserves even unused padding byte for byte.
            if pc_format != "extended" or custom_diff:
                segments[0x10000003] = retry.ljust(RETRY_CAPACITY, b"\0")
    result = bytearray(data[:HEADER_SIZE])
    if pc_format == "legacy":
        struct.pack_into("<H", result, HEADER_CHECKSUM_OFFSET,
                         sum(result[4:HEADER_CHECKSUM_OFFSET]) & 0xFF)
    layout = COMMON_LAYOUT + (EXTRA_LAYOUT if pc_format == "extended" else ())
    if has_retry:
        layout += RETRY_LAYOUT
    for kind, _ in layout:
        result.extend(pack_segment(kind, segments[kind]))
    if custom_diff == "enable":
        result[0x1304] |= 0x03
    elif custom_diff == "disable":
        result[0x1304] &= ~0x03
    return finish_save(result)


def conv_bin(ps4_bin, pc_bin, custom_diff=None, pc_format="legacy"):
    """File-stream interface, like the existing Vita/PC converters."""
    ps4_bin.seek(0)
    result = convert_bin(ps4_bin.read(), pc_format, custom_diff)
    pc_bin.seek(0)
    pc_bin.write(result)
    pc_bin.truncate()


def put_text(buffer, offset, size, text):
    """Write a terminated UTF-8 field, never cutting a multibyte character."""
    raw = text.encode("utf-8")[:size - 1].decode("utf-8", errors="ignore").encode("utf-8")
    buffer[offset:offset + size] = raw.ljust(size, b"\0")


def read_name(raw):
    # Each SJIS name occupies 18 bytes, including its NUL terminator.
    name = raw.split(b"\0", 1)[0].decode("cp932", errors="replace")
    # The game stores Latin letters full-width; compact them for the menu fields.
    name = unicodedata.normalize("NFKC", name)
    return "".join(c for c in name if c.isprintable() and c not in ":\r\n")


def make_binslot(data, modified_time, system=False):
    """Build PC metadata and both MD5 hashes from the converted save itself.

    Without a PS4 param.sfo, localized location names are unavailable. Use the
    save's location IDs and a generic phase label; the game can refresh these
    display strings when the imported slot is saved again.
    """
    slot = bytearray(SLOT_DATA_SIZE)
    if system:
        put_text(slot, 4, 0x40, "SAVE DATA")
        put_text(slot, 0x44, 0x80, "SYSTEM DATA")
    else:
        day, phase, frames = struct.unpack_from("<HHI", data, 4)
        level, difficulty, cleared = struct.unpack_from("<BBB", data, 0x0C)
        surname = read_name(data[0x64:0x76])
        firstname = read_name(data[0x76:0x88])
        name = f"{firstname} {surname}".strip() or "PS4 player"
        date = (datetime(2011, 4, 1) + timedelta(days=day)).strftime("%m/%d")
        # These labels are confirmed by the PC and decrypted Vita references.
        phases = {3: "Afternoon", 4: "After School", 5: "Evening"}
        date_phase = f"{date}:{phases.get(phase, f'Time {phase}')}"
        area = (data[0x34], data[0x35])
        locations = {(8, 2): "Central Shopping District", (255, 255): "RESERVE"}
        location = locations.get(area, f"Area {area[0]}/{area[1]}")
        title = f"{name} Lv:{level}"
        seconds = frames // 30  # Verified against PC reference: 14686 -> 0:08:09.
        play_time = f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        difficulties = {0: "CUSTOM", 1: "VERY EASY", 2: "EASY", 3: "NORMAL",
                        4: "HARD", 5: "VERY HARD"}
        diff = difficulties.get(difficulty, f"{difficulty}")
        put_text(slot, 4, 0x40, title)
        put_text(slot, 0x44, 0x80, f"{date_phase}:{location}")
        details = (f"Date:{date_phase}\nName:{title}\nDifficulty:{diff} \n"
                   f"Location:{location}\nPlay Time:{play_time}\nLANG1\n"
                   f"Times Cleared:{cleared}\n")
        put_text(slot, 0xC4, 0x200, details)
    put_text(slot, 0x2C4, 0x40, "app0:/data/icon.png")
    stamp = datetime.fromtimestamp(modified_time, timezone.utc)
    # 0x304..0x30B are two reserved/user fields, not the timestamp.
    struct.pack_into("<6HI", slot, 0x30C, stamp.year, stamp.month, stamp.day,
                     stamp.hour, stamp.minute, stamp.second, stamp.microsecond)
    return (SLOT_MAGIC + hashlib.md5(slot + SLOT_SALT).digest()
            + hashlib.md5(data).digest() + slot)


def discover_saves(source):
    """Accept one exported slot directory or an account/export directory tree."""
    if not source.is_dir():
        raise SaveError(f"save directory does not exist: {source}")
    found = {}
    ignored_settings = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name.lower() != "game.bin":
            continue
        match = SAVE_DIR_RE.fullmatch(path.parent.name)
        if not match:
            continue
        kind = match[1].upper()
        if kind == "SYSTEMSAVE":
            ignored_settings += 1
            continue
        if kind == "CHANNELSAVE":
            name = "system.bin"
        else:
            number = int(kind[-4:])
            if not 1 <= number <= 16:
                raise SaveError(f"unsupported slot {number}: {path}")
            name = f"data{number:04}.bin"
        if name in found:
            raise SaveError(f"multiple exports for {name}: {found[name]} and {path}; select one account/export")
        found[name] = path
    if not any(name.startswith("data") for name in found):
        raise SaveError("no SAVELIST0001..0016/GAME.BIN files found; use a decrypted PS4 export")
    return found, ignored_settings


def convert_directory(source, destination=None, pc_format="legacy", custom_diff=None):
    source = Path(source).resolve()
    destination = Path(destination).resolve() if destination else source.with_name(source.name + "_conv")
    if source == destination or source in destination.parents:
        raise SaveError("output must be outside the input directory")
    # A new directory prevents accidental replacement/mixing of existing saves.
    if destination.exists():
        raise SaveError(f"output already exists: {destination}; choose a new --output directory")
    files, ignored_settings = discover_saves(source)
    prepared = {}
    for name, path in sorted(files.items()):
        try:
            data = path.read_bytes()
            if name != "system.bin":
                data = convert_bin(data, pc_format, custom_diff)
            prepared[name] = data
            prepared[name + "slot"] = make_binslot(data, path.stat().st_mtime,
                                                   system=name == "system.bin")
        except SaveError as exc:
            raise SaveError(f"{path}: {exc}") from exc
    # Prepare all conversions before creating output files.
    destination.mkdir(parents=True)
    remote = destination / "remote"
    remote.mkdir()
    for name, data in prepared.items():
        (remote / name).write_bytes(data)
    write_remcache(destination / "remotecache.vdf", remote)
    return destination, len(files), ignored_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save_dir", type=Path, help="decrypted PS4 export/account or SAVELIST directory")
    parser.add_argument("-o", "--output", type=Path, help="new output directory (default: <save_dir>_conv)")
    parser.add_argument("--pc-format", choices=("legacy", "extended"), default="legacy",
                        help="legacy matches the original PC converter; extended preserves the expanded layout")
    parser.add_argument("--custom-diff", choices=("enable", "disable"), help="toggle the custom difficulty menu")
    args = parser.parse_args(argv)
    try:
        output, count, ignored = convert_directory(args.save_dir, args.output,
                                                   args.pc_format, args.custom_diff)
    except (SaveError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Converted {count} save files ({args.pc_format}) to {output / 'remote'}")
    print(f"Generated matching .binslot files and {output / 'remotecache.vdf'}")
    if ignored:
        print("Skipped PS4 SYSTEMSAVE settings; CHANNELSAVE supplies PC system.bin when present.")
    print("Save-menu time/location labels are generic; re-save each imported slot in game to refresh them.")


if __name__ == "__main__":
    main()
