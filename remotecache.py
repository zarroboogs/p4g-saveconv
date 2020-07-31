

import os
import math
import hashlib
import argparse
from pathlib import Path


def sha1sum( stream, start=0 ):
    sha1 = hashlib.sha1()
    stream.seek( start, 0 )

    while True:
        data = stream.read( 1024 )
        if not data:
            break
        sha1.update( data )

    stream.seek( 0, 0 )
    return sha1


def vdf_write( vdf, level, key="", val=None ):
    pad = '\t' * level
    if key == None or key == "":
        vdf.write( f'{pad}' + "}\n" )
    elif val == None:
        vdf.write( f'{pad}"{key}"\n{pad}' + "{\n" )
    else:
        vdf.write( f'{pad}"{key}"\t\t"{val}"\n' )


def write_remcache_file( vdf, filepath ):
    fstat = os.stat( filepath )
    fsize = fstat.st_size
    ftime = math.floor( fstat.st_mtime )

    with open( filepath, "rb" ) as fs:
        fsha = sha1sum( fs ).hexdigest()

    vdf_write( vdf, 1, filepath.name )
    vdf_write( vdf, 2, "root", 0 )
    vdf_write( vdf, 2, "size", fsize )
    vdf_write( vdf, 2, "localtime", ftime )
    vdf_write( vdf, 2, "time", ftime )
    vdf_write( vdf, 2, "remotetime", ftime )
    vdf_write( vdf, 2, "sha", fsha )
    vdf_write( vdf, 2, "syncstate", 4 )
    vdf_write( vdf, 2, "persiststate", 0 )
    vdf_write( vdf, 2, "platformstosync2", -1 )
    vdf_write( vdf, 1 )


def write_remcache( remcache_path, data_path ):
    with open( remcache_path, "w", newline='\n' ) as vdf:
        vdf_write( vdf, 0, "1113000" )

        for f in data_path.glob( "system.bin" ):
            write_remcache_file( vdf, f )
            write_remcache_file( vdf, Path( f"{f}slot" ) )

        for f in data_path.glob( "data*.bin" ):
            write_remcache_file( vdf, f )
            write_remcache_file( vdf, Path( f"{f}slot" ) )

        vdf_write( vdf, 0 )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument( "save_dir", nargs=1, help="pc save dir" )
    args = parser.parse_args()

    save_path = Path( args.save_dir[ 0 ] )

    if not save_path.is_dir():
        raise Exception( "missing save dir or save dir doesn't exist" )

    files = [ f for f in save_path.glob( "data*.binslot" ) if f.is_file() ]
    if len( files ) == 0:
        raise Exception( "input dir doesn't contain pc saves" )

    print( "generating remotecache.vdf" )
    remcache_path = Path ( save_path.parent / "remotecache.vdf" )
    write_remcache( remcache_path, save_path )

    print( "done!" )


if __name__ == "__main__":
    main()

