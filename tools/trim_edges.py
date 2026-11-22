import sys
import numpy as np
import soundfile as sf

src, dst = sys.argv[1], sys.argv[2]
data, sr = sf.read(src, always_2d=True)
mono = data.mean(axis=1)
thr = 10 ** (-70 / 20)

above = np.flatnonzero(np.abs(mono) > thr)
if above.size:
    pad = int(0.25 * sr)
    start = max(0, above[0] - pad)
    end = min(len(data), above[-1] + pad)
    data = data[start:end]

sf.write(dst, data, sr)
print("trimmed to %.2f s" % (len(data) / sr))
