#!/usr/bin/env python3
# Poll the DIAG firmware's telemetry byte (reply byte 18 of `81 04 41 00`) and decode frames:
# FF, LT hi7, LT lo7, RT hi7, RT lo7, LX hi7, LX lo7 -> raw table values (>>1, so x2 to restore).
# usage: telem.py /dev/hidrawN seconds out.log      (log lines: "t LT RT LX" in raw-table units)
import os, select, sys, time

fd = os.open(sys.argv[1], os.O_RDWR)
end = time.time() + float(sys.argv[2])
out = open(sys.argv[3], "w", buffering=1)
req = bytes([0x81, 0x04, 0x41, 0x00]).ljust(64, b"\0")
frame, polls, frames = None, 0, 0
while time.time() < end:
    os.write(fd, req)
    polls += 1
    t_wait = time.time() + 0.1
    b = None
    while (left := t_wait - time.time()) > 0 and select.select([fd], [], [], left)[0]:
        r = os.read(fd, 64)
        if r[0] == 0x02 and r[1] == 0x04 and r[4] == 0x41:
            b = r[18]; break
    if b is None: continue
    if b == 0xFF:
        frame = []
    elif frame is not None:
        frame.append(b)
        if len(frame) == 6:
            v = [((frame[i] << 7) | frame[i + 1]) * 2 for i in (0, 2, 4)]
            out.write(f"{time.time():.3f} {v[0]} {v[1]} {v[2]}\n")
            frames += 1
            frame = None
print(f"{polls} polls, {frames} frames, {frames / float(sys.argv[2]):.1f} frames/s")
