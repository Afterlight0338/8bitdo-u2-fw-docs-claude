#!/usr/bin/env python3
# Resolve auipc+jalr far calls in a rizin listing of the CH32 app.
# RAM code is stored at flash 0x3100..0x3100+hclen and runs at 0x20000000.
# usage: farcalls.py dis.txt hclen [target_hex]
import re, sys
lines = open(sys.argv[1]).read().splitlines()
hclen = int(sys.argv[2], 16)
want = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
rx = re.compile(r'^0x([0-9a-f]+)\s+[0-9a-f]+\s+(\S+)\s+(.*)$')
prev = None
for l in lines:
    m = rx.match(l)
    if not m: continue
    a, op, args = int(m[1], 16), m[2], m[3]
    if op == 'auipc':
        r, imm = [x.strip() for x in args.split(',')]
        prev = (a, r, int(imm, 16))
        continue
    if prev and op in ('jalr', 'jr') and prev[1] in args:
        off = int(re.search(r'(-?\d+)\(', args)[1])
        pa, _, imm = prev
        pc = 0x20000000 + pa - 0x3100 if 0x3100 <= pa < 0x3100 + hclen else pa
        t = (pc + (imm << 12) + off) & 0xffffffff
        if t >= 0x20000000 and t < 0x20000000 + hclen:
            t_flash = t - 0x20000000 + 0x3100
            tag = f"{t:#x} (flash {t_flash:#x})"
        else:
            t_flash, tag = t, f"{t:#x}"
        if want is None or want in (t, t_flash):
            print(f"{pa:#x}: call {tag}")
    prev = None
