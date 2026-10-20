"""앱 아이콘: 파란 바탕 위 노란 전구 (PC 창 아이콘·exe 아이콘, 폰 아이콘과 같은 그림).

python appicon.py  → app.ico 다시 만들기 (16~256 크기 PNG 를 담은 ICO)
"""
import os
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

BLUE = "#3182F6"
BULB = "#FFD24D"
BASE = "#E8F1FE"

# 108칸 격자 (폰 적응형 아이콘과 같은 좌표)
GLASS = ("M54,27 a17,17 0 0 1 17,17 c0,6.5 -3.6,10.3 -6.4,13.6 c-1.6,1.9 -2.6,3.6 -2.6,6.4 h-16 "
         "c0,-2.8 -1,-4.5 -2.6,-6.4 C40.6,54.3 37,50.5 37,44 a17,17 0 0 1 17,-17z")


def svg(background=True, scale=1.1):
    bg = '<rect x="0" y="0" width="108" height="108" rx="26" fill="%s"/>' % BLUE if background else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108">{bg}
<g transform="translate(54 52) scale({scale}) translate(-54 -50)">
<g stroke="#ffffff" stroke-width="3.2" stroke-linecap="round" opacity="0.9">
<path d="M54,15.5v4.5"/><path d="M28.5,26.5l3.2,3.2"/><path d="M79.5,26.5l-3.2,3.2"/>
<path d="M20,46h4.5"/><path d="M88,46h-4.5"/></g>
<path fill="{BULB}" d="{GLASS}"/>
<path d="M45.5,41.5a9.5,9.5 0 0 1 7,-7.5" stroke="#ffffff" stroke-width="3.2" stroke-linecap="round" fill="none" opacity="0.85"/>
<rect x="45" y="67" width="18" height="4.6" rx="2.3" fill="{BASE}"/>
<rect x="46.5" y="73" width="15" height="4.6" rx="2.3" fill="{BASE}"/>
<rect x="50" y="79" width="8" height="3.4" rx="1.7" fill="{BASE}"/>
</g></svg>'''


def pixmap(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg().encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def write_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    pngs = []
    for s in sizes:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pixmap(s).toImage().convertToFormat(QImage.Format_ARGB32).save(buf, "PNG")
        pngs.append((s, bytes(buf.data())))
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, data = b"", b""
    for s, png in pngs:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    with open(path, "wb") as f:
        f.write(head + entries + data)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    here = os.path.dirname(os.path.abspath(__file__))
    write_ico(os.path.join(here, "app.ico"))
    pixmap(512).save(os.path.join(here, "app_icon_preview.png"))
    print("app.ico 만듦")
