"""Frame-to-frame motion of the background (window area) to spot jitter, jumps and cuts."""
import subprocess, sys
import numpy as np

FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
W, H = 540, 960
path, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
raw = subprocess.run([FF, "-v", "error", "-ss", str(t0), "-t", str(t1 - t0), "-i", path,
                      "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)

def shift(a, b):
    """subpixel translation b->a via phase correlation"""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    A, B = np.fft.fft2(a * win), np.fft.fft2(b * win)
    R = A * np.conj(B); R /= np.abs(R) + 1e-9
    r = np.fft.ifft2(R).real
    y, x = np.unravel_index(np.argmax(r), r.shape)
    def sub(c, n, get):
        l, m, h = get((c - 1) % n), get(c), get((c + 1) % n)
        d = l - 2 * m + h
        return c + (0.5 * (l - h) / d if d else 0)
    ys = sub(y, r.shape[0], lambda i: r[i, x]); xs = sub(x, r.shape[1], lambda i: r[y, i])
    if ys > r.shape[0] / 2: ys -= r.shape[0]
    if xs > r.shape[1] / 2: xs -= r.shape[1]
    return ys * 2, xs * 2, r.max()  # in 1080p pixels

# top band = window/lamps (behind the head); its vertical motion reflects zoom + jitter
band = (slice(40, 260), slice(20, 520))
print(" t      dy(px)   dx(px)  conf  diff")
for i in range(1, len(fr)):
    dy, dx, c = shift(fr[i][band], fr[i - 1][band])
    diff = np.abs(fr[i] - fr[i - 1]).mean()
    flag = ""
    if diff > 18: flag = "CUT/INSERT"
    elif abs(dy) > 1.5 or abs(dx) > 1.5: flag = "JUMP"
    print(f"{t0 + i / 30:6.2f} {dy:7.2f} {dx:7.2f} {c:5.2f} {diff:5.1f} {flag}")
