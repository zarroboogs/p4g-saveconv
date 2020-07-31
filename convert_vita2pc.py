

import shutil
import struct
import hashlib
import argparse
from pathlib import Path
from remotecache import write_remcache


def md5sum( stream, start=0 ):
    md5 = hashlib.md5()
    stream.seek( start, 0 )

    while True:
        data = stream.read( 1024 )
        if not data:
            break
        md5.update( data )

    stream.seek( 0, 0 )
    return md5


def conv_bin( vita_bin, pc_bin, custom_diff=None ):
    # name data
    vita_bin.seek( 0x10, 0 )
    name_p = vita_bin.read( 0x24 ) # game encoding
    vita_bin.seek( 0x64, 0 )
    name_j = vita_bin.read( 0x24 ) # sjis encoding

    vita_bin.seek( 0, 0 )

    if custom_diff:
        pc_bin.write( vita_bin.read( 0x1304 ) )
        diff = struct.unpack( "<B", vita_bin.read( 1 ) )[ 0 ]
        if custom_diff == "enable":
            pc_bin.write( struct.pack( "<B", diff | 0x03 ) )
        else:
            pc_bin.write( struct.pack( "<B", diff & ~0x03 ) )

    # same as vita upto rescue requests
    pc_bin.write( vita_bin.read( 0x15120 - vita_bin.tell() ) )

    # rescue requests segment new format
    pc_bin.write( struct.pack( "<2I", 0x0000000F, 0x00003FA4 ) ) # segment header
    pc_bin.write( struct.pack( "<2I", 0x4D16009B, 0x4D0F004D ) ) # default message
    pc_bin.write( name_p ) # name, using game encoding
    pc_bin.seek( 0x24, 1 )
    pc_bin.write( struct.pack( "<B", 1 ) )
    vita_bin.seek( 0x17A28 )
    pc_bin.seek( 0x190CC ) # zero out request data

    # next segments are the same as vita
    pc_bin.write( vita_bin.read( 0xC14 ) )

    # new pc name segment
    pc_bin.write( struct.pack( "<2II", 0x00000013, 0x00000028, 1 ) )
    pc_bin.write( name_j ) # name, sjis enc

    # ignore the retry save, but write the new save size to the retry save segment header
    pc_bin.write( struct.pack( "<2II", 0x10000001, 0x04, 0 ) )
    pc_bin.write( struct.pack( "<2II", 0x10000002, 0x04, 0 ) )
    pc_bin.write( struct.pack( "<2I", 0x10000003, 0x0001B000 ) )

    # main save checksum
    upto = pc_bin.tell()
    pc_bin.seek( 0x38, 0 )
    check = 0
    for b in pc_bin.read( upto ):
        check = ( check + b ) % 256

    pc_bin.seek( 0x34D30, 0 )
    pc_bin.write( struct.pack( "<2IBI", 0x2000, 1, check, 0xffffffff ) )


def conv_binslot( sdslot, offset, target_path, bin_path ):
    sdslot.seek( offset, 0 )

    with open( target_path, "w+b" ) as binslot:
        # magic
        binslot.write( b'SAVE0001' )

        # corresponding .bin md5sum
        with open( bin_path, "rb" ) as bin:
            bin_md5sum = md5sum( bin )
        binslot.seek( 0x18, 0 )
        binslot.write( bin_md5sum.digest() )

        binslot.write( sdslot.read( 0xC4 ) )

        # slot data + lang
        contents = sdslot.read( 0xC4 )
        contents = contents.replace( b"\nTimes ", b"\nLANG1\nTimes " )
        binslot.write( contents )
        binslot.seek( 0xC4 - len( contents ), 1 )

        binslot.write( sdslot.read( 0x34C - 2 * 0xC4 ) )

        # slot data md5sum
        # md5sum of bytes 0x28 to EOF
        # *** with P4GOLDEN appended to the end ***
        slot_md5sum = md5sum( binslot, 0x28 )
        slot_md5sum.update( "P4GOLDEN".encode() )
        binslot.seek( 0x08, 0 )
        binslot.write( slot_md5sum.digest() )


def convert_data( dir_in, dir_out, do_convert=True, custom_diff=None ):
    # system.bin has the same format
    system_in = dir_in / "system.bin"
    system_out = dir_out / "system.bin"

    if system_in.exists():
        shutil.copy( system_in, system_out )
        print( "  copied system.bin" )

    # convert saves first
    for vita_path in dir_in.glob( 'data*.bin' ):
        pc_path = dir_out / vita_path.name

        if do_convert:
            with open( vita_path, "rb" ) as vita_bin, open( pc_path, "w+b" ) as pc_bin:
                conv_bin( vita_bin, pc_bin, custom_diff )
            print( f"  converted {vita_path}" )
        else:
            shutil.copy( vita_path, pc_path )
            print( f"  copied {vita_path}" )


def convert_sdslot( sdslot_path, dir_out ):
    with open( sdslot_path, "rb" ) as sdslot:
        sdslot.seek( 0x200 )
        active_slots = struct.unpack( "<17B", sdslot.read( 17 ) )

        # system.binslot
        bin_path = dir_out / "system.bin"
        binslot_path = f"{bin_path}slot"
        if bin_path.exists():
            conv_binslot( sdslot, 0x400, binslot_path, bin_path )
            print( f"  generated {binslot_path}" )

        # dataXXXX.binslot
        for i in range( 1, 17 ):
            if active_slots[ i ]:
                bin_path = dir_out / f"data00{i:02}.bin"
                binslot_path = f"{bin_path}slot"
                if bin_path.exists():
                    conv_binslot( sdslot, 0x400 + i * 0x400, binslot_path, bin_path )
                    print( f"  generated {binslot_path}" )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument( "--custom-diff", choices={ "enable", "disable" }, help="toggle custom diff menu" )
    parser.add_argument( "save_dir", nargs=1, help="vita save dir" )
    args = parser.parse_args()

    save_path = Path( args.save_dir[0] )
    sdslot_path = save_path / "sce_sys/sdslot.dat"

    if not save_path.is_dir():
        raise Exception( "missing save dir or save dir doesn't exist" )
    print( f"converting save dir {save_path}" )

    if not sdslot_path.exists():
        raise Exception( f"{sdslot_path} not found" )
    print( f"using {sdslot_path} from save dir" )

    files = [ f for f in save_path.glob( "data*.binslot" ) if f.is_file() ]
    if len( files ) != 0:
        raise Exception( "input dir already contain pc saves" )

    dir_out = Path( f"{save_path}_conv" )
    dir_out.mkdir( exist_ok=True )
    print( f"using output dir {dir_out}" )

    print( f"converting saves" )
    convert_data( save_path, dir_out, custom_diff=args.custom_diff )
    print( f"converting sdslot" )
    convert_sdslot( sdslot_path, dir_out )

    print( "generating remotecache.vdf" )
    remcache_path = Path ( dir_out.parent / "remotecache.vdf" )
    write_remcache( remcache_path, dir_out )

    print( "done!" )


if __name__ == "__main__":
    main()

