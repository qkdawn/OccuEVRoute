from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math
import random


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "ppt" / "assets"
OUT.mkdir(parents=True, exist_ok=True)


NAVY = (20, 45, 78)
BLUE = (42, 111, 151)
TEAL = (46, 139, 137)
GREEN = (68, 145, 106)
RED = (188, 83, 73)
GREY = (84, 96, 112)
LIGHT = (242, 245, 248)
MID = (216, 224, 232)
WHITE = (255, 255, 255)
INK = (18, 24, 32)
ROAD = (235, 150, 64)
WATER = (190, 220, 245)
LAND = (235, 243, 231)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/aptosdisplay-bold.ttf") if bold else Path("C:/Windows/Fonts/aptos.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf") if bold else Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


F10 = font(10)
F11 = font(11)
F12 = font(12)
F13 = font(13)
F14 = font(14)
F16 = font(16)
F18 = font(18, True)
F20 = font(20, True)
F24 = font(24, True)
F30 = font(30, True)


def rounded(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text(draw: ImageDraw.ImageDraw, xy, value: str, fill=INK, font_obj=F14, anchor=None):
    draw.text(xy, value, fill=fill, font=font_obj, anchor=anchor)


def line_arrow(draw: ImageDraw.ImageDraw, start, end, fill=GREY, width=3):
    draw.line([start, end], fill=fill, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 10
    left = (end[0] - size * math.cos(angle - 0.45), end[1] - size * math.sin(angle - 0.45))
    right = (end[0] - size * math.cos(angle + 0.45), end[1] - size * math.sin(angle + 0.45))
    draw.polygon([end, left, right], fill=fill)


def draw_map(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int):
    rounded(draw, (x, y, x + w, y + h), 14, LAND, MID, 2)
    # water
    draw.polygon(
        [
            (x + 40, y + h - 210),
            (x + 230, y + h - 160),
            (x + 410, y + h - 120),
            (x + w - 30, y + h - 170),
            (x + w, y + h),
            (x, y + h),
        ],
        fill=WATER,
    )
    random.seed(4)
    # roads
    for i in range(14):
        pts = []
        base_y = y + 45 + i * h / 15
        for k in range(8):
            px = x + 20 + k * w / 7
            py = base_y + math.sin(k * 1.2 + i) * 22 + random.randint(-8, 8)
            pts.append((px, py))
        draw.line(pts, fill=(245, 186, 92), width=3)
    for i in range(10):
        pts = []
        base_x = x + 40 + i * w / 11
        for k in range(6):
            px = base_x + math.sin(k * 0.9 + i) * 20 + random.randint(-5, 5)
            py = y + 20 + k * h / 5
            pts.append((px, py))
        draw.line(pts, fill=(247, 170, 75), width=3)
    # route
    route = [
        (x + 110, y + 330),
        (x + 200, y + 270),
        (x + 320, y + 250),
        (x + 430, y + 200),
        (x + 560, y + 178),
    ]
    draw.line(route, fill=BLUE, width=8)
    draw.line(route, fill=(220, 240, 255), width=3)
    # markers
    for px, py, color in [
        (*route[0], NAVY),
        (*route[-1], RED),
        (x + 390, y + 310, GREEN),
        (x + 510, y + 260, GREEN),
        (x + 260, y + 170, GREEN),
    ]:
        draw.ellipse((px - 11, py - 11, px + 11, py + 11), fill=WHITE, outline=color, width=4)
    text(draw, (route[0][0] - 22, route[0][1] + 18), "Start", NAVY, F12)
    text(draw, (route[-1][0] - 36, route[-1][1] - 34), "Top station", RED, F12)
    text(draw, (x + 18, y + 18), "Shenzhen road network", GREY, F12)


def planner_demo():
    img = Image.new("RGB", (1500, 900), (232, 240, 236))
    d = ImageDraw.Draw(img)
    rounded(d, (24, 24, 380, 876), 16, WHITE, (205, 218, 216), 2)
    rounded(d, (400, 24, 1070, 876), 16, WHITE, (205, 218, 216), 2)
    rounded(d, (1090, 24, 1476, 876), 16, WHITE, (205, 218, 216), 2)

    text(d, (52, 58), "OCCUEVROUTE", GREEN, F12)
    text(d, (52, 88), "EV charging", NAVY, F30)
    text(d, (52, 124), "route planner", NAVY, F30)
    d.line((52, 178, 348, 178), fill=MID, width=2)
    text(d, (52, 220), "PLAN", GREY, F12)
    for label, value, yy in [
        ("Search radius", "10 km", 252),
        ("Max driving time", "30 min", 326),
        ("Current SOC", "50%", 400),
        ("Algorithm", "ALT A*", 474),
        ("Ranking", "Balanced", 548),
    ]:
        text(d, (52, yy), label, GREY, F12)
        rounded(d, (52, yy + 22, 348, yy + 66), 8, (250, 252, 252), (210, 220, 220), 1)
        text(d, (70, yy + 34), value, INK, F16)
    rounded(d, (52, 650, 348, 704), 10, TEAL)
    text(d, (200, 677), "Recommend stations", WHITE, F16, "mm")

    draw_map(d, 420, 44, 630, 812)

    text(d, (1120, 58), "OUTPUT", GREY, F12)
    text(d, (1120, 88), "Recommendation list", NAVY, F20)
    cards = [
        ("Top", "Station 1048", "12.4 min", "5.8 km", "SOC 41.8%", "occ 18%"),
        ("2", "Station 0872", "13.1 min", "6.2 km", "SOC 40.6%", "occ 24%"),
        ("3", "Station 0553", "14.7 min", "7.1 km", "SOC 39.0%", "occ 31%"),
    ]
    yy = 128
    for rank, station, time_v, dist, soc, occ in cards:
        rounded(d, (1120, yy, 1448, yy + 112), 12, LIGHT, (210, 220, 230), 1)
        rounded(d, (1138, yy + 18, 1186, yy + 66), 10, TEAL if rank == "Top" else BLUE)
        text(d, (1162, yy + 42), rank, WHITE, F14, "mm")
        text(d, (1204, yy + 18), station, NAVY, F18)
        text(d, (1204, yy + 50), f"{time_v}  |  {dist}", INK, F14)
        text(d, (1204, yy + 78), f"{soc}  |  predicted {occ}", GREY, F12)
        yy += 128
    text(d, (1120, 560), "DIAGNOSTICS", GREY, F12)
    for label, detail, yy in [
        ("Passed constraints", "drive time, energy and charger count validated", 592),
        ("Balanced score", "drive time + occupancy risk penalty", 660),
        ("Search trace", "expanded nodes shown for route explanation", 728),
    ]:
        rounded(d, (1120, yy, 1448, yy + 52), 10, WHITE, (210, 220, 230), 1)
        text(d, (1138, yy + 10), label, NAVY, F14)
        text(d, (1138, yy + 30), detail, GREY, F10)
    img.save(OUT / "planner-demo-clean.png", quality=95)


def ranking_diagnostics():
    img = Image.new("RGB", (1400, 760), WHITE)
    d = ImageDraw.Draw(img)
    text(d, (48, 42), "Recommendation output: route metrics + congestion risk + diagnostics", NAVY, F30)
    headers = ["Rank", "Station", "Drive time", "Distance", "Arrival SOC", "Pred. occupancy", "Balanced score"]
    xs = [54, 150, 360, 540, 700, 880, 1110]
    y = 126
    d.rounded_rectangle((40, y, 1360, y + 54), radius=10, fill=NAVY)
    for x, h in zip(xs, headers):
        text(d, (x, y + 18), h, WHITE, F14)
    rows = [
        ("Top", "Charging Station 1048", "12.4 min", "5.8 km", "41.8%", "18%", "0.59"),
        ("2", "Charging Station 0872", "13.1 min", "6.2 km", "40.6%", "24%", "0.68"),
        ("3", "Charging Station 0091", "16.2 min", "7.9 km", "37.2%", "22%", "0.76"),
        ("4", "Charging Station 0553", "14.7 min", "7.1 km", "39.0%", "31%", "0.80"),
    ]
    y += 68
    for i, row in enumerate(rows):
        fill = LIGHT if i % 2 == 0 else WHITE
        d.rounded_rectangle((40, y, 1360, y + 58), radius=8, fill=fill, outline=MID)
        for x, value in zip(xs, row):
            color = TEAL if value == "Top" else INK
            text(d, (x, y + 18), value, color, F14 if x != 150 else F16)
        y += 68
    text(d, (54, 476), "Rejected examples from post-check", NAVY, F20)
    rejects = [
        ("drive_time_exceeded", "route found but exceeds user's max driving time"),
        ("arrival_soc_below_safety_threshold", "energy use would leave too little arrival battery"),
        ("too_few_chargers", "station does not satisfy minimum charger count"),
    ]
    y = 522
    for code, desc in rejects:
        d.rounded_rectangle((54, y, 640, y + 52), radius=10, fill=(255, 246, 245), outline=(238, 196, 190))
        text(d, (74, y + 10), code, RED, F14)
        text(d, (74, y + 30), desc, GREY, F11)
        y += 64
    d.rounded_rectangle((730, 510, 1330, 702), radius=16, fill=LIGHT, outline=MID)
    text(d, (760, 540), "Balanced ranking", NAVY, F20)
    text(d, (760, 582), "ml_rank_score = drive_time_min / max_drive_time_min + occupancy", INK, F14)
    text(d, (760, 626), "time is normalized; occupancy is congestion risk, not waiting time", GREY, F14)
    img.save(OUT / "ranking-diagnostics.png", quality=95)


def pill(draw: ImageDraw.ImageDraw, xy, label: str, fill, outline=None, color=INK, font_obj=F13):
    rounded(draw, xy, 18, fill, outline or fill, 1)
    cx = (xy[0] + xy[2]) / 2
    cy = (xy[1] + xy[3]) / 2
    text(draw, (cx, cy), label, color, font_obj, "mm")


def draw_node(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, fill, outline=WHITE, size: int = 30):
    draw.ellipse((x - size // 2, y - size // 2, x + size // 2, y + size // 2), fill=fill, outline=outline, width=3)
    text(draw, (x, y), label, WHITE, F12, "mm")


def route_search_comparison():
    img = Image.new("RGB", (1500, 900), WHITE)
    d = ImageDraw.Draw(img)
    text(d, (54, 44), "Search strategies used in OccuEVRoute", NAVY, F30)
    text(d, (56, 86), "Six algorithms are presented as two families: search-space reduction and weighted shortest-path search.", GREY, F16)

    panels = [
        (54, 132, 440, 300, "BFS", "Single frontier baseline", BLUE),
        (530, 132, 440, 300, "Bidirectional BFS", "Forward and backward frontiers meet", TEAL),
        (1006, 132, 440, 300, "CH Bidirectional Dijkstra", "Offline shortcuts, online upward query", GREEN),
        (54, 492, 440, 300, "UCS", "Travel-time Dijkstra baseline", NAVY),
        (530, 492, 440, 300, "A*", "Travel-time search with heuristic h(n)", BLUE),
        (1006, 492, 440, 300, "ALT A*", "Landmark triangle-inequality heuristic", TEAL),
    ]
    for x, y, w, h, title, caption, color in panels:
        rounded(d, (x, y, x + w, y + h), 18, LIGHT, MID, 2)
        text(d, (x + 26, y + 22), title, color, F24)
        text(d, (x + 26, y + 58), caption, GREY, F14)
        # small grid
        gx, gy = x + 72, y + 112
        coords = []
        for r in range(3):
            row = []
            for c in range(6):
                px = gx + c * 58
                py = gy + r * 48 + (18 if c % 2 else 0)
                row.append((px, py))
                d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=MID)
                if c > 0:
                    prev = row[c - 1]
                    d.line((prev[0], prev[1], px, py), fill=(205, 214, 224), width=2)
            coords.append(row)
        start = coords[1][0]
        goal = coords[1][5]
        if title == "BFS":
            for rad, alpha_color in [(92, (220, 234, 246)), (62, (205, 224, 240)), (32, (188, 213, 232))]:
                d.ellipse((start[0] - rad, start[1] - rad, start[0] + rad, start[1] + rad), outline=alpha_color, width=6)
            d.line([coords[1][0], coords[0][1], coords[1][2], coords[0][3], coords[1][4], coords[1][5]], fill=BLUE, width=6)
        elif title == "Bidirectional BFS":
            d.ellipse((start[0] - 70, start[1] - 70, start[0] + 70, start[1] + 70), outline=(196, 222, 240), width=8)
            d.ellipse((goal[0] - 70, goal[1] - 70, goal[0] + 70, goal[1] + 70), outline=(194, 228, 222), width=8)
            d.line([start, coords[1][2], coords[1][3], goal], fill=TEAL, width=6)
            draw_node(d, coords[1][3][0], coords[1][3][1], "M", RED, size=26)
        elif title.startswith("CH"):
            for c in range(6):
                px, py = coords[1][c]
                d.line((px, py - 72, px, py + 72), fill=(221, 230, 226), width=2)
            d.line([start, coords[0][2], coords[1][4], goal], fill=GREEN, width=8)
            d.line([coords[0][2], coords[1][4]], fill=(255, 255, 255), width=3)
            pill(d, (x + 245, y + 204, x + 380, y + 236), "shortcut", (230, 242, 236), GREEN, GREEN, F12)
        elif title == "UCS":
            d.line([start, coords[2][1], coords[2][3], coords[1][4], goal], fill=NAVY, width=6)
            pill(d, (x + 120, y + 222, x + 318, y + 254), "priority by g(n)", WHITE, NAVY, NAVY, F12)
        elif title == "A*":
            d.polygon([(start[0] + 24, start[1] + 62), (goal[0] - 16, goal[1] - 54), (goal[0] - 16, goal[1] + 54)], fill=(230, 243, 244), outline=TEAL)
            d.line([start, coords[1][2], coords[1][4], goal], fill=BLUE, width=6)
            pill(d, (x + 145, y + 222, x + 295, y + 254), "f = g + h", WHITE, BLUE, BLUE, F12)
        else:
            for lx, ly in [coords[0][0], coords[2][1], coords[0][5], coords[2][5]]:
                d.rectangle((lx - 9, ly - 9, lx + 9, ly + 9), fill=(246, 196, 89), outline=(196, 136, 40))
            d.line([start, coords[0][2], coords[0][4], goal], fill=TEAL, width=6)
            pill(d, (x + 108, y + 222, x + 332, y + 254), "landmark lower bound", WHITE, TEAL, TEAL, F12)
        draw_node(d, start[0], start[1], "S", NAVY, size=30)
        draw_node(d, goal[0], goal[1], "G", RED, size=30)

    img.save(OUT / "route-search-comparison.png", quality=95)


def data_artifact_pipeline():
    img = Image.new("RGB", (1500, 860), WHITE)
    d = ImageDraw.Draw(img)
    text(d, (54, 42), "Project data pipeline and generated artifacts", NAVY, F30)
    text(d, (56, 84), "The route planner and ML model use different data streams, then meet inside the recommendation API.", GREY, F16)

    lanes = [
        ("Routing data", BLUE, [
            ("OSM Shenzhen roads", "download_road_network_tiles.py"),
            ("Clean directed graph", "shenzhen_drive_with_station_access.graphml"),
            ("Station access edges", "station_road_access.csv"),
            ("Search artifacts", "landmark_distances.npz\nch_index.pkl"),
        ]),
        ("Occupancy data", TEAL, [
            ("UrbanEV sessions", "busy / total chargers"),
            ("Time-series windows", "lag and rolling features"),
            ("Static context", "POI, weather, price, station profile"),
            ("Model artifacts", "occupancy_horizon_xgboost.pkl\nfeatures.json"),
        ]),
        ("Recommendation", GREEN, [
            ("User request", "location, SOC, constraints"),
            ("Candidate stations", "top 20 within 10 km"),
            ("Route + prediction", "time, distance, arrival SOC, occupancy"),
            ("Ranked response", "diagnostics and explanation"),
        ]),
    ]
    y = 145
    for title, color, steps in lanes:
        rounded(d, (54, y, 1446, y + 170), 18, LIGHT, MID, 2)
        text(d, (82, y + 28), title, color, F20)
        x = 285
        for i, (head, body) in enumerate(steps):
            bx = x + i * 275
            rounded(d, (bx, y + 32, bx + 220, y + 128), 14, WHITE, color, 2)
            text(d, (bx + 18, y + 52), head, NAVY, F16)
            text(d, (bx + 18, y + 82), body, GREY, F11)
            if i < len(steps) - 1:
                line_arrow(d, (bx + 228, y + 80), (bx + 262, y + 80), color, 3)
        y += 220

    img.save(OUT / "data-artifact-pipeline.png", quality=95)


def model_feature_stack():
    img = Image.new("RGB", (1500, 820), WHITE)
    d = ImageDraw.Draw(img)
    text(d, (54, 42), "ML feature stack for occupancy risk", NAVY, F30)
    text(d, (56, 84), "The model predicts occupancy rate at the arrival horizon; the planner uses it as congestion risk.", GREY, F16)

    groups = [
        ("Time", "hour, weekday, month,\nholiday flags", BLUE),
        ("Weather", "temperature, rain,\nwind, humidity", TEAL),
        ("Station profile", "charger count, price,\nhistorical profile", GREEN),
        ("POI context", "nearby malls, offices,\ntransit, restaurants", NAVY),
        ("Neighbor history", "nearby station load\nand local trend", BLUE),
        ("Lag features", "recent occupancy and\nrolling statistics", TEAL),
        ("Horizon", "prediction_horizon_min\n5 to 120 minutes", RED),
    ]
    center = (1160, 430)
    rounded(d, (980, 300, 1350, 560), 22, (235, 245, 244), TEAL, 3)
    text(d, (1165, 362), "XGBoost", NAVY, F30, "mm")
    text(d, (1165, 414), "multi-horizon\noccupancy model", GREY, F18, "mm")
    pill(d, (1040, 488, 1290, 528), "output: predicted occupancy rate", WHITE, TEAL, TEAL, F13)

    positions = [
        (70, 150), (370, 150), (670, 150),
        (70, 410), (370, 410), (670, 410),
        (370, 630),
    ]
    for (head, body, color), (x, y) in zip(groups, positions):
        rounded(d, (x, y, x + 230, y + 135), 16, LIGHT, color, 2)
        text(d, (x + 20, y + 22), head, color, F20)
        text(d, (x + 20, y + 62), body, GREY, F14)
        line_arrow(d, (x + 230, y + 68), (center[0] - 190, center[1]), color, 2)

    img.save(OUT / "model-feature-stack.png", quality=95)


def complexity_tradeoff():
    img = Image.new("RGB", (1500, 760), WHITE)
    d = ImageDraw.Draw(img)
    text(d, (54, 42), "Search complexity and trade-off map", NAVY, F30)
    text(d, (56, 84), "Worst-case complexity is only part of the story; practical expansion depends on frontier direction, heuristic strength, and preprocessing.", GREY, F16)

    # axes
    x0, y0, w, h = 130, 620, 1050, 430
    d.line((x0, y0, x0 + w, y0), fill=GREY, width=3)
    d.line((x0, y0, x0, y0 - h), fill=GREY, width=3)
    line_arrow(d, (x0 + w, y0), (x0 + w + 65, y0), GREY, 3)
    line_arrow(d, (x0, y0 - h), (x0, y0 - h - 55), GREY, 3)
    text(d, (x0 + w + 78, y0 - 10), "preprocessing / index cost", GREY, F14)
    text(d, (x0 - 92, y0 - h - 70), "online expansions", GREY, F14)

    points = [
        ("BFS", 80, 330, BLUE, "O(V + E)"),
        ("Bi-BFS", 170, 250, TEAL, "O(V + E)"),
        ("UCS", 330, 300, NAVY, "O((V + E) log V)"),
        ("A*", 520, 205, BLUE, "same worst-case"),
        ("ALT A*", 700, 140, TEAL, "landmark heuristic"),
        ("CH Dijkstra", 960, 80, GREEN, "offline + fast query"),
    ]
    for label, px, py, color, note in points:
        ax = x0 + px
        ay = y0 - py
        d.ellipse((ax - 18, ay - 18, ax + 18, ay + 18), fill=color, outline=WHITE, width=3)
        text(d, (ax + 28, ay - 22), label, color, F18)
        text(d, (ax + 28, ay + 5), note, GREY, F12)

    rounded(d, (1110, 160, 1440, 492), 18, LIGHT, MID, 2)
    text(d, (1138, 190), "Project scale", NAVY, F20)
    for i, (label, value) in enumerate([
        ("Road graph", "67,966 nodes\n148,995 directed edges"),
        ("Station access", "1,365 stations\n17,479 chargers"),
        ("CH index", "338,531 query edges\n192,196 shortcuts"),
        ("Default scope", "top 20 candidates\nwithin 10 km"),
    ]):
        yy = 235 + i * 62
        text(d, (1138, yy), label, TEAL, F14)
        text(d, (1264, yy), value, GREY, F12)
    img.save(OUT / "complexity-tradeoff.png", quality=95)


if __name__ == "__main__":
    planner_demo()
    ranking_diagnostics()
    route_search_comparison()
    data_artifact_pipeline()
    model_feature_stack()
    complexity_tradeoff()
    print(OUT)
