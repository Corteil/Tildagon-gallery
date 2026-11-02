# Run with the unix port built with imgtool:  micropython mp_test.py DIR
# DIR holds big.jpg, p.png, bad.bin, il.png (made by compare_mp.py)
import imgtool, sys, os
d = sys.argv[1]
print("size", imgtool.size(d + "/big.jpg"), imgtool.size(d + "/p.png"))
print("thumb", imgtool.thumbnail(d + "/big.jpg", d + "/out_t.png"))
print("thumb40", imgtool.thumbnail(d + "/p.png", d + "/out_t40.png", size=40))
print("resize", imgtool.resize(d + "/big.jpg", d + "/out_r.jpg", 300, quality=90))
print("resize png", imgtool.resize(d + "/p.png", d + "/out_rp.jpg", max=200))
for name, call in (
    ("junk", lambda: imgtool.resize(d + "/bad.bin", d + "/x.jpg")),
    ("missing", lambda: imgtool.size(d + "/nope.jpg")),
    ("interlaced", lambda: imgtool.resize(d + "/il.png", d + "/x.jpg")),
    ("bad size", lambda: imgtool.thumbnail(d + "/big.jpg", d + "/x.png", size=0)),
    ("unwritable", lambda: imgtool.thumbnail(d + "/big.jpg", d + "/no/such/dir/x.png")),
):
    try:
        call(); print(name, "NO ERROR")
    except Exception as e:
        print(name, type(e).__name__)
# nothing half-written is left behind for failures that happen before output
print("x.jpg exists:", "x.jpg" in os.listdir(d))
# many in a row: memory must be released each time
for i in range(300):
    imgtool.thumbnail(d + "/big.jpg", d + "/loop.png")
    imgtool.resize(d + "/p.png", d + "/loop.jpg")
print("loop ok")
