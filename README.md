
# Persona 4 Golden Save Converter

A utility that converts P4G PS Vita saves to P4G PC saves:

- PS Vita `data00XX.bin` and `system.bin` files are converted to the PC format (see [FAQ](#faq) #1).
- PS Vita `sdslot.dat` file is converted to PC `data00XX.binslot` files (see [FAQ](#faq) #2).

**This tool will convert the above into proper PC `.bin`/`.binslot` files.**

**_There's no need to edit any hashes manually._**

| PS Vita                          | PC                             |
| :------------------------------: | :----------------------------: |
| ![preview](img/preview_vita.png) | ![preview](img/preview_pc.png) |

## Requirements

- PS Vita with HENkaku + VitaShell or vita-savemgr
- Persona 4 Golden on PS Vita
- Persona 4 Golden on PC
- Python 3

## Usage

### Dumping Saves

Use VitaShell or vita-savemgr to export a save. Transfer the exported save directory to PC using FTP/USB.

For example, using VitaShell:

- Navigate to `ux0:user/00/savedata/`.
- "Select" the `PCSE00120` directory.
- Press `Triangle` and select `Open decrypted`.
- Using FTP/USB, copy the saves to a directory on PC.

The directory you exported to PC should look like the following, if all save slots were populated:

```sh
PCSE00120/
|- sce_sys/
|  \- sdslot.dat
|- data0001.bin
|- data0002.bin
|- ...
|- data0016.bin
\- system.bin
```

Note that the `sce_sys` directory contains other files, but they are not relevant to the conversion process.

### Converting Saves

Clone this repository, then run:

```sh
python convert.py <save_dir>
```

Copy the converted saves in `<save_dir>_conv` to `%PROGRAMFILES(X86)%/Steam/userdata/<user_id>/1113000/remote/` and launch the game.

## FAQ

1. Why do I need to convert the saves? PS Vita saves seem to work fine without conversion.

    - The PC save format is slightly different (see [Save Format Changes](#save-format-changes). If you load a PS Vita save directly without conversion, you might get the following error:

        ![retry point error](img/retry_point.png)

        This can be avoided by converting the saves properly.

2. Why do I need to include `sdslot.dat`?

    - PS Vita saves store metadata in the `sdslot.dat` file, which can be found in `ux0:user/00/savedata/PCSE00120/sce_sys/`. PC saves store metadata in `binslot` files. This converter takes data found in `sdslot.dat` and converts it to the PC `binslot` format (see [Save Format Changes](#save-format-changes).

3. Why can't I see some of my saves in the save select screen? Why am I getting a "Load failed." message when trying to load a save?

    - The game seems to store either the max save slot you used or a flag per each save slot you've used in some config file (or in the registry). To make sure all saves will appear and will be loaded correctly, first make a dummy save in each slot, then copy over the converted saves, overwriting each `bin` and `binslot` file.

4. Why does my Clear Data save look like this? Why aren't NG+ saves colored pink/purple in the save select screen?

    ![clear data bug](img/clear_data.png)

    - This is (_probably_) caused due to a bug in the game itself. Note that the saves work as they should, the only issue is with how the save metadata is displayed. Wait for a patch.

## Save Format Changes

### Config Settings

Config settings are no longer saved in `system.bin`, instead there's a config `P4G.ini` file in `%LOCALAPPDATA%/Sega/P4G/`.

### `.bin` Files

- The *Rescue Requests* save segment increased in size (due to internal struct changes), from `0x2908` bytes (PS Vita) to `0x3FAC` bytes (PC).
- PC saves contain a new save segment (`0x30` bytes) that contains the Hero's name.
- PS Vita saves are padded to `0x38000` bytes with garbage data from Vita memory. PC saves aren't padded (`0x34D3D` bytes).

### `.binslot` Files

BINslot files are the PC alternative to `sdslot.dat`.

BINslot file structure:

```cpp
typedef struct
{
    char Magic[ 0x08 ]; // SAVE0001

    ubyte SlotFile_MD5[ 0x10 ]; // md5sum of bytes 0x28 to EOF (SlotData)
                                // *** with P4GOLDEN appended to the end ***

    ubyte SaveFile_MD5[ 0x10 ]; // md5sum of corresponding data00XX.bin or system.bin file

    ubyte SlotData[ 0x34C ]; // slot data, same as sdslot.dat data
                             // at offset 0x400 + <save_num> * 0x400
                             // save 0 == system.bin
                             // save 1 == data0001.bin
                             // etc.

} BINslot;

BINslot Slot;
```

Why append `P4GOLDEN` to the end of `SlotData` for md5sum calc?

Because ATLUS _loves_ to complicate things.

`(ノಠ益ಠ)ノ彡┻━┻`