from PIL import Image

def analyze(img_path, name):
    img = Image.open(img_path)
    w, h = img.size
    print("\n" + "="*60)
    print("=== %s ===" % name)
    print("Size: %dx%d" % (w, h))
    
    # Find sidebar width by scanning first row for color changes
    print("\n--- First row color changes (sidebar boundary) ---")
    prev = img.getpixel((0, 5))
    for x in range(0, w, 2):
        px = img.getpixel((x, 5))
        diff = abs(px[0]-prev[0]) + abs(px[1]-prev[1]) + abs(px[2]-prev[2])
        if diff > 30:
            print("  x=%d: %s -> %s" % (x, str(prev), str(px)))
            prev = px
    
    # Sample sidebar
    print("\n--- Sidebar samples ---")
    for y in [10, 50, 100, 150, 200, 250, 300, 350]:
        px = img.getpixel((10, y))
        print("  y=%d: %s" % (y, str(px)))
    
    # Sample header
    print("\n--- Header samples ---")
    for x in [260, 300, 400, 500, 600, 700, 800, 900]:
        px = img.getpixel((x, 10))
        print("  x=%d: %s" % (x, str(px)))
    
    # Content area - find card boundaries
    print("\n--- Content vertical scan (x=300) ---")
    for y in range(0, h, 20):
        px = img.getpixel((300, y))
        r, g, b, a = px
        if r > 30 or g > 30 or b > 30:
            print("  y=%d: %s" % (y, str(px)))
    
    # Find all distinct horizontal bands with non-dark content
    print("\n--- UI element rows ---")
    for y in range(0, h, 5):
        non_bg = []
        for x in range(0, w, 5):
            px = img.getpixel((x, y))
            r, g, b, a = px
            if r > 35 or g > 35 or b > 35:
                non_bg.append(x)
        if non_bg:
            print("  y=%d: x=[%d..%d], count=%d" % (y, non_bg[0], non_bg[-1], len(non_bg)))
    
    img.close()

analyze('C:/Projekty/FrigoCore/MAKIETY/PULPIT.png', 'PULPIT.png')
analyze('C:/Projekty/FrigoCore/MAKIETY/OBIEKTY.png', 'OBIEKTY.png')
analyze('C:/Projekty/FrigoCore/MAKIETY/ALARM.jpg', 'ALARM.jpg')
