"""Convert decrypted Vita P4G saves to PS4 GAME.BIN replacement files."""

import argparse
from io import BytesIO
from pathlib import Path

from console_common import discover_flat_saves, output_path, write_prepared
from convert_pc2ps4 import convert_bin as pc_to_ps4, load_templates, template_for
from convert_ps4topc import SaveError
from convert_vita2pc import conv_bin as vita_to_pc


def convert_bin(data, template, custom_diff=None):
    pc = BytesIO()
    vita_to_pc(BytesIO(data), pc, custom_diff)
    return pc_to_ps4(pc.getvalue(), template)


def conv_bin(vita_bin, ps4_bin, template, custom_diff=None):
    vita_bin.seek(0)
    data = convert_bin(vita_bin.read(), template, custom_diff)
    ps4_bin.seek(0)
    ps4_bin.write(data)
    ps4_bin.truncate()


def convert_directory(source, ps4_template, destination=None, custom_diff=None):
    source = Path(source).resolve()
    output = output_path(source, destination, "_ps4", (ps4_template,))
    files = discover_flat_saves(source)
    templates = load_templates(ps4_template)
    prepared = {}
    for name, path in sorted(files.items()):
        try:
            data = path.read_bytes()
            if name == "system.bin":
                directory = "CHANNELSAVE"
            else:
                data = convert_bin(data, template_for(templates, name), custom_diff)
                directory = "SAVELIST" + name[4:8]
            prepared[f"{directory}/GAME.BIN"] = data
        except SaveError as exc:
            raise SaveError(f"{path}: {exc}") from exc
    write_prepared(output, prepared)
    return output, len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save_dir", type=Path, help="decrypted Vita save directory")
    parser.add_argument("--ps4-template", required=True, type=Path,
                        help="decrypted PS4 export tree (matching slots), or one GAME.BIN for all slots")
    parser.add_argument("-o", "--output", type=Path, help="new output directory (default: <save_dir>_ps4)")
    parser.add_argument("--custom-diff", choices=("enable", "disable"))
    args = parser.parse_args(argv)
    try:
        output, count = convert_directory(args.save_dir, args.ps4_template, args.output, args.custom_diff)
    except (SaveError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Converted {count} files to {output}")
    print("Rescue requests and retry checkpoints were reset by the existing Vita-to-PC converter.")
    print("Replace GAME.BIN in matching decrypted PS4 exports and import them with your save manager.")
    print("PS4-only segments come from the template; console encryption/signing is not performed.")


if __name__ == "__main__":
    main()
