#!/usr/bin/env python3
# Patch the CH32 co-processor part of 8BitDo's Ultimate 2 Wireless 1.10 update (.dat).
# THE FIX (ADC clock 12 -> 6 MHz, nothing else):
#   patch_ch32.py u2w_1.10.dat u2w_1.10_adcfix.dat --adcdiv 8 --adc-only
# Needs llvm-mc/llvm-objcopy: nix-shell -p llvm python3
#
# Everything below is the earlier experiments, kept so the README's numbers can be rebuilt:
#   patch_ch32.py in.dat out.dat [T] [N] [DZ] [--diag [--diag2]] [--adcdiv N]
#   T = jump size (0..1023 units) that counts as a glitch, N = samples a jump must persist,
#   DZ = rest deadzone in scaled units (one bad ADC sample ~ 25.6), rest rescaled to 0..1023.
# Filter, per trigger (axis 4 = LT, 5 = RT), on the 0..1023 value from scale() @0x5920:
#   |x - out| <= T  -> accept x immediately (normal motion, no lag)
#   bigger jump     -> only accept once it persisted N calls in a row, else keep out
# State: 4 bytes per trigger at 0x20004700 (u16 out, u8 cnt), between heap and stack.
import os, struct, subprocess, sys, tempfile

src, dst = sys.argv[1], sys.argv[2]
nums = [int(a) for a in sys.argv[3:6] if a.isdigit()]
T, N, DZ = (nums + [32, 24, 0][len(nums):])[:3]
DIAG = "--diag" in sys.argv
# --adcdiv N: ADC clock = 48 MHz / N instead of the stock /4 (ADC CTLR3 @0x50, WCH SDK encoding
# ADC_CLK_DivN = ((N-1)>>1)<<4 | (N-1), stock 0x13). Stock top-bit SAR errors (raw 0x800 / 0x3FF)
# were measured at /4; see the README.
ADCDIV = int(sys.argv[sys.argv.index("--adcdiv") + 1]) if "--adcdiv" in sys.argv else 0
ADC_CLK_CALL = 0x6cd6   # c.li a1,19 ; jal ra,0x9940 (ADC_CLKConfig)
assert 0 <= DZ < 1023

BLOB = 28 + 0x17a68          # CH32 app offset inside the .dat (1.10)
BASE = 0x3000                # CH32 app load address
HC_FLASH, HC_LEN = 0x3100, 0x1a04   # RAM code stored here, runs at 0x20000000
CAVE = 0xec60                # zero padding after .data init (0xec44..0xed98)
SCALE, GET_RGB = 0x5920, 0x8a0c
LT_CALL, RT_CALL, RGB_CALL = 0x3a06, 0x3a12, 0x4862

def run_pc(flash):           # address the instruction executes at
    return 0x20000000 + flash - HC_FLASH if HC_FLASH <= flash < HC_FLASH + HC_LEN else flash

# filter at CAVE (jal at +16), marker stub after it; no compressed instrs so offsets are fixed
asm = f"""
filt:
  addi sp, sp, -16
  sw   ra, 12(sp)
  sw   s0, 8(sp)
  mv   s0, a0
  jal  ra, {SCALE - (CAVE + 16)}
  li   a3, {DZ}
  bltu a0, a3, dz0
  sub  a0, a0, a3
  li   a3, 1023
  mul  a0, a0, a3
  li   a3, {1023 - DZ}
  divu a0, a0, a3
  j    dzok
dz0:
  li   a0, 0
dzok:
  lui  a5, 0x20004
  addi a5, a5, 0x700
  addi a4, s0, -4
  slli a4, a4, 2
  add  a5, a5, a4
  lhu  a4, 0(a5)
  li   a3, 1023
  bltu a3, a4, accept
  sub  a3, a0, a4
  bgez a3, 1f
  neg  a3, a3
1:
  li   a2, {T}
  bgeu a2, a3, accept
  lbu  a3, 2(a5)
  addi a3, a3, 1
  li   a2, {N}
  bgeu a3, a2, accept
  sb   a3, 2(a5)
  mv   a0, a4
  j    done
accept:
  sh   a0, 0(a5)
  sb   zero, 2(a5)
done:
  lw   ra, 12(sp)
  lw   s0, 8(sp)
  addi sp, sp, 16
  ret
ADCCLK_FN
stub:
  addi sp, sp, -16
  sw   ra, 12(sp)
  jal  ra, STUBJAL
  ori  a0, a0, 0x40
  lw   ra, 12(sp)
  addi sp, sp, 16
  ret
"""
# DIAG: the get_rgb_theme reply becomes a telemetry byte stream instead of the marker:
# frame = FF, LT hi7, LT lo7, RT hi7, RT lo7, LX hi7, LX lo7 (raw table values >> 1, latched at FF).
# State at 0x20004710: u8 idx, u16 vals[3] @+2. Poll with `81 04 41 00`, reply byte 18.
diag_stub = """
stub:
  lui  a5, 0x20004
  addi a5, a5, 0x710
  lbu  a4, 0(a5)
  bnez a4, tdata
  addi a3, gp, -1796
  lhu  a2, 8(a3)
  sh   a2, 2(a5)
  lhu  a2, 10(a3)
  sh   a2, 4(a5)
  lhu  a2, 0(a3)
  sh   a2, 6(a5)
  li   a0, 0xff
  j    tnext
tdata:
  addi a3, a4, -1
  srli a2, a3, 1
  slli a2, a2, 1
  add  a2, a5, a2
  lhu  a2, 2(a2)
  srli a2, a2, 1
  andi a1, a3, 1
  bnez a1, tlo
  srli a2, a2, 7
tlo:
  andi a0, a2, 0x7f
tnext:
  addi a4, a4, 1
  li   a3, 7
  bltu a4, a3, tstore
  li   a4, 0
tstore:
  sb   a4, 0(a5)
  ret
"""
# DIAG2: full DMA buffer snapshot. Frame = FF + 168 samples (arr4 = LT then arr5 = RT, 84 each,
# base gp-836, 168 bytes per channel array), each sample as hi7, lo7. State: u16 idx @0x20004710,
# snapshot buffer @0x20004720 (336 bytes).
diag2_stub = """
stub:
  lui  a5, 0x20004
  addi a5, a5, 0x710
  lhu  a4, 0(a5)
  li   a3, 337
  bltu a4, a3, sidx
  li   a4, 0
sidx:
  bnez a4, sdata
  addi a3, gp, -836
  addi a3, a3, 672
  addi a2, a5, 0x10
  li   a1, 168
scopy:
  lhu  a0, 0(a3)
  sh   a0, 0(a2)
  addi a3, a3, 2
  addi a2, a2, 2
  addi a1, a1, -1
  bnez a1, scopy
  li   a0, 0xff
  j    snext
sdata:
  addi a3, a4, -1
  srli a2, a3, 1
  slli a2, a2, 1
  add  a2, a5, a2
  lhu  a2, 0x10(a2)
  andi a1, a3, 1
  bnez a1, slo
  srli a2, a2, 7
slo:
  andi a0, a2, 0x7f
snext:
  addi a4, a4, 1
  li   a3, 337
  bltu a4, a3, sstore
  li   a4, 0
sstore:
  sh   a4, 0(a5)
  ret
"""
if DIAG:
    asm = asm[:asm.index("stub:")] + (diag2_stub if "--diag2" in sys.argv else diag_stub)

def assemble(text):
    with tempfile.TemporaryDirectory() as d:
        s, o, b = (os.path.join(d, n) for n in ("c.s", "c.o", "c.bin"))
        open(s, "w").write(text)
        subprocess.run(["llvm-mc", "-triple=riscv32", "-mattr=+m,-c,-relax", "-filetype=obj", s, "-o", o], check=True)
        subprocess.run(["llvm-objcopy", "-O", "binary", "-j", ".text", o, b], check=True)
        return open(b, "rb").read()

# first pass to find the stub offset, second with the real jal offset
adc_fn = ""
if ADCDIV:
    assert 2 <= ADCDIV <= 16
    asm = asm.replace("ADCCLK_FN", "ADCCLK_FN_REAL")
adc_val = (((ADCDIV - 1) >> 1) << 4) | (ADCDIV - 1) if ADCDIV else 0
def adc_asm(off):
    return f"adcclk:\n  li a1, {adc_val}\n  j {off}\n" if ADCDIV else ""
# first pass with a dummy tail-call offset to find adcclk's address
asm = asm.replace("ADCCLK_FN_REAL", "ADCCLK_PLACEHOLDER")
pre = asm[:asm.index("ADCCLK_PLACEHOLDER")] if ADCDIV else ""
ADCCLK = CAVE + len(assemble(pre)) if ADCDIV else 0
asm = asm.replace("ADCCLK_PLACEHOLDER", adc_asm(0x9940 - (ADCCLK + 4)) if ADCDIV else "").replace("ADCCLK_FN", "")
stub_off = len(assemble(asm[:asm.index("stub:")]))
STUB = CAVE + stub_off
code = assemble(asm.replace("STUBJAL", str(GET_RGB - (STUB + 8))))
assert CAVE + len(code) + 4 <= 0xed98

def far_call(at, target):    # auipc ra + jalr ra, encoded for the pc the code runs at
    off = (target - run_pc(at)) & 0xffffffff
    hi = ((off + 0x800) >> 12) & 0xfffff
    lo = (off - (hi << 12)) & 0xfff
    return struct.pack("<II", (hi << 12) | (1 << 7) | 0x17, (lo << 20) | (1 << 15) | (1 << 7) | 0x67)

dat = bytearray(open(src, "rb").read())
assert struct.unpack_from("<I", dat, 0)[0] & 0xff == 0x6e, "expects 1.10"
def put(addr, data, expect=None):
    i = BLOB + addr - BASE
    if expect is not None:
        assert dat[i:i + len(data)] == expect, f"unexpected bytes at {addr:#x}: {dat[i:i+len(data)].hex()}"
    dat[i:i + len(data)] = data

if "--adc-only" in sys.argv:
    # minimal fix: stock firmware + ADC clock /ADCDIV only (no filter, deadzone, marker or telemetry)
    assert ADCDIV
    code = assemble(f"adcclk:\n  li a1, {adc_val}\n  j {0x9940 - (CAVE + 4)}\n")
    ADCCLK = CAVE
    put(CAVE, code, bytes(len(code)))
else:
    ADCCLK = ADCCLK
# sanity: original call sites must still point at the originals
assert far_call(LT_CALL, SCALE) == dat[BLOB + LT_CALL - BASE:][:8]
assert far_call(RT_CALL, SCALE) == dat[BLOB + RT_CALL - BASE:][:8]
assert far_call(RGB_CALL, GET_RGB) == dat[BLOB + RGB_CALL - BASE:][:8]
if "--adc-only" not in sys.argv:
    put(CAVE, code, bytes(len(code)))
    put(LT_CALL, far_call(LT_CALL, CAVE))
    put(RT_CALL, far_call(RT_CALL, CAVE))
    put(RGB_CALL, far_call(RGB_CALL, STUB))
if ADCDIV:
    off = ADCCLK - ADC_CLK_CALL
    imm = off & 0x1fffff
    jal = (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3ff) << 21) | (((imm >> 11) & 1) << 20) | (((imm >> 12) & 0xff) << 12) | (1 << 7) | 0x6f
    put(ADC_CLK_CALL, struct.pack("<IH", jal, 0x0001), expect=bytes.fromhex("cd45ef209046"))
# Bootloader checks (bl/bl_r.c FUN_274 / FUN_1a3c): CH32 image length = u32 at blob+0x14, and the
# u32 right after that length must equal the byte-sum of blob[0:len]. The CH32 is only re-flashed
# when its version (u32 at blob+0x20) differs from what it runs now (flash 1.09 first).
# Extend len over the cave and redo the sum, else the bootloader refuses to boot the image.
old_len = struct.unpack_from("<I", dat, BLOB + 0x14)[0]
new_len = (CAVE + len(code) - BASE + 3) & ~3
assert new_len > old_len
struct.pack_into("<I", dat, BLOB + 0x14, new_len)
struct.pack_into("<I", dat, BLOB + new_len, sum(dat[BLOB:BLOB + new_len]) & 0xffffffff)
open(dst, "wb").write(dat)
if "--adc-only" in sys.argv:
    print(f"wrote {dst}: len {old_len:#x}->{new_len:#x}, ADC clock /{ADCDIV} only (helper @{CAVE:#x}, {len(code)} bytes)")
else:
    print(f"wrote {dst}: len {old_len:#x}->{new_len:#x}, T={T} N={N} DZ={DZ} ADCDIV={ADCDIV or 4}, filter @{CAVE:#x}, marker stub @{STUB:#x}, {len(code)} bytes")
