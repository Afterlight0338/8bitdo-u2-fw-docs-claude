
# 8BitDo Ultimate 2 Wireless: the phantom trigger was the ADC clock

My 8BitDo Ultimate 2 Wireless started pressing its own triggers. LT, and later RT, sat at 20 to 70%
with nothing touching them. Everyone's first guess (mine too) was a dying hall sensor. It wasn't.
The co-processor that reads the triggers runs its ADC faster than this particular chip can handle,
and every now and then a conversion comes out as exactly 2048. Halving the ADC clock in the
firmware fixed it completely.

This is everything learned on the way: the wrong turns, how 8BitDo's updater and bootloader work,
how to get raw sensor data out of a stock controller without soldering anything, the proof, and
the 8-byte patch. Every number here was measured on the controller or read from the firmware.
Things that were not verified say so.

Written 2026-10-22. Firmware analysed: 8BitDo's official Ultimate 2 Wireless update `1.10`
(145,436 bytes, SHA-256 `968edee5…f5eb87`), plus `1.09` for comparison.

> **This only matters if your controller has the same fault.** If your triggers are fine, there
> is nothing to fix. The patch has been tested on exactly one controller.

## -2. Changelog

Newest first. Small wording fixes are not listed.

**2026-10-22**

* First version.

## -1. What?

Find out why the triggers of one Ultimate 2 Wireless press themselves, and fix it if it can be
fixed. It could: it's a firmware setting, not broken hardware.

## 0. How to flash the fix

Linux only as written (the tools talk to `/dev/hidraw*` directly). You need Python 3 and, to
build the patch, `llvm-mc` and `llvm-objcopy` (`nix-shell -p llvm python3` on NixOS).

**0.1 Get the official files.** 8BitDo's firmware list is public:

```
curl -s -X POST https://support.8bitdo.com/restapi/link/v1/client/firmware/select \
  -H 'Content-Type: application/json' -d '{"firmware_type":94,"beta":1}'
```

Download the `fileURL` of `1.09` and `1.10` from the reply. Check them (the reply's `md5` field
is the same for both versions, so don't trust it):

| File | SHA-256 |
| :--- | :--- |
| 1.09 | `f754df15d0a3fde833f231c7d9d585490e22adfe9145a8dc1b7c85ab5515cbc1` |
| 1.10 | `968edee528c23d56e2059288f90c109fa5135f060de5b403e72d0b6c50f5eb87` |

**0.2 Build the patched 1.10.**

```
python3 tools/patch_ch32.py u2w_1.10.dat u2w_1.10_adcfix.dat --adcdiv 8 --adc-only
sha256sum u2w_1.10_adcfix.dat
# c5e5d60c3929d5a0701c5dbd91736bc77fc817fcf91f82146f286263d5962833
```

If the hash differs, stop.

**0.3 Find the controller's two HID nodes.** Plug it in with a USB cable. The *vendor* node is the
one whose report descriptor contains usage page `0xff7a`:

```
for h in /sys/class/hidraw/hidraw*; do
  od -An -tx1 -v $h/device/report_descriptor | tr -d '\n' | grep -q '06 7a ff' && basename $h
done
```

**0.4 Flash 1.09, then the patch.** The bootloader only re-flashes the co-processor when its
version number changes (5.5), and the patch keeps 1.10's number. So go through 1.09 first:

```
python3 tools/bootflash.py /dev/hidrawV jump            # V = vendor node from 0.3
# the controller re-enumerates as 2dc8:3208 "8BitDo Boot"; find its hidraw (B):
grep -l 'HID_NAME=8BitDo 8BitDo Boot' /sys/class/hidraw/*/device/uevent
python3 tools/bootflash.py /dev/hidrawB flash u2w_1.09.dat
# boots into 1.09. Repeat 0.3, then:
python3 tools/bootflash.py /dev/hidrawV jump
python3 tools/bootflash.py /dev/hidrawB flash u2w_1.10_adcfix.dat
```

`flash` checks the PID, erases, writes, reads everything back and only then restarts the
controller. It refuses to touch anything below `0x5000`, where the bootloader lives.

**0.5 Going back to stock.** Same thing with the official files: `1.09`, then `1.10`. Flashing
stock `1.10` straight over the patch keeps the patched co-processor, because the version
numbers match.

**0.6 If it ends up stuck in "8BitDo Boot".** Nothing is broken: the bootloader is untouched.
Flash any official file with `bootflash.py ... flash`, or just `bootflash.py /dev/hidrawB reset`
if the last write completed. The official web updater can also leave it there, see 5.3.

## Contents

1. [The controller](#1-the-controller)
2. [The symptom](#2-the-symptom)
3. [What it wasn't](#3-what-it-wasnt)
4. [Two chips in one update file](#4-two-chips-in-one-update-file)
5. [The update path and the bootloader](#5-the-update-path-and-the-bootloader)
6. [How a trigger gets read](#6-how-a-trigger-gets-read)
7. [Root cause: the ADC is clocked too fast](#7-root-cause-the-adc-is-clocked-too-fast)
8. [The fix](#8-the-fix)
9. [The patches that came before the fix](#9-the-patches-that-came-before-the-fix)
10. [Corrections and open questions](#10-corrections-and-open-questions)
11. [Reference](#11-reference)

