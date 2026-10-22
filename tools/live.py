#!/usr/bin/env python3
# Live LT/RT readout from evdev: bars, 1 s peak, events/s. Logs "t code value" to argv[2].
import os, struct, sys, time, select

dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/input/event18"
log = open(sys.argv[2] if len(sys.argv) > 2 else os.devnull, "a", buffering=1)
AX = {2: "LT", 5: "RT"}  # ABS_Z / ABS_RZ
fmt = "llHHi"
sz = struct.calcsize(fmt)
val = {c: 0 for c in AX}
peak = {c: 0 for c in AX}
cnt = {c: 0 for c in AX}
show = {c: (0, 0) for c in AX}
def find():
    # re-resolve by name: the event number can change after a reconnect
    for blk in open("/proc/bus/input/devices").read().split("\n\n"):
        if 'Name="8BitDo Ultimate 2 Wireless Controller"' in blk:
            return "/dev/input/" + next(h for h in blk.split("Handlers=")[1].split() if h.startswith("event"))
    return None

def reopen():
    while True:
        try:
            d = find() or dev
            f = os.open(d, os.O_RDONLY)
            log.write(f"{time.time():.3f} CONNECT {d}\n")
            return f
        except OSError:
            time.sleep(0.5)

fd = reopen()
last = time.time()
print("\033[2J", end="")
while True:
    try:
        buf = os.read(fd, sz * 64) if select.select([fd], [], [], 0.05)[0] else b""
    except OSError:
        os.close(fd)
        log.write(f"{time.time():.3f} DISCONNECT\n")
        print("\033[2J\033[HDISCONNECTED, waiting...", flush=True)
        fd = reopen()
        continue
    if buf:
        for i in range(0, len(buf), sz):
            _, _, typ, code, v = struct.unpack_from(fmt, buf, i)
            if typ == 3 and code in AX:
                val[code] = v
                peak[code] = max(peak[code], v)
                cnt[code] += 1
                log.write(f"{time.time():.3f} {AX[code]} {v}\n")
    out = ["\033[H"]
    for c, n in AX.items():
        bar = "#" * (val[c] * 50 // 255)
        out.append(f"{n} {val[c]:3d} |{bar:<50}| peak {show[c][0]:3d}  ev/s {show[c][1]:5d}\033[K\n")
    print("".join(out), end="", flush=True)
    if time.time() - last >= 1:
        last = time.time()
        show = {c: (peak[c], cnt[c]) for c in AX}
        peak = dict(val)
        cnt = {c: 0 for c in AX}
