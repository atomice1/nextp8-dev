#!/usr/bin/python3

import os
import re
import struct
import subprocess
import sys

def decode_timestamp(timestamp):
    day = (timestamp >> 27) & 0x1F
    month = (timestamp >> 23) & 0x0F
    year = 2000 + ((timestamp >> 17) & 0x3F)
    hour = (timestamp >> 12) & 0x1F
    minute = (timestamp >> 6) & 0x3F
    second = timestamp & 0x3F
    return f"{year:04d}{month:02d}{day:02d}{hour:02d}{minute:02d}{second:02d}"
def make_version(kv):
    return str(kv['MAJOR_VERSION']) + '_' + str(kv['MINOR_VERSION']) + '_' + str(kv['PATCH_VERSION'])

basedir = os.path.dirname(os.path.dirname(sys.argv[0]))

parameters = {}
with open(f'{basedir}/nextp8-core/nextp8.srcs/sources_1/nextp8_top.v') as f:
    for line in f:
        line = line.strip()
        if 'parameter' in line and 'VERSION' in line and not '{' in line:
            matches = re.match("parameter +([A-Z]+_VERSION) *= *8'h([0-9a-fA-F][0-9a-fA-F]?)", line)
            if not matches:
                print(f"Parse error: {line}", file=sys.stderr)
                sys.exit(1)
            name = matches.group(1)
            value = int(matches.group(2), 16)
            parameters[name] = value
hw_version = make_version(parameters)
hw_timestamp = None
with open(f'{basedir}/nextp8-core/nextp8.runs/impl_1/nextp8.bit', "rb") as f:
    bs = f.read(4)
    while True:
        c = f.read(1)
        if len(c) == 0:
            break
        bs = bs[1:] + c
        word = struct.unpack('>I', bs)[0]
        if word == 0x3001A001:
            bs = f.read(4)
            hw_timestamp = struct.unpack('>I', bs)[0]
            break
if hw_timestamp:
    hw_timestamp = decode_timestamp(hw_timestamp)
defines = {}
with open(f'{basedir}/femto8-nextp8/src/main.c') as f:
    for line in f:
        line = line.strip()
        if 'define' in line and 'VERSION' in line:
            matches = re.match("#define +([A-Z_]+_VERSION) *([0-9][0-9]*)", line)
            if not matches:
                print(f"Parse error: {line}", file=sys.stderr)
                sys.exit(1)
            name = matches.group(1)
            value = int(matches.group(2))
            defines[name] = value
sw_version = make_version(defines)
with subprocess.Popen(['gdb-multiarch', f'{basedir}/femto8-nextp8/build-nextp8/femto8', '-quiet', '-ex', "print femto8_timestamp", '-ex', "quit"], stdout=subprocess.PIPE, encoding='utf-8') as p:
    for line in p.stdout:
        line = line.strip()
        if line.startswith('$1'):
            matches = re.match(r'\$1 = ([0-9]+)', line)
            if not matches:
                print(f"Parse error: {line}", file=sys.stderr)
                sys.exit(1)
            sw_timestamp = int(matches.group(1))
if sw_timestamp:
    sw_timestamp = decode_timestamp(sw_timestamp)
print(f'hw_{hw_version}_{hw_timestamp}_sw_{sw_version}_{sw_timestamp}')
