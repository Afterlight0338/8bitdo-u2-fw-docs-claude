#!/usr/bin/env python3
# Outlier stats for telem2 snapshot logs: samples 4..83 of each 84-sample LT/RT DMA buffer
# (the firmware's averaging window) that are >12 LSB from the buffer median.
import collections, statistics, sys
for path in sys.argv[1:]:
    rows = [list(map(int, l.split()[1:])) for l in open(path)]
    print(f"{path}: {len(rows)} snapshots")
    for name, off in (("LT", 0), ("RT", 84)):
        c, n, per = collections.Counter(), 0, []
        for r in rows:
            a = r[off + 4: off + 84]
            med = statistics.median(a)
            bad = [v for v in a if abs(v - med) > 12]
            per.append(len(bad)); n += len(a)
            for v in bad: c[v] += 1
        tot = sum(c.values())
        print(f"  {name}: median {statistics.median([statistics.median(r[off+4:off+84]) for r in rows]):.0f}, "
              f"outliers {tot}/{n} = {tot/n*100:.2f}%, buffers with any: {sum(1 for p in per if p)}/{len(per)}, values {c.most_common(6)}")
