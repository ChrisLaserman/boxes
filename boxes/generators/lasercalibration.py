# Copyright (C) 2026 Chris (ChrisLaserman)
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

from boxes import *


class LaserCalibration(Boxes):
    """Measure kerf and effective material thickness in one cut"""

    description = """Everything on this sheet is drawn at its nominal size with
no burn correction, whatever burn is set to.

**Kerf coupon:** a square hole of known size. Measure the square that drops
out and the hole it leaves with calipers. The square shrinks and the hole
grows by one kerf, so kerf = (hole - square) / 2 and the burn setting to use
is half of that.

**Thickness gauge:** a comb of notches labelled with their drawn width.
Slide a scrap of your sheet into them and note the label of the tightest
notch it still goes into. The real slot width is the label plus one kerf.

Feed both results into `scripts/calibrate` to write them into
machine_profile.yaml.
"""

    ui_group = "Part"

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.argparser.add_argument(
            "--square", action="store", type=float, default=40.0,
            help="size of the kerf coupon square in mm")
        self.argparser.add_argument(
            "--gauge_min", action="store", type=float, default=2.4,
            help="narrowest notch of the thickness gauge in mm")
        self.argparser.add_argument(
            "--gauge_max", action="store", type=float, default=3.4,
            help="widest notch of the thickness gauge in mm")
        self.argparser.add_argument(
            "--gauge_step", action="store", type=float, default=0.05,
            help="width increase between notches in mm")

    def gauge(self, move=None):
        n = int(round((self.gauge_max - self.gauge_min) / self.gauge_step)) + 1
        widths = [self.gauge_min + i * self.gauge_step for i in range(n)]
        gap, depth, h = 6.0, 12.0, 25.0
        l = gap + sum(w + gap for w in widths)

        if self.move(l, h, move, True):
            return

        font = {"fontsize": 2.5, "align": "center", "color": Color.ETCHING}
        x = l - gap
        for w in widths:
            self.text(f"{w:.2f}", x - w / 2, h - depth - 4, **font)
            x -= w + gap
        self.text("thickness gauge (drawn width, mm)", l / 2, 3, **font)

        self.moveTo(0, 0)
        self.polyline(l, 90, h, 90)
        # notches along the top edge, right to left
        for w in widths:
            self.polyline(gap, 90, depth, -90, w, -90, depth, 90)
        self.polyline(gap, 90, h, 90)

        self.move(l, h, move)

    def coupon(self, move=None):
        s = self.square
        f = s + 20

        if self.move(f, f, move, True):
            return

        font = {"fontsize": 3, "align": "center", "color": Color.ETCHING}
        self.text(f"kerf coupon {s:.1f} mm", f / 2, 4, **font)
        self.text("measure square and hole", f / 2, f - 7, **font)
        self.rectangularHole(f / 2, f / 2, s, s)
        self.moveTo(0, 0)
        self.polyline(f, 90, f, 90, f, 90, f, 90)

        self.move(f, f, move)

    def render(self):
        self.burn = 0.0
        self.coupon(move="right")
        self.gauge(move="right")
