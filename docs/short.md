## What this is

An 8BitDo Ultimate 2 Wireless whose triggers pressed themselves. Not a broken sensor: the chip
that reads the triggers runs its ADC too fast, and now and then a reading comes out as exactly
2048 instead of about 1040. Each bad reading shows up as a phantom 9% press. Halving the ADC clock
in the firmware fixed it: 0 phantom presses in 5 minutes, full range still there.

This is the short version: is it your problem, what to run, how to undo it. The long version
has the proof, the wrong turns and every byte.

## Is this your controller?

| Check | Must be |
| :--- | :--- |
| Controller | 8BitDo Ultimate 2 **Wireless** (2.4 GHz). Not the Bluetooth model |
| USB ID | `2dc8:310b` when running |
| Firmware | 1.10 |
| Symptom | LT and/or RT read above zero with nothing touching them, jumping in steps of roughly 24, 47, 67 (of 255) |

Tested on exactly one controller. If your triggers are fine, leave it alone.

## What you need

* Linux, Python 3, a USB cable
* `llvm-mc` and `llvm-objcopy` to build the patch (`nix-shell -p llvm python3` on NixOS)
* from the GitHub repo: [`tools/patch_ch32.py`](tools/patch_ch32.py) and [`tools/bootflash.py`](tools/bootflash.py)
* 8BitDo's official `1.09` and `1.10` files:

```
curl -s -X POST https://support.8bitdo.com/restapi/link/v1/client/firmware/select \
  -H 'Content-Type: application/json' -d '{"firmware_type":94,"beta":1}'
```

Download the two `fileURL`s and check them:

| File | SHA-256 |
| :--- | :--- |
| 1.09 | `f754df15d0a3fde833f231c7d9d585490e22adfe9145a8dc1b7c85ab5515cbc1` |
| 1.10 | `968edee528c23d56e2059288f90c109fa5135f060de5b403e72d0b6c50f5eb87` |

## Steps

**1. Build the patch** and check its hash. If it differs, stop.

```
python3 tools/patch_ch32.py u2w_1.10.dat u2w_1.10_adcfix.dat --adcdiv 8 --adc-only
sha256sum u2w_1.10_adcfix.dat
# c5e5d60c3929d5a0701c5dbd91736bc77fc817fcf91f82146f286263d5962833
```

**2. Find the controller's vendor node** (call it `hidrawV`):

```
for h in /sys/class/hidraw/hidraw*; do
  od -An -tx1 -v $h/device/report_descriptor | tr -d '\n' | grep -q '06 7a ff' && basename $h
done
```

**3. Flash 1.09 first.** The controller only re-flashes the trigger chip when the version number
changes, and the patch keeps 1.10's number.

```
python3 tools/bootflash.py /dev/hidrawV jump
grep -l 'HID_NAME=8BitDo 8BitDo Boot' /sys/class/hidraw/*/device/uevent   # -> hidrawB
python3 tools/bootflash.py /dev/hidrawB flash u2w_1.09.dat
```

**4. Then the patch.** Find `hidrawV` again (step 2), then:

```
python3 tools/bootflash.py /dev/hidrawV jump
python3 tools/bootflash.py /dev/hidrawB flash u2w_1.10_adcfix.dat
```

`flash` erases, writes, reads everything back and only then restarts the controller. It never
touches the bootloader.

**5. Check it.** Leave the controller alone for a few minutes: LT and RT should stay at 0. Pull
both triggers all the way: they should still reach 255.

## Undo

Steps 3 and 4 with the official files: `1.09`, then `1.10`. Official `1.10` straight over the
patch keeps the patched trigger chip.

## Don't

* Don't use 8BitDo's website for the patched file. It does write it, then waits forever for an
  answer the bootloader never sends, says "update failed" and leaves the controller in
  "8BitDo Boot". If that happens: `python3 tools/bootflash.py /dev/hidrawB reset`.
* Don't flash any of the other experiments from `patch_ch32.py` unless you've read section 9.
* Don't use this on the Ultimate 2 Bluetooth. Different hardware.

