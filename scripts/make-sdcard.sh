#!/bin/sh
dd if=/dev/zero of=sdcard.img bs=1024 count=8192
mkfs.vfat sdcard.img
mkdir -p /tmp/sdcard
sudo mount -o loop,uid=${LOGNAME} sdcard.img /tmp/sdcard
oldpwd=${PWD}
mkdir -p /tmp/sdcard/nextp8/carts
cp ../femto8-nextp8/carts/*.p8 /tmp/sdcard/nextp8/carts/
cp ../nextp8-loader/build/loader.bin /tmp/sdcard/nextp8/
cp ../femto8-nextp8/build-nextp8/femto8.bin /tmp/sdcard/nextp8/nextp8.bin
cd ${oldpwd}
sudo umount /tmp/sdcard
