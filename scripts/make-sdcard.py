#!/usr/bin/env python3
"""
Create an SD card image for nextp8.

This script creates a FAT filesystem image in user space using pyfatfs,
populates it with the nextp8 release files, and optionally copies
carts from specified directories.

Requirements:
    - pyfatfs: pip install pyfatfs

Usage:
    make-sdcard.py [OPTIONS]

Options:
    -o, --output FILE          Output image file (default: sdcard.img)
    -s, --size MB              Size of image in MB or 'auto' to calculate (default: auto)
    -c, --cart-dir DIR         Directory containing .p8 carts to copy (can be specified multiple times)
    --no-bitstream             Skip including the bitstream in the release
    -h, --help                 Show this help message
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    from pyfatfs.PyFatFS import PyFatFS
    from pyfatfs.PyFat import PyFat
    from pyfatfs.FATDirectoryEntry import FATDirectoryEntry
except ImportError:
    print("Error: pyfatfs module not found. Install it with:", file=sys.stderr)
    print("  pip install pyfatfs", file=sys.stderr)
    sys.exit(1)


def get_script_dir():
    """Get the directory containing this script."""
    return Path(__file__).parent.absolute()


def get_base_dir():
    """Get the base directory of the project."""
    return get_script_dir().parent


def create_release_zip(output_zip, no_bitstream=False):
    """
    Create a release zip file by calling make-release.sh.

    Args:
        output_zip: Path to output zip file
        no_bitstream: If True, skip including the bitstream

    Returns:
        Path to the created zip file
    """
    script_dir = get_script_dir()
    make_release_script = script_dir / "make-release.sh"

    if not make_release_script.exists():
        raise FileNotFoundError(f"make-release.sh not found at {make_release_script}")

    cmd = [str(make_release_script), str(output_zip)]
    if no_bitstream:
        cmd.append("--no-bitstream")

    print(f"Creating release zip: {output_zip}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error creating release: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    return output_zip


def create_fat_image(image_path, size_mb):
    """
    Create an empty FAT filesystem image.

    Args:
        image_path: Path to the image file to create
        size_mb: Size of the image in megabytes
    """
    size_bytes = size_mb * 1024 * 1024

    if size_mb < 16:
        fat_type = PyFat.FAT_TYPE_FAT12
        fat_name = "FAT12"
    elif size_mb < 512:
        fat_type = PyFat.FAT_TYPE_FAT16
        fat_name = "FAT16"
    else:
        fat_type = PyFat.FAT_TYPE_FAT32
        fat_name = "FAT32"

    print(f"Creating {size_mb}MB {fat_name} image: {image_path}")

    with open(image_path, 'wb') as f:
        f.truncate(size_bytes)

    fs = PyFat()
    fs.mkfs(
        str(image_path),
        fat_type=fat_type,
        size=size_bytes,
        label="NEXTP8"
    )
    fs.close()

    with open(image_path, 'r+b') as f:
        f.seek(0x16)  # Offset to sectors per FAT
        sectors_per_fat = int.from_bytes(f.read(2), 'little')

        # Fix CHS geometry - use common SD card values
        f.seek(0x18)  # sectors/track
        f.write(b'\x20\x00')  # 32 sectors/track
        f.seek(0x1A)  # heads
        f.write(b'\x40\x00')  # 64 heads

        # Fix FAT initialization (both copies) based on FAT type
        if fat_type == PyFat.FAT_TYPE_FAT12:
            fat_init = b'\xf8\xff\xff'
        elif fat_type == PyFat.FAT_TYPE_FAT16:
            fat_init = b'\xf8\xff\xff\xff'
        else:  # FAT32
            fat_init = b'\xf8\xff\xff\x0f\xff\xff\xff\x0f'

        fat1_offset = 0x200  # First FAT starts after boot sector
        fat2_offset = fat1_offset + (sectors_per_fat * 512)  # Second FAT

        for fat_offset in [fat1_offset, fat2_offset]:
            f.seek(fat_offset)
            f.write(fat_init)


def copy_directory_recursive(fs, src_path, dest_path=""):
    """
    Recursively copy a directory into the FAT filesystem.

    Args:
        fs: PyFatFS filesystem object
        src_path: Source directory path (on host)
        dest_path: Destination path in the FAT filesystem
    """
    src = Path(src_path)

    if not src.exists():
        print(f"Warning: Source directory does not exist: {src_path}", file=sys.stderr)
        return

    for item in src.iterdir():
        if item.is_file():
            dest_file = f"{dest_path}/{item.name}" if dest_path else item.name
            print(f"  Copying: {item.name} -> {dest_file}")

            with open(item, 'rb') as f:
                data = f.read()

            try:
                with fs.open(dest_file, 'wb') as fat_file:
                    fat_file.write(data)
            except Exception as e:
                print(f"  Warning: Could not copy {item.name}: {e}", file=sys.stderr)

        elif item.is_dir():
            dest_dir = f"{dest_path}/{item.name}" if dest_path else item.name
            print(f"  Creating directory: {dest_dir}")

            try:
                fs.makedirs(dest_dir, recreate=True)
            except Exception as e:
                print(f"  Warning: Could not create directory {dest_dir}: {e}", file=sys.stderr)
                continue

            copy_directory_recursive(fs, item, dest_dir)


def extract_zip_to_fat(fs, zip_path):
    """
    Extract a zip file into the FAT filesystem.

    Args:
        fs: PyFatFS filesystem object
        zip_path: Path to the zip file to extract
    """
    print(f"Extracting {zip_path} to FAT image...")

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.namelist():
            if member.endswith('/'):
                continue

            parts = member.split('/')
            if len(parts) > 1:
                dir_path = '/'.join(parts[:-1])
                try:
                    fs.makedirs(dir_path, recreate=True)
                except:
                    pass

            print(f"  Extracting: {member}")
            data = zf.read(member)

            try:
                with fs.open(member, 'wb') as fat_file:
                    fat_file.write(data)
            except Exception as e:
                print(f"  Warning: Could not extract {member}: {e}", file=sys.stderr)


def copy_carts_to_fat(fs, cart_dirs):
    """
    Copy cart files to the FAT filesystem.

    Args:
        fs: PyFatFS filesystem object
        cart_dirs: List of directories containing .p8 cart files
    """
    if not cart_dirs:
        return

    carts_path = "machines/nextp8/carts"
    try:
        fs.makedirs(carts_path, recreate=True)
    except:
        pass

    print(f"Copying carts to {carts_path}...")

    for cart_dir in cart_dirs:
        cart_dir_path = Path(cart_dir)

        if not cart_dir_path.exists():
            print(f"Warning: Cart directory does not exist: {cart_dir}", file=sys.stderr)
            continue

        if not cart_dir_path.is_dir():
            print(f"Warning: Not a directory: {cart_dir}", file=sys.stderr)
            continue

        for cart_file in cart_dir_path.glob("*.p8"):
            dest_file = f"{carts_path}/{cart_file.name}"

            try:
                if fs.exists(dest_file):
                    continue
            except:
                pass

            print(f"  Copying: {cart_file.name}")

            with open(cart_file, 'rb') as f:
                data = f.read()

            try:
                with fs.open(dest_file, 'wb') as fat_file:
                    fat_file.write(data)
            except Exception as e:
                print(f"  Warning: Could not copy {cart_file.name}: {e}", file=sys.stderr)


def calculate_required_size(zip_path, cart_dirs):
    """
    Calculate the required size for the image in MB.

    Args:
        zip_path: Path to the release zip file
        cart_dirs: List of directories containing .p8 cart files

    Returns:
        Size in MB (rounded up to nearest MB, with 10% overhead for FAT filesystem)
    """
    total_bytes = 0

    if Path(zip_path).exists():
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                total_bytes += info.file_size

    if cart_dirs:
        for cart_dir in cart_dirs:
            cart_dir_path = Path(cart_dir)
            if cart_dir_path.exists() and cart_dir_path.is_dir():
                for cart_file in cart_dir_path.glob("*.p8"):
                    if cart_file.is_file():
                        total_bytes += cart_file.stat().st_size

    size_mb = (total_bytes * 1.1) / (1024 * 1024)

    size_mb = max(2, int(size_mb + 0.999))

    return size_mb


def main():
    parser = argparse.ArgumentParser(
        description="Create an SD card image for nextp8 without requiring sudo.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-o', '--output',
        default='sdcard.img',
        help='Output image file (default: sdcard.img)'
    )

    parser.add_argument(
        '-s', '--size',
        default='auto',
        help='Size of image in MB or "auto" to calculate (default: auto)'
    )

    parser.add_argument(
        '-c', '--cart-dir',
        action='append',
        dest='cart_dirs',
        help='Directory containing .p8 carts to copy (can be specified multiple times)'
    )

    parser.add_argument(
        '--no-bitstream',
        action='store_true',
        help='Skip including the bitstream in the release'
    )

    parser.add_argument(
        '-z', '--release-zip',
        help='Use existing release zip instead of creating one'
    )

    args = parser.parse_args()

    if args.release_zip:
        zip_path = args.release_zip
        cleanup_zip = False
    else:
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
            zip_path = tmp_zip.name
        cleanup_zip = True

    try:
        if not args.release_zip:
            create_release_zip(zip_path, args.no_bitstream)

        if args.size == 'auto':
            size_mb = calculate_required_size(zip_path, args.cart_dirs)
            print(f"Calculated required size: {size_mb}MB")
        else:
            try:
                size_mb = int(args.size)
            except ValueError:
                print(f"Error: Invalid size '{args.size}'. Must be a number or 'auto'.", file=sys.stderr)
                sys.exit(1)

        image_path = Path(args.output).absolute()
        create_fat_image(image_path, size_mb)

        print(f"Populating FAT image...")
        with PyFatFS(str(image_path)) as fs:
            extract_zip_to_fat(fs, zip_path)

            if args.cart_dirs:
                copy_carts_to_fat(fs, args.cart_dirs)

        print(f"\nSD card image created successfully: {args.output}")
        print(f"Size: {size_mb}MB")

        if args.cart_dirs:
            print(f"Cart directories included: {', '.join(args.cart_dirs)}")

    finally:
        if cleanup_zip and Path(zip_path).exists():
            Path(zip_path).unlink()


if __name__ == '__main__':
    main()
