## 1. The controller

| | |
| :--- | :--- |
| Controller | 8BitDo Ultimate 2 Wireless (2.4 GHz), the Evernight edition. It runs the regular Ultimate 2 Wireless firmware |
| Updater IDs | `firmware_type` 94, product ID `0x6012` |
| USB, normal | `2dc8:310b` "8BitDo Ultimate 2 Wireless Controller for PC" |
| USB, bootloader | `2dc8:3208` "8BitDo Boot" |
| Firmware on it | 1.10 (2026-05-13). 8BitDo's server only offers 1.09 and 1.10 |
| Triggers | hall effect: a magnet in the tip of each trigger arm, a 3-pin SOT-23 sensor marked `G39F` on the back board under each tip |

Not to be confused with the Ultimate 2 **Bluetooth** (`firmware_type` 97): different hardware,
encrypted firmware, nothing here applies to it.

![Back board, hall sensors marked](images/board_back_hall_sensors.jpg)

This is the back of the controller, so LT is on the right of the photo (the trigger bracket says
`L2` on that side). Each `G39F` sits right under its trigger's magnet. There are no wires to the
sensor itself: the magnet moves closer, the voltage on the sensor's output pin changes. `G39F`
probably is a GoChip GH39FKSW linear hall sensor (same package and name fragment), not confirmed.

![LT trigger arm, magnet in the tip](images/lt_trigger_arm_magnet.jpg)

## 2. The symptom

With nothing touching it, 8BitDo's Ultimate Software showed LT at 28 to 56% and jumping around.
RT was fine at first and started doing the same a day later. Anything above `0x4D` (77 of 255,
about 30%) also sets the digital LT/RT button bits in the report (4.2), so games saw real trigger
presses. The owner remembered it starting after a firmware update.

It comes and goes. Some captures, all with the controller lying on the desk:

| Firmware | Length | LT | RT |
| :--- | :--- | :--- | :--- |
| 1.10 | 5 s | 0 to 191, 96 events | 0 to 69, 8 events |
| 1.10, right after flashing it | 30 s | 0 to 137, 5,658 events | quiet |
| 1.09 | 30 s, quiet phase | 0, no events | 0, no events |
| 1.09 | 30 s, a bit later | 0 to 179, 21,017 events | 0 to 83, 66 events |

"Events" are value changes seen by Linux (evdev, `tools/live.py`), so they also say how busy it
was. Values are the report's 0 to 255.

## 3. What it wasn't

Most of the time went into things that turned out to be wrong. They're kept here because each
one looked convincing at the time, and two of them would have ended the investigation early.

### 3.1 The bumpers

The first description was "LB/RB glitching". The main chip's button code (4.2) scans a 4×6 key
matrix every 1 ms and reports each key from a single sample, with no debounce, so a bouncy
bumper switch would pass straight through. All true, and all about the wrong input: the video
showed the analog LT, not a bumper.

### 3.2 "1.10 broke it"

Flashing 1.09 gave 0 events in 5 s and again in 30 s. Back on 1.10: 5,658 events in 30 s.
That looked like proof, and 1.10's co-processor changes are almost all lighting code, so the
story became "the new RGB code disturbs the analog readings". Then 1.09 drifted again: 21,017
events in 30 s. The drift comes in phases, and short A/B tests happily land in a quiet one.
Both versions set the ADC clock the same way (7.2), so the version never mattered.

### 3.3 Calibration

8BitDo's software can recalibrate the triggers, and the same commands work over raw HID
(11.1): `81 05 00 3a 00` resets the trigger calibration, `81 05 00 3a 01` saves the newly learned
range. Both were acknowledged. 30 s untouched afterwards: LT 0 to 139 with 2,271 events. No change.

### 3.4 The lighting

Since 1.10 mostly changed RGB code, the lighting was switched off over HID (`81 04 40 00 06`,
11.1). 60 s before vs after: LT 23,900 → 8,800 events, RT 30,100 → 23,800. Still drifting.

### 3.5 Hall sensors, magnets, the ribbon

Before opening it, a flex test: pressing the left grip pegged LT at 255, pressing the middle of
the back woke both triggers, pressing the right side did nothing. That pointed at the left
sensor and the ribbon in the middle.

Opened up, the multimeter found the sensor pins: one at 0 V (GND), one at a steady 3.35 V (VCC,
doesn't move when the trigger is pulled), one that follows the trigger (OUT). The meter's other
readings on OUT were impossible (+7.68 V against GND, −17.67 V from VCC to OUT on a 3.35 V
part), so it couldn't say anything useful about OUT.

Poking around the bare board with a plastic stick (each sensor, the ribbon, the contacts in the
middle, the trigger motor plug) while logging: no spot made a difference. What the log did show:
the drift hit **both triggers at the same moments**, and the jumps landed on **the same few
values** over and over (LT 28, 52, 70, 83, 95, 133; RT 25, 48, 68, 80, 94). Two sensors failing
in lockstep is unlikely, so it had to be something they share. That was the first real clue, and
at that point the suspects were the sensors' shared power, ground, or the ribbon.

The flex test result is still not explained, see 10.2.

### 3.6 Filtering it away

Two firmware patches tried to hide the drift: a spike filter, then a rest deadzone (section 9).
Both helped and neither fixed it. They were useful anyway: they showed the output moving in fixed
steps, which is what led to looking at raw ADC values.

