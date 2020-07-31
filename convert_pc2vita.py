

import shutil
import struct
import hashlib
import argparse
from pathlib import Path


def conv_bin( pc_bin, vita_bin, custom_diff=None ):
    # name data
    pc_bin.seek( 0x10, 0 )
    name_p = pc_bin.read( 0x24 ) # game encoding

    pc_bin.seek( 0, 0 )

    if custom_diff:
        vita_bin.write( pc_bin.read( 0x1304 ) )
        diff = struct.unpack( "<B", pc_bin.read( 1 ) )[ 0 ]
        if custom_diff == "enable":
            vita_bin.write( struct.pack( "<B", diff | 0x03 ) )
        else:
            vita_bin.write( struct.pack( "<B", diff & ~0x03 ) )

    # same as vita upto rescue requests
    vita_bin.write( pc_bin.read( 0x15120 - pc_bin.tell() ) )

    # rescue requests segment new format
    vita_bin.write( struct.pack( "<2I", 0x0000000F, 0x00002900 ) ) # segment header
    vita_bin.write( struct.pack( "<2I", 0x4D16009B, 0x4D0F004D ) ) # default message
    vita_bin.write( name_p ) # name, using game encoding

    vita_bin.write( struct.pack( "<B", 1 ) )
    pc_bin.seek( 0x190CC )
    vita_bin.seek( 0x17A28 ) # zero out request data

    # next segments are the same as vita
    vita_bin.write( pc_bin.read( 0xC14 ) )

    # new pc name segment
    pc_bin.seek( 0x30, 1 )

    # ignore the retry save, but write the new save size to the retry save segment header
    vita_bin.write( struct.pack( "<2II", 0x10000001, 0x04, 0 ) )
    vita_bin.write( struct.pack( "<2II", 0x10000002, 0x04, 0 ) )
    vita_bin.write( struct.pack( "<2I", 0x10000003, 0x00019000 ) )

    # main save checksum
    upto = vita_bin.tell()
    vita_bin.seek( 0x38, 0 )
    check = 0
    for b in vita_bin.read( upto ):
        check = ( check + b ) % 256

    vita_bin.seek( 0x3165C, 0 )
    vita_bin.write( struct.pack( "<2IBI", 0x2000, 1, check, 0xffffffff ) )

    vita_bin.write( bytearray( [ 0 ] * ( 0x38000 - vita_bin.tell() ) ) )


def conv_binslot( sdslot, offset, binslot_path ):
    sdslot.seek( offset, 0 )

    with open( binslot_path, "r+b" ) as binslot:
        binslot.seek( 0x28, 0 )

        sdslot.write( binslot.read( 0xC4 ) )

        # slot data + lang
        contents = binslot.read( 0xC4 )
        contents = contents.replace( b"\nLANG1\nTimes ", b"\nTimes " )
        sdslot.write( contents )
        sdslot.seek( 0xC4 - len( contents ), 1 )

        sdslot.write( binslot.read( 0x34C - 2 * 0xC4 ) )
        sdslot.write( bytearray( [ 0 ] * ( 0x400 - 0x34C ) ) )


def convert_data( dir_in, dir_out, do_convert=True, custom_diff=None ):
    # system.bin has the same format
    system_in = dir_in / "system.bin"
    system_out = dir_out / "system.bin"
    binslot_path = binslot_path = Path( f"{system_in}slot" )

    if not binslot_path.exists():
        print( f"  missing binslot for {system_in}, skipping..." )
    elif system_in.exists():
        shutil.copy( system_in, system_out )
        print( "  copied system.bin" )

    # convert saves first
    for pc_path in dir_in.glob( "data*.bin" ):
        vita_path = dir_out / pc_path.name

        # only convert saves that have metadata
        binslot_path = Path( f"{pc_path}slot" )
        if not binslot_path.exists():
            print( f"  missing binslot for {pc_path}, skipping..." )
            continue

        if do_convert:
            with open( vita_path, "w+b" ) as vita_bin, open( pc_path, "rb" ) as pc_bin:
                conv_bin( pc_bin, vita_bin, custom_diff )
            print( f"  converted {pc_path}" )
        else:
            shutil.copy( pc_path, vita_path )
            print( f"  copied {pc_path}" )


def convert_sdslot( sdslot_path, dir_in ):
    with open( sdslot_path, "wb" ) as sdslot:
        active_slots = [ 0 ] * 17

        sdslot.write( b"SDSL" )
        sdslot.seek( 9, 0 )
        sdslot.write( struct.pack( "<1B", 1 ) )

        # system.binslot
        bin_path = dir_in / "system.bin"
        binslot_path = Path( f"{bin_path}slot" )
        if bin_path.exists() and binslot_path.exists():
            conv_binslot( sdslot, 0x400, binslot_path )
            print( f"  merged {binslot_path}" )
            active_slots[ 0 ] = 1

        # dataXXXX.binslot
        for i in range( 1, 17 ):
            bin_path = dir_in / f"data00{i:02}.bin"
            binslot_path = Path( f"{bin_path}slot" )
            if bin_path.exists() and binslot_path.exists():
                conv_binslot( sdslot, 0x400 + i * 0x400, binslot_path )
                print( f"  merged {binslot_path}" )
                active_slots[ i ] = 1

        sdslot.write( bytearray( [ 0 ] * ( 0x40400 - sdslot.tell() ) ) )

        sdslot.seek( 0x200 )
        sdslot.write( struct.pack ( "<17B", *active_slots ) )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument( "--custom-diff", choices={ "enable", "disable" }, help="toggle custom diff menu" )
    parser.add_argument( "save_dir", nargs=1, help="vita save dir" )
    args = parser.parse_args()

    save_path = Path( args.save_dir[0] )

    if not save_path.is_dir():
        raise Exception( "missing save dir or save dir doesn't exist" )
    print( f"converting save dir {save_path}" )

    if ( save_path / "sce_sys/sdslot.dat" ).is_file():
        raise Exception( "input dir already contains vita saves" )

    dir_out = Path( f"{save_path}_conv" )
    dir_out.mkdir( exist_ok=True )
    print( f"using output dir {dir_out}" )

    sdslot_path = dir_out / "sce_sys/sdslot.dat"
    sdslot_path.parent.mkdir( parents=True, exist_ok=True )

    print( f"converting saves" )
    convert_data( save_path, dir_out, custom_diff=args.custom_diff )
    print( f"converting sdslot" )
    convert_sdslot( sdslot_path, save_path )

    print( "done!" )


if __name__ == "__main__":
    main()

