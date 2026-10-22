#!/usr/bin/env python3
# Local flasher for the 8BitDo bootloader (USB 2dc8:3208 "8BitDo Boot"), reimplemented from
# web.8bitdo.com's p_connectDevice-*.js boot-mode path (functions w/E/K/Pt/Ye/Le).
# usage: bootflash.py /dev/hidrawN probe              (boot device, 2dc8:3208)
#        bootflash.py /dev/hidrawN flash file.dat [--no-reset]
#        bootflash.py /dev/hidrawN reset              (boot -> normal firmware)
#        bootflash.py /dev/hidrawN jump               (vendor iface of the RUNNING controller -> bootloader)
# Notes: the SAVE cmd (196) never gets a reply on this bootloader (that is where the website hangs
# and reports "update failed"); a plain RESET boots the written image fine, so flash skips SAVE.
import os, select, struct, sys, time

ERASE, WRITE, READ, READ_PID, RESET, READ_CRC, SAVE = 4, 3, 5, 8, 7, 195, 196
CHUNK = 46  # bytes per write packet, as the web updater uses
BL_END = 0x5000  # bootloader lives below this; never erase/write it

def crc16(d):  # web updater Z(): CRC-16/MODBUS
    c = 0xffff
    for x in d:
        c ^= x
        for _ in range(8): c = (c >> 1) ^ (0xa001 if c & 1 else 0)
    return c

class Boot:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR)

    def drain(self):
        while select.select([self.fd], [], [], 0)[0]: os.read(self.fd, 64)

    def cmd(self, cmd, params=0, data=b"", total=0, offset=0, length=None, timeout=3.0, wait=True):
        length = len(data) if length is None else length
        if cmd in (ERASE, WRITE):  # hard guard: the bootloader is the only recovery path
            assert offset >= BL_END, f"refusing cmd {cmd} at {offset:#x}: inside bootloader (<{BL_END:#x})"
        pkt = struct.pack("<BHHHHII", 5, cmd, params, length, crc16(data) if data else 0, total, offset) + data
        self.drain()
        os.write(self.fd, b"\0" + pkt.ljust(64, b"\0"))  # report id 0 + 64-byte report
        if not wait: return None
        if not select.select([self.fd], [], [], timeout)[0]:
            raise TimeoutError(f"no reply to cmd {cmd} @ {offset:#x}")
        r = os.read(self.fd, 64)
        rcmd, rparams = struct.unpack_from("<HH", r, 2)
        return r, rcmd, rparams

    def ok(self, cmd, **kw):  # success = reply cmd field 0 with params echoing our cmd
        for attempt in range(4):
            try:
                r, rcmd, rparams = self.cmd(cmd, **kw)
            except TimeoutError as e:
                print(" ", e, "- retry"); continue
            if rcmd == 0 and rparams == cmd: return r
            raise RuntimeError(f"cmd {cmd} failed: {r[:24].hex(' ')}")
        raise RuntimeError(f"cmd {cmd} timed out 4x")

def main():
    dev, op = sys.argv[1], sys.argv[2]
    b = Boot(dev)
    if op == "probe":
        r, rc, rp = b.cmd(READ_PID, length=4, total=4, timeout=1.0)
        print("reply:", r[:32].hex(" "), f"| cmd={rc} params={rp} u32@18={struct.unpack_from('<I', r, 18)[0]:#x}")
        return
    if op == "jump":  # app-mode vendor report 0x81: cmd 0x5100 sets analog reg 0x3c=0x5a and reboots
        os.write(b.fd, bytes([0x81, 5, 0, 0x51, 0]).ljust(64, b"\0")); print("jump sent"); return
    if op == "reset":
        b.cmd(RESET, wait=False); print("reset sent"); return
    dat = open(sys.argv[3], "rb").read()
    ver, addr, size, pid = struct.unpack_from("<IIII", dat, 0)
    img = dat[28:28 + size]
    assert len(img) == size, "truncated .dat"
    print(f"file: version {ver:#x}, addr {addr:#x}, size {size:#x}, pid {pid:#x}")
    r, rc, rp = b.cmd(READ_PID, length=4, total=4, timeout=1.0)
    devpid = struct.unpack_from("<I", r, 18)[0]
    print(f"device pid {devpid:#x}")
    assert devpid & 0xffff == pid & 0xffff, "PID mismatch, refusing to flash"
    print("erasing..."); b.ok(ERASE, total=size, offset=addr, timeout=10.0)
    t0 = time.time()
    for n in range(0, size, CHUNK):
        part = img[n:n + CHUNK]
        b.ok(WRITE, data=part, total=size, offset=addr + n)
        if n % 0x2000 < CHUNK: print(f"  wrote {n:#07x}/{size:#x}  {time.time()-t0:.0f}s", flush=True)
    print("verifying by readback...")
    back = bytearray()
    for n in range(0, size, 32):
        back += b.ok(READ, length=32, total=32, offset=addr + n)[18:50]
    bad = sum(x != y for x, y in zip(back[:size], img))
    print("verify:", "OK" if not bad else f"{bad} bytes differ")
    if bad: sys.exit(1)
    if "--no-reset" not in sys.argv:
        b.cmd(RESET, wait=False); print("reset sent")

if __name__ == "__main__":
    main()
