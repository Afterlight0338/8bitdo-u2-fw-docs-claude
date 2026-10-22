## 7. Root cause: the ADC is clocked too fast

### 7.1 Getting raw values out without soldering

The firmware has no debug output for the ADC, and measuring the sensors with a multimeter went
nowhere (3.5). But there is one existing round trip from the PC into the co-processor and back:
`81 04 41 00` makes the main chip ask the co-processor for its lighting mode (UART command
`0x1b`), and the one-byte answer comes back to the PC in byte 18 of the reply.

So the diagnostic builds point the co-processor's call at `0x4862` (which fetches that byte) at
a small routine of their own, and the byte becomes a data stream. A frame starts with `FF`, the
data is split into 7-bit pieces so `FF` can't appear inside it. Polling as fast as USB allows
gives about 270 bytes per second:

* `--diag`: raw LT, RT and stick X from the raw table, 39 frames per second (`tools/telem.py`)
* `--diag2`: a full copy of the LT and RT sample arrays, 84 + 84 values, about one every 1.2 s
  (`tools/telem2.py`)

Everything else keeps working while it runs.

### 7.2 Raw values: a lattice

![Raw LT and RT values with the controller untouched, stock ADC clock](images/raw_lattice_div4.png)

60 s untouched at the stock clock (`data/telem_raw_div4_60s.log`). LT rests at 8330 and RT at
8602, and every excursion lands **exactly** 100 (LT) or about 97 (RT) above the last step:
8330, 8430, 8530, 8630… The stick, read the same way, mostly stayed within ±10 of 17930
(17788 to 18020 over the minute). Noise doesn't make steps of exactly 100.
Whole extra samples do: 100 raw is one sample being about 1,000 off (6.4).

### 7.3 The sample arrays: exactly 2048

![One LT sample array at 12 MHz with four samples of exactly 2048, and one at 6 MHz with none](images/dma_buffer_div4_vs_div8.png)

72 snapshots at the stock clock (`data/snap_div4_90s.log`, `tools/snapstats.py`). Samples 4 to
83, the ones that get averaged:

| | LT | RT |
| :--- | :--- | :--- |
| Rest value | 1041 | 1075 |
| Spread of the normal samples | ±2 (std 2.1) | ±2 (std 1.5) |
| Bad samples | 122 of 5,760 (2.12%) | 94 of 5,760 (1.63%) |
| Snapshots with at least one | 31 of 72 | 28 of 72 |
| Bad values | 2048 ×113, 1023 ×8, 1052 ×1 | 2048 ×89, 1023 ×3, 1792 ×1, 1055 ×1 |

The bad samples sit at random positions in the array, and they are **exactly** `0x800` (2048) or
`0x3FF` (1023). A sensor or a noisy supply would give random wrong values. These are bit patterns.

### 7.4 Why exactly 2048

The ADC is a successive approximation type: it finds the value one bit at a time, most
significant first. "Is the input above half scale?" If yes, set bit 11, then ask about the
next half, and so on down to bit 0.

At 1041 the first answer should be no. If the comparator hasn't settled when it's asked and
says yes, bit 11 is set, and every later step correctly decides the input is below each new
threshold, so all the remaining bits come out 0: **`0x800`**. The same thing one step later
(bit 10 wrongly cleared) gives **`0x3FF`**. Wrong decisions on the top bits, where the
comparator needs the most time, are the classic sign of an ADC clocked faster than it can settle.

Why the triggers and not the sticks: a trigger at rest sits near 1040, far below 2048, so a
wrong top bit adds about 1,000. A centred stick sits around 2240, close to 2048, so the same
mistake costs much less, and the stick deadzone hides it.

### 7.5 The clock

The ADC init writes the clock setting once, into ADC register `CTLR3` (`0x40012450`, bits 0 to 8):

| | 1.09 | 1.10 |
| :--- | :--- | :--- |
| Code | `c.li a1,19` / `jal 0x9940` at `0x6ca6` | the same at `0x6cd6` |
| Value | `0x13` | `0x13` |

In WCH's CH32X035 SDK, `0x13` is `ADC_CLK_Div4`: 48 MHz / 4 = **12 MHz**. The SDK's divider
values follow `((N-1) >> 1) << 4 | (N-1)`, so /8 is `0x37`. Whether 12 MHz is inside the chip's
rated range was not checked: it's the value 8BitDo ships, and it fails on this one.

### 7.6 The test

Same diagnostic build, only the clock changed to /8 (6 MHz), 88 snapshots
(`data/snap_div8_90s.log`):

| | 12 MHz (stock) | 6 MHz |
| :--- | :--- | :--- |
| LT bad samples | 122 of 5,760 | **0 of 7,040** |
| RT bad samples | 94 of 5,760 | **0 of 7,040** |
| Snapshots with any | 31 and 28 of 72 | 0 of 88 |

## 8. The fix

### 8.1 What changes

Stock 1.10 plus the clock, nothing else:

| Where (co-processor) | Stock | Patched |
| :--- | :--- | :--- |
| `0x6cd6` | `c.li a1,19` / `jal 0x9940` (`cd 45 ef 20 90 46`) | `jal 0xec60` / `c.nop` |
| `0xec60` | zero padding | `li a1,0x37` / `j 0x9940` |
| length word (offset `0x14`) | `0xbc44` | `0xbc68` |
| byte-sum (after the length) | `0x004cb5e5` | recomputed |

The helper loads the /8 value and jumps into the original clock function, which returns to the
code right after `0x6cd6`. The length grows by the helper so the bootloader sums and installs
it (5.5). `tools/patch_ch32.py --adcdiv 8 --adc-only` builds it and checks the original bytes
first.

### 8.2 Result

| Test | Result |
| :--- | :--- |
| 5 min untouched (`data/adcfix_untouched_300s.log`) | **0 LT events, 0 RT events** (a separate check right after showed the stick still reporting, so the reader was alive) |
| Owner's pull test, 4.5 min (`data/adcfix_user_pull_test.log`) | 45 LT and 38 RT presses, all real: full pulls to 255 and partial ones (61 to 98). No spikes. 2.5 minutes in the middle with no events at all |
| Version | still reports 1.10 |

On stock firmware every capture showed drift within seconds.

### 8.3 What it costs

Each conversion takes twice as long. Estimated from the settings (not measured), one round over
all six inputs goes from about 0.7 ms to about 1.5 ms, so the analog values in each report are
on average well under 1 ms older. The USB report rate, the buttons and the gyro don't change.

## 9. The patches that came before the fix

All built by `tools/patch_ch32.py` and kept so the numbers can be checked.

### 9.1 Getting code into the co-processor

The co-processor image ends with about 340 bytes of zero padding after its initialised data
(`0xec44` to `0xed98`), enough for small routines. The two trigger calls at `0x3a06`/`0x3a12` and
the lighting-mode call at `0x4862` are `auipc`/`jalr` pairs and easy to point elsewhere. The early
builds also set bit `0x40` in the lighting-mode answer, as a marker that the patched code was
really running (with the 1.09 hop from 0.4, it was).

### 9.2 Spike filter (`T=32 N=24`)

A change of up to 32 (of 1023) passes at once; a bigger jump only counts after 24 calls in a
row. 60 s untouched: off zero 5.2% (LT) and 6.2% (RT) of the time, against 23 to 67% in short
stock captures. Better, but most of what was left climbed one step at a time, and each step
was "small".

### 9.3 Rest deadzone (`DZ=115`)

Scaled values under 115 read 0 and the rest is stretched back to 0 to 1023, in front of the
filter. The deadzone itself worked (the new steps showed up exactly where predicted), but the
next 60 s landed in a bad phase: off zero 21% and 25% of the time, mostly 5 to 8 steps up. A
deadzone big enough for the bad phases would have eaten about 30% of the trigger.

### 9.4 Diagnostic builds

`--diag` and `--diag2` (7.1). They also carry the 9.2/9.3 code; the raw values they report are
from before it.

