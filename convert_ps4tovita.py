"""Convert decrypted PS4 P4G saves to Vita .bin files and sce_sys/sdslot.dat."""

import argparse
from io import BytesIO
from pathlib import Path

from console_common import make_sdslot, output_path, write_prepared
from convert_pc2vita import conv_bin as pc_to_vita
from convert_ps4topc import SaveError, convert_bin as ps4_to_pc, discover_saves


def convert_bin(data, custom_diff=None):
    # Reuse the established Vita conversion, including its rescue/retry reset.
    pc_data = ps4_to_pc(data, "legacy", custom_diff)
    result = BytesIO()
    pc_to_vita(BytesIO(pc_data), result)
    return result.getvalue()


def conv_bin(ps4_bin, vita_bin, custom_diff=None):
    ps4_bin.seek(0)
    data = convert_bin(ps4_bin.read(), custom_diff)
    vita_bin.seek(0)
    vita_bin.write(data)
    vita_bin.truncate()


def convert_directory(source, destination=None, custom_diff=None):
    source = Path(source).resolve()
    output = output_path(source, destination, "_vita")
    files, _ = discover_saves(source)
    prepared = {}
    metadata = []
    for name, path in sorted(files.items()):
        try:
            data = path.read_bytes()
            if name != "system.bin":
                data = convert_bin(data, custom_diff)
            prepared[name] = data
            metadata.append((name, data, path.stat().st_mtime))
        except SaveError as exc:
            raise SaveError(f"{path}: {exc}") from exc
    prepared["sce_sys/sdslot.dat"] = make_sdslot(metadata)
    write_prepared(output, prepared)
    return output, len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save_dir", type=Path, help="decrypted PS4 export/account or SAVELIST directory")
    parser.add_argument("-o", "--output", type=Path, help="new output directory (default: <save_dir>_vita)")
    parser.add_argument("--custom-diff", choices=("enable", "disable"))
    args = parser.parse_args(argv)
    try:
        output, count = convert_directory(args.save_dir, args.output, args.custom_diff)
    except (SaveError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Converted {count} files and sce_sys/sdslot.dat to {output}")
    print("Rescue requests and retry checkpoints were reset by the existing PC-to-Vita converter.")
    print("Copy the .bin files and sce_sys/sdslot.dat into an existing decrypted Vita save.")


if __name__ == "__main__":
    main()
