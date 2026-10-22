#!/usr/bin/env python3
# Send one vendor output report (report id 0x81 first byte, padded to 64) and print replies for 0.5 s.
# usage: hidcmd.py /dev/hidrawN 81 05 00 21 01
import os, select, sys, time

fd = os.open(sys.argv[1], os.O_RDWR)
pkt = bytes(int(b, 16) for b in sys.argv[2:]).ljust(64, b"\0")
os.write(fd, pkt)
end = time.time() + 0.5
while (left := end - time.time()) > 0:
    if select.select([fd], [], [], left)[0]:
        r = os.read(fd, 64)
        if r[0] != 0x03:  # skip normal input reports, keep vendor replies
            print(r[:24].hex(" "))
