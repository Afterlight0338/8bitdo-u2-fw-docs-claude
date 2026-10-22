## 10. Corrections and open questions

### 10.1 Corrections

Things said during the investigation that turned out wrong. Kept so nobody repeats them.

| Said | Actually |
| :--- | :--- |
| The bumpers glitch | It was the analog LT (3.1) |
| 1.10 introduced the drift | It comes in phases and is on both versions; 1.09 sets the same clock (3.2, 7.5) |
| The new lighting code disturbs the ADC | Lighting off changed nothing that matters (3.4) |
| Faulty left hall sensor, ribbon or magnet | Both triggers fail in lockstep with bit-pattern values; the sensors are fine (7.3) |
| Each step of the ladder is one ADC count, and the trigger range is only about 40 counts | Each step is one bad sample out of 80, about 100 raw. The range is about 4,000 raw (6.4) |
| The update file's co-processor part has no checksum | Length at `0x14`, byte-sum right after it, checked by the bootloader (5.5) |
| The website's "update failed" means the flash failed | The write completes, the bootloader just never answers the save command (5.3) |

### 10.2 Open questions

* **The flex test.** Before opening the controller, pressing the left grip pegged LT at 255 and
  pressing the middle of the back woke both triggers (3.5). Bad ADC samples don't explain a
  solid 255. Maybe flexing moved the trigger arm, maybe it landed in a bad phase. Not
  repeated with the fix.
* **Why only this unit.** The replacement controller, same firmware, doesn't drift. Probably a
  slower ADC on this particular chip. A guess.
* **Why it comes in phases.** Minutes of quiet, then bursts. Temperature or supply voltage are
  the obvious suspects; nothing was measured.
* **Other units.** Untested. If yours drifts the same way (steps of the same size on both
  triggers), the diagnostic builds in 7.1 can check it without opening anything.
* **The chip.** CH32X035 is inferred from the code (4.3).
* **The cost.** 8.3 is an estimate. Counting ADC rounds per second on stock and patched would
  settle it.

## 11. Reference

### 11.1 HID commands (running controller)

Output report `0x81` on the vendor interface (usage page `0xff7a`), 64 bytes including the
report ID. `tools/hidcmd.py /dev/hidrawN 81 ...` sends one and prints the replies.

| Send | Does | Reply |
| :--- | :--- | :--- |
| `81 05 00 21 01` | read version | `02 22 6e …` = 1.10 |
| `81 05 00 3a 00` | reset trigger calibration | `02 3b …` |
| `81 05 00 3a 01` | save trigger calibration | `02 3b …` |
| `81 05 00 36 00` / `01` | reset all / stick calibration | |
| `81 04 40 00 <mode>` | set lighting mode, saved | `02 04 04 00 40 …` |
| `81 04 41 00` | read lighting mode | byte 18 |
| `81 05 00 51 00` | reboot into the bootloader (5.4) | none, it disconnects |

Lighting modes: 0 none, 1 power-on, 2 dynamic (default), 3 hot wheel, 4 solid,
5 "dynamic mingmo", 6 off, 7 max.

### 11.2 Co-processor addresses (1.10)

| Address | What |
| :--- | :--- |
| `0x3a06`, `0x3a12` | calls `scale(4)` (LT) and `scale(5)` (RT), RAM code |
| `0x4862` | call that fetches the lighting mode for UART command `0x1b`, RAM code |
| `0x5920` | `scale(axis)`: raw to 0..1023 |
| `0x6cd6` | ADC clock setup (`0x13` = /4) |
| `0x9940` | writes the ADC clock register (`ADC + 0x50`) |
| `0xdec0` | response curve, 1024 bytes |
| `0xec44` to `0xed98` | zero padding (patch space) |
| `gp-836` | six arrays of 84 samples |
| `gp-1796` | raw table, u16 per axis (4 = LT, 5 = RT) |

### 11.3 Tools

| File | What |
| :--- | :--- |
| `tools/bootflash.py` | bootloader flasher: `jump`, `probe`, `flash`, `reset`. Never writes below `0x5000` |
| `tools/patch_ch32.py` | builds the fix and the earlier patches (8, 9) |
| `tools/hidcmd.py` | sends one vendor report, prints replies |
| `tools/live.py` | live LT/RT bars from evdev, logs every change |
| `tools/telem.py`, `tools/telem2.py` | read the diagnostic builds (7.1) |
| `tools/snapstats.py` | bad-sample statistics for `telem2.py` logs |
| `tools/farcalls.py` | resolves `auipc`/`jalr` far calls in a rizin listing, RAM code aware |
| `tools/plots.py` | the two charts |
| `tools/build_readme.py`, `tools/build_site_page.py` | this README and the vivlos.dev page |

### 11.4 Data

| File | What |
| :--- | :--- |
| `data/snap_div4_90s.log`, `data/snap_div8_90s.log` | sample-array snapshots, 12 MHz and 6 MHz (7.3, 7.6) |
| `data/telem_raw_div4_60s.log`, `data/telem_raw_div4_probe.log` | raw LT/RT/stick X, stock clock (7.2) |
| `data/adcfix_untouched_300s.log`, `data/adcfix_user_pull_test.log` | the fix (8.2) |
| `data/filter_v1_untouched_60s.log`, `data/filter_v2_deadzone_untouched_60s.log` | 9.2, 9.3 |
| `data/stock_110_untouched_5s.log`, `data/stock_109_untouched_4s.log` | short stock captures |
| `data/stock_110_poke_test.log` | the bare-board poke test (3.5) |

Log lines are `unix_time axis value` (evdev, 0..255), `unix_time LT RT LX` (raw) or
`unix_time` followed by 168 samples (snapshots).

