from math import cos, pi, sin
from sketch2gui.models import Stroke


def rectangle(x1, y1, x2, y2, points_per_side=12):
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    points = []
    for start, end in zip(corners, corners[1:]):
        for i in range(points_per_side):
            t = i / points_per_side
            points.append((start[0] + (end[0]-start[0])*t, start[1] + (end[1]-start[1])*t))
    points.append(corners[-1])
    return Stroke(points)


def line(x1, y1, x2, y2, n=16):
    return Stroke([(x1 + (x2-x1)*i/n, y1 + (y2-y1)*i/n) for i in range(n+1)])


def ellipse(cx, cy, rx, ry, n=80):
    return Stroke([(cx + rx*cos(2*pi*i/n), cy + ry*sin(2*pi*i/n)) for i in range(n+1)])
