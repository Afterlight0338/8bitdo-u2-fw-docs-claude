#!/usr/bin/env python3
# Poll DIAG2 firmware: frame = FF + 168 samples (84 LT DMA samples, then 84 RT), each hi7,lo7.
# usage: telem2.py /dev/hidrawN seconds out.log   (log line: "t s0 s1 ... s167" raw 12-bit ADC)
import os, select, sys, time

fd = os.open(sys.argv[1], os.O_RDWR)
end = time.time() + float(sys.argv[2])
out = open(sys.argv[3], "w", buffering=1)
req = bytes([0x81, 0x04, 0x41, 0x00]).ljust(64, b"\0")
frame, frames = None, 0
while time.time() < end:
    os.write(fd, req)
    t_wait, b = time.time() + 0.1, None
    while (left := t_wait - time.time()) > 0 and select.select([fd], [], [], left)[0]:
        r = os.read(fd, 64)
        if r[0] == 0x02 and r[1] == 0x04 and r[4] == 0x41:
            b = r[18]; break
    if b is None: continue
    if b == 0xFF:
        frame = []
    elif frame is not None:
        frame.append(b)
        if len(frame) == 336:
            v = [(frame[i] << 7) | frame[i + 1] for i in range(0, 336, 2)]
            out.write(f"{time.time():.3f} " + " ".join(map(str, v)) + "\n")
            frames += 1
            frame = None
print(f"{frames} snapshots")
