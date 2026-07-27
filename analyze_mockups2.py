from PIL import Image

def analyze(img_path, name):
    img = Image.open(img_path)
    w, h = img.size
    print("\n" + "="*60)
    print("=== %s ===" % name)
    print("Size: %dx%d" % (w, h))
    
    # Handle both RGBA and RGB
    has_alpha = len(img.getpixel((0,0))) == 4
    
    def get_px(x, y):
        px = img.getpixel((x, y))
        if has_alpha:
            return px[:3]
        return px
    
    # Find sidebar width - scan first row for non-dark pixels
    print("\n--- First row scan (y=5) ---")
    prev = get_px(0, 5)
    for x in range(0, w, 1):
        px = get_px(x, 5)
        diff = abs(px[0]-prev[0]) + abs(px[1]-prev[1]) + abs(px[2]-prev[2])
        if diff > 20:
            print("  x=%d: %s -> %s" % (x, str(prev), str(px)))
            prev = px
    
    # Find all non-dark horizontal bands
    print("\n--- Content bands (non-dark rows) ---")
    bands = []
    in_band = False
    band_start = 0
    for y in range(0, h, 2):
        has_content = False
        for x in range(0, w, 10):
            px = get_px(x, y)
            if px[0] > 30 or px[1] > 30 or px[2] > 30:
                has_content = True
                break
        if has_content and not in_band:
            band_start = y
            in_band = True
        elif not has_content and in_band:
            bands.append((band_start, y))
            in_band = False
    if in_band:
        bands.append((band_start, h))
    
    for start, end in bands:
        # Sample colors in this band
        colors = set()
        for x in [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]:
            if x < w:
                colors.add(get_px(x, start + 2))
        print("  y=%d..%d: colors=%s" % (start, end, str(colors)))
    
    # Detailed scan of specific areas
    print("\n--- Detailed color map (every 50px) ---")
    for y in range(0, h, 50):
        row_colors = []
        for x in range(0, w, 50):
            px = get_px(x, y)
            row_colors.append("%d:%s" % (x, str(px)))
        print("  y=%d: %s" % (y, " | ".join(row_colors)))
    
    img.close()

analyze('C:/Projekty/FrigoCore/MAKIETY/PULPIT.png', 'PULPIT.png')
analyze('C:/Projekty/FrigoCore/MAKIETY/OBIEKTY.png', 'OBIEKTY.png')

# ALARM.jpg is RGB not RGBA
img = Image.open('C:/Projekty/FrigoCore/MAKIETY/ALARM.jpg')
w, h = img.size
print("\n" + "="*60)
print("=== ALARM.jpg ===")
print("Size: %dx%d" % (w, h))
print("Mode: %s" % img.mode)

# Find sidebar
print("\n--- First row scan (y=5) ---")
prev = img.getpixel((0, 5))
for x in range(0, w, 1):
    px = img.getpixel((x, 5))
    diff = abs(px[0]-prev[0]) + abs(px[1]-prev[1]) + abs(px[2]-prev[2])
    if diff > 20:
        print("  x=%d: %s -> %s" % (x, str(prev), str(px)))
        prev = px

print("\n--- Content bands ---")
bands = []
in_band = False
band_start = 0
for y in range(0, h, 2):
    has_content = False
    for x in range(0, w, 10):
        px = img.getpixel((x, y))
        if px[0] > 30 or px[1] > 30 or px[2] > 30:
            has_content = True
            break
    if has_content and not in_band:
        band_start = y
        in_band = True
    elif not has_content and in_band:
        bands.append((band_start, y))
        in_band = False
if in_band:
    bands.append((band_start, h))

for start, end in bands:
    colors = set()
    for x in [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]:
        if x < w:
            colors.add(img.getpixel((x, start + 2)))
    print("  y=%d..%d: colors=%s" % (start, end, str(colors)))

print("\n--- Detailed color map ---")
for y in range(0, h, 50):
    row_colors = []
    for x in range(0, w, 50):
        px = img.getpixel((x, y))
        row_colors.append("%d:%s" % (x, str(px)))
    print("  y=%d: %s" % (y, " | ".join(row_colors)))

img.close()
