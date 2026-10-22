## 4. Two chips in one update file

### 4.1 The `.dat`

| Offset | Content |
| :--- | :--- |
| `0x00` | 28-byte header: version (`0x6e` = 1.10), load address `0x5000`, size `0x23800`, PID `0x6012`, a 32-bit field that didn't match any checksum tried, 0, 0 |
| `0x1c` | main chip image (Telink, `KNLT` at +8). Word +`0x18` = end of its code (`0x17a64` in 1.10), followed by a CRC32 |
| `0x1c + 0x17a68` | the co-processor's application, to the end of the file |

Offsets below are inside the image (header stripped) unless they're co-processor addresses.

### 4.2 Main chip: Telink

A Telink chip (TC32 instruction set) does USB, the 2.4 GHz radio, the buttons, remapping and
macros, and builds the reports. Buttons are a 4×6 matrix scanned every 1 ms. Analog trigger
values arrive from the co-processor over a UART, and anything above `0x4D` also sets the digital
LT/RT bits. Decompiled with Ghidra and the TC32 module from `trust1995/Ghidra_TELINK_TC32`.

### 4.3 Co-processor: WCH RISC-V

The rest of the file is a plain RISC-V application for a WCH microcontroller. It reads the
sticks and triggers, the gyro, drives the lighting and stores calibration. Most likely a
CH32X035: 48 MHz fixed clock, 20 KB RAM, and an ADC clock register that matches WCH's CH32X035
SDK (7.5). Inferred from the code, the chip marking was not read.

| 1.10 | |
| :--- | :--- |
| Load address | `0x3000` (its own 12 KB bootloader sits below) |
| RAM code | flash `0x3100`, `0x1a04` bytes, copied to `0x20000000` at boot. Far calls from there show up as `0xe000xxxx` when disassembled at the flash address |
| gp | `0x20002288` |
| Stack top | `0x20005000` (20 KB RAM) |
| Vector table | `mtvec = 0x3004`, vectored. Reserved slots 4 and 7 hold 8BitDo's length and version (5.5) |

### 4.4 1.09 vs 1.10

The main chip's code is identical except for the power-off routine. The co-processor changes
are lighting code (a new RGB type handler, extra logging) and one new UART command. Nothing
touches the ADC or the triggers, which fits 3.2.

## 5. The update path and the bootloader

### 5.1 The official updater

`web.8bitdo.com` is a WebHID page and works on Linux in Chromium and Brave, no driver needed.
It lists every version the server has (so 1.09 is selectable), and **Ctrl+click on the update
button opens a file picker for a local `.dat`**. Its protocol code is in
`p_connectDevice-*.js`; `tools/bootflash.py` is a reimplementation of the bootloader-mode part.

### 5.2 Bootloader protocol

In the bootloader the controller is `2dc8:3208` with one HID interface: 64-byte reports, no
report ID. Each request is `05, cmd u16, params u16, len u16, crc16 u16, total_len u32,
offset u32, data…` (little endian). The reply repeats the fields from byte 2; success is
reply cmd 0 with params equal to the command sent, reply data starts at byte 18.

| cmd | What | Notes |
| :--- | :--- | :--- |
| 8 | read PID | answers `0x6012` |
| 5 | read flash | 32 bytes at `offset` |
| 4 | erase | `total_len` bytes from `offset` |
| 3 | write | 46 bytes, `crc16` = CRC-16/MODBUS of the data |
| 7 | reset | no reply, boots the image |
| 195 | "read CRC" | returned values didn't match a CRC-16 of the data, not used |
| 196 | save | **never answers** (5.3) |

The image is written at `0x5000`. The bootloader lives at `0` to `0x5000`; the tools here refuse
to erase or write below `0x5000`.

### 5.3 Why the website says "update failed"

After writing, the website sends cmd 196 and waits for a reply that never comes. It reports
"update failed" and never sends the reset, so the controller stays in "8BitDo Boot". The image
was fine: all `0x23800` bytes read back identical to the official file, and a plain reset
(cmd 7) booted it. `bootflash.py` skips cmd 196.

### 5.4 Getting into the bootloader

From the running controller, on the vendor interface (usage page `0xff7a`), send report
`81 05 00 51 00`. The firmware writes `0x5a` into retained analog register `0x3c` and reboots,
and the bootloader sees the flag and stays. The website's own jump command (12) does nothing on
this model.

### 5.5 What the bootloader checks before booting

Read out the bootloader with cmd 5 (`0` to `0x5000`) and decompiled it with the same TC32 setup.
If the `0x3c` flag isn't set:

1. **Main image:** the Telink code ends with a standard CRC32; the byte-sum of everything
   before that CRC must equal the word right after it.
2. **Co-processor image:** length = u32 at co-processor offset `0x14`; the 32-bit byte-sum of
   the first `length` bytes must equal the u32 stored right after them. Otherwise it stays in
   the bootloader. This is what rejected the first patched file here: the new code sat past
   `length` and the sum was stale.
3. **Co-processor version:** it reads the version from the co-processor (its address
   `0x08003020`) and compares it with u32 at offset `0x20` of the image. **Only if they differ**
   does it re-flash the co-processor: erase 4 KB pages, write 256-byte chunks up to `length`,
   then send the stored sum for the co-processor's own bootloader to check.

Point 3 is why installing the patch goes through 1.09 first (0.4).

| | 1.09 | 1.10 |
| :--- | :--- | :--- |
| co-processor `length` | `0xbbdc` | `0xbc44` |
| stored sum | `0x004c9bc0` | `0x004cb5e5` |
| version word | `0x6d` | `0x6e` |

## 6. How a trigger gets read

All co-processor addresses, 1.10.

### 6.1 ADC and DMA

The ADC reads six inputs: four stick axes, LT and RT. One channel at a time: DMA collects **84
conversions** into a buffer, an interrupt copies it into that channel's array (six arrays of 84
values at `gp-836`) and starts the next channel. The ADC clock is set once at init (7.5).

### 6.2 Averaging

A loop sums samples **4 to 83** of each array (sample 0 still holds the previous channel) and
divides by 10, so the "raw" value is 8 × the mean of 80 conversions. For LT and RT that value
goes straight into the raw table at `gp-1796` (entries 4 and 5); the stick values get more
processing first.

### 6.3 Scaling

`scale(axis)` at `0x5920`: `(raw - min) * 1023 / (max - min)`, clamped to 0 to 1023, with min and
max from calibration. Then a 1024-entry response curve at `0xdec0` turns that into 0 to 255.
The curve is steep near zero (`curve[26] = 24`), so small values get amplified. The result goes
over the UART to the main chip and into the USB report.

The two calls that do this for LT and RT are in the RAM code at flash `0x3a06` and `0x3a12`.

### 6.4 What one bad sample does

If one of the 80 samples reads 2048 instead of 1041, the raw value goes up by
(2048 − 1041) / 10 ≈ **100**. This unit's calibrated trigger range is about 4,000 raw, so that's
26 of 1023 after scaling, and **24 of 255 in the report**: a phantom 9% press from one wrong
conversion out of 80. Two bad samples, 47. Three, 67. That's the ladder of repeating values
from 3.5 (the exact numbers shift a little with where each trigger rests).

