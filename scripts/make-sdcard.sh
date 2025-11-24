#!/bin/sh
scriptdir="$(dirname "$0")"
basedir="$(dirname "${scriptdir}")"
zipfile="$(mktemp --suffix=.zip)"
mountpoint="$(mktemp -d)"
"${scriptdir}"/make-release.sh "${zipfile}" --no-bitstream
ls "${zipfile}"
dd if=/dev/zero of=sdcard.img bs=1024 count=8192
mkfs.vfat sdcard.img
mkdir -p "${mountpoint}"
sudo mount -o loop,uid="${LOGNAME}" sdcard.img "${mountpoint}"
abszipfile="$(readlink -f "${zipfile}")"
oldpwd="${PWD}"
cd "${mountpoint}"
unzip "${zipfile}"
cd "${oldpwd}"
cp "${basedir}"/femto8-nextp8/carts/*.p8 "${mountpoint}"/machines/nextp8/carts/
sudo umount "${mountpoint}"
rm "${zipfile}"
rmdir "${mountpoint}"
