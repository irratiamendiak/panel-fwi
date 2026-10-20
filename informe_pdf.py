#!/usr/bin/env python3
"""
Informe PDF diario del panel de riesgo de incendios de Gipuzkoa (para adjuntarlo al correo).

Contenido (A4, euskera y castellano):
  1. Resumen: último dato y previsión a 3 días de FWI, Basugix e ICONA por estación.
  2-4. Una página por índice con 4 mapas (dato del día + 3 días de previsión).
  5. Meteorología al mediodía solar: tabla y mapas (temperatura, humedad, viento, lluvia 24 h).
  6. Previsión meteorológica a 3 días: tabla y 12 mapas.
Los mapas colorean las zonas de influencia de cada estación (docs/data/zonas.geojson) y dibujan el
contorno de Gipuzkoa (docs/data/gipuzkoa.geojson, si existe).

Uso:  from informe_pdf import generar;  generar(datos_fwi_json, "informe.pdf")
"""
import json, math
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Image as RLImage)
import io
import numpy as np
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageFilter
from reportlab.graphics.shapes import Drawing, Polygon, Rect, String, Circle, Group
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------- tipografía y estilos
for nom, fich in (("DV", "DejaVuSans.ttf"), ("DVB", "DejaVuSans-Bold.ttf")):
    for carpeta in ("/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/", ""):
        try:
            pdfmetrics.registerFont(TTFont(nom, carpeta + fich)); break
        except Exception:
            continue
from reportlab.lib.fonts import addMapping
if not {"DV", "DVB"} <= set(pdfmetrics.getRegisteredFontNames()):
    raise RuntimeError("Falta la tipografía DejaVu (paquete fonts-dejavu-core)")
addMapping("DV", 0, 0, "DV"); addMapping("DV", 1, 0, "DVB")

VERDE = colors.HexColor("#1f5f46"); GRIS = colors.HexColor("#56636b"); TINTA = colors.HexColor("#14231c")
ST = {
    "t": ParagraphStyle("t", fontName="DVB", fontSize=16, leading=20, textColor=TINTA),
    "sub": ParagraphStyle("sub", fontName="DV", fontSize=9, leading=12, textColor=GRIS, spaceAfter=6),
    "h": ParagraphStyle("h", fontName="DVB", fontSize=13, leading=16, textColor=VERDE, spaceBefore=4, spaceAfter=4),
    "p": ParagraphStyle("p", fontName="DV", fontSize=8.5, leading=11.5, spaceAfter=4),
    "n": ParagraphStyle("n", fontName="DV", fontSize=7.5, leading=10, textColor=GRIS),
    "c": ParagraphStyle("c", fontName="DV", fontSize=7.5, leading=9.5, alignment=1),
    "cl": ParagraphStyle("cl", fontName="DV", fontSize=7.5, leading=9.5),
    "ch": ParagraphStyle("ch", fontName="DVB", fontSize=7.5, leading=9.5, alignment=1, textColor=colors.white),
}
P = lambda t, s="p": Paragraph(t, ST[s])

# ---------------------------------------------------------------- niveles de los índices
COL = ["#2f8f5b", "#8fbf3f", "#f0c53b", "#ee8a2e", "#d9382b", "#7a1f4d"]
FG = ["#ffffff", "#14231c", "#14231c", "#14231c", "#ffffff", "#ffffff"]
NIV = ["Oso baxua", "Baxua", "Ertaina", "Handia", "Oso handia", "Muturrekoa"]
NIV_ICO = ["Hutsa", "Baxua", "Ertaina", "Handia", "", "Muturrekoa"]


def bgx(d):
    i = d.get("ifg")
    return None if i is None else max(0.0, 20 + 10 * math.log2(max(i, 1e-6)))


def idx_fwi(v):
    return None if v is None else sum(v > t for t in (5.2, 11.2, 21.3, 38, 50))


def idx_bgx(v):
    return None if v is None else sum(v >= t for t in (10, 20, 30, 40, 50))


def idx_ico(v):
    if v is None:
        return None
    v = round(v)
    return 0 if v <= 0 else 1 if v <= 4 else 2 if v <= 8 else 3 if v <= 12 else 5


INDICES = {   # nombre: (valor, índice de nivel, formato, leyenda)
    "FWI": (lambda d: d.get("fwi"), idx_fwi, lambda v: f"{v:.1f}".replace(".", ","),
            [(0, "< 5,2"), (1, "5,2–11,2"), (2, "11,2–21,3"), (3, "21,3–38"), (4, "38–50"), (5, "≥ 50")]),
    "Basugix": (bgx, idx_bgx, lambda v: f"{v:.1f}".replace(".", ","),
                [(0, "< 10"), (1, "10–20"), (2, "20–30"), (3, "30–40"), (4, "40–50"), (5, "≥ 50")]),
    "ICONA": (lambda d: d.get("icona"), idx_ico, lambda v: str(int(round(v))),
              [(0, "0"), (1, "1–4"), (2, "5–8"), (3, "9–12"), (5, "≥ 13")]),
}

# ---------------------------------------------------------------- escalas meteorológicas (las de la web)
RAMPAS = {
    "T": [[0, (59, 111, 182)], [10, (127, 183, 217)], [17, (242, 230, 160)], [24, (240, 160, 75)], [32, (217, 56, 43)]],
    "H": [[20, (217, 96, 43)], [45, (242, 196, 107)], [70, (207, 227, 239)], [100, (59, 120, 182)]],
    "W": [[0, (244, 246, 248)], [10, (215, 234, 223)], [20, (159, 208, 176)], [35, (240, 192, 64)], [55, (217, 56, 43)]],
    "R": [[0, (244, 246, 248)], [0.5, (207, 227, 245)], [3, (134, 184, 232)], [8, (63, 134, 214)], [15, (31, 79, 158)], [25, (122, 63, 176)]],
}
TRAMOS = {"T": [0, 4, 8, 12, 16, 20, 24, 28, 32], "H": [20, 30, 40, 50, 60, 70, 80, 90, 100],
          "W": [0, 5, 10, 15, 20, 25, 30, 35, 45, 55], "R": [0, 0.2, 0.5, 1, 2, 3, 5, 8, 12, 15, 20, 25]}
METEO = {"T": ("Tenperatura<br/><font size='5'>(eguzki-eguerdian)</font>", "°C"), "H": ("Hezetasuna<br/><font size='5'>(eguzki-eguerdian)</font>", "%"),
         "W": ("Haizea<br/><font size='5'>(eguzki-eguerdian)</font>", "km/h"), "R": ("Euria<br/><font size='5'>(aurreko 24 orduak)</font>", "mm")}


def rampa(r, v):
    if v <= r[0][0]:
        return r[0][1]
    for i in range(1, len(r)):
        if v <= r[i][0]:
            (a, ca), (b, cb) = r[i - 1], r[i]; t = (v - a) / (b - a)
            return tuple(x + t * (y - x) for x, y in zip(ca, cb))
    return r[-1][1]


def color_tramo(var, v):
    t = TRAMOS[var]; i = len(t) - 2
    for k in range(1, len(t)):
        if v < t[k]:
            i = k - 1; break
    c = rampa(RAMPAS[var], (t[i] + t[i + 1]) / 2)
    return colors.Color(*(x / 255 for x in c))


def sector8(g):
    return None if g is None else ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int(((g % 360) + 22.5) // 45) % 8]


DIAS_EU = ["al.", "ar.", "az.", "og.", "or.", "lr.", "ig."]
DIAS_ES = ["lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."]
MES_EU = ["urt.", "ots.", "mar.", "api.", "mai.", "eka.", "uzt.", "abu.", "ira.", "urr.", "aza.", "abe."]
MES_ES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]


def ffecha(f):
    d = date.fromisoformat(f)
    return f"{DIAS_EU[d.weekday()]}, {MES_EU[d.month-1]} {d.day}"


def fnum(v, dec=1):
    return "—" if v is None else (f"{v:.{dec}f}".replace(".", ","))


# ---------------------------------------------------------------- mapas
DESPLAZA = {"Pasaia": (9, -1), "Miramon": (-4, -1), "Zizurkil": (6, 1)}   # (derecha, arriba) en puntos


class Mapa:
    def __init__(self, zonas, contorno=None):
        self.zonas = zonas; self.contorno = contorno
        pts = [p for f in zonas["features"] for r in self._anillos(f["geometry"]) for p in r]
        self.x0 = min(p[0] for p in pts); self.x1 = max(p[0] for p in pts)
        self.y0 = min(p[1] for p in pts); self.y1 = max(p[1] for p in pts)
        self.kx = math.cos(math.radians((self.y0 + self.y1) / 2))

    @staticmethod
    def _anillos(g):
        return [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]

    def continuo(self, ancho, valores, color_de, etiquetas=None, flechas=None, letra=6.3, dpi=220, nombres=True):
        """Mapa continuo: interpolación por distancia inversa (peso 1/d^4) entre las estaciones con valor,
        coloreada con color_de(v) -> (r, g, b), recortada con el contorno de Gipuzkoa. Devuelve una imagen."""
        W = int(ancho / 72 * dpi); esc = W / ((self.x1 - self.x0) * self.kx); H = int((self.y1 - self.y0) * esc) + 1
        P_ = lambda x, y: ((x - self.x0) * self.kx * esc, (self.y1 - y) * esc)
        est = [(f["properties"]["lon"], f["properties"]["lat"], valores[f["properties"]["estacion"]])
               for f in self.zonas["features"] if f["properties"].get("lat") is not None and valores.get(f["properties"]["estacion"]) is not None]
        img = PILImage.new("RGBA", (W, H), (255, 255, 255, 0))
        # máscara de Gipuzkoa (contorno, o la unión de las zonas si no hay contorno)
        mask = PILImage.new("L", (W, H), 0); dm = ImageDraw.Draw(mask)
        for f in (self.contorno or self.zonas)["features"]:
            for r in self._anillos(f["geometry"]):
                dm.polygon([P_(*p[:2]) for p in r], fill=255)
        if est:
            xs = (np.arange(W) + 0.5) / esc / self.kx + self.x0
            ys = self.y1 - (np.arange(H) + 0.5) / esc
            X, Y = np.meshgrid(xs, ys)
            num = np.zeros((H, W)); den = np.zeros((H, W))
            for lo, la, v in est:
                d2 = ((X - lo) * self.kx) ** 2 + (Y - la) ** 2 + 1e-12
                w = 1.0 / (d2 * d2); num += w * v; den += w
            campo = num / den
            # colores por valor (se agrupan valores redondeados para no llamar mil veces a color_de)
            q = np.round(campo, 2); unicos, inv = np.unique(q, return_inverse=True)
            pal = np.array([color_de(float(u)) for u in unicos], dtype=np.uint8)
            rgb = pal[inv.reshape(q.shape)]
            capa = PILImage.fromarray(np.dstack([rgb, np.full((H, W), 240, np.uint8)]).astype(np.uint8), "RGBA")
            img.paste(capa, (0, 0), mask)
        # contorno
        borde = mask.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0)
        img.paste(PILImage.new("RGBA", (W, H), (20, 35, 28, 255)), (0, 0), borde)
        dr = ImageDraw.Draw(img)
        k = dpi / 72
        def ft(nombre_fich, tam):
            for c in ("", "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/"):
                try:
                    return ImageFont.truetype(c + nombre_fich, int(tam * k))
                except OSError:
                    continue
            return ImageFont.load_default()
        fuente = ft("DejaVuSans-Bold.ttf", letra)
        fuente_n = ft("DejaVuSans.ttf", letra * 0.78)
        for f in self.zonas["features"]:
            pr = f["properties"]
            if pr.get("lat") is None:
                continue
            x, y = P_(pr["lon"], pr["lat"])
            dxl, dyl = DESPLAZA.get(pr["estacion"], (0, 0))     # etiquetas que se pisan con la vecina
            if flechas and pr["estacion"] in flechas and flechas[pr["estacion"]][0] is not None:
                g, roja = flechas[pr["estacion"]]
                a = math.radians(g + 180); ux, uy = math.sin(a), -math.cos(a); s_ = 6.5 * k
                pts = [(0, s_), (s_ * .45, -s_ * .5), (0, -s_ * .15), (-s_ * .45, -s_ * .5)]
                rot = [(x + py * ux + px * uy, y + py * uy - px * ux) for px, py in pts]
                dr.polygon(rot, fill=(217, 56, 43) if roja else (20, 35, 28), outline=(255, 255, 255))
                y += 9 * k
            if etiquetas and pr["estacion"] in etiquetas:
                x += dxl * k; y -= dyl * k
                t = etiquetas[pr["estacion"]]
                bb = dr.textbbox((0, 0), t, font=fuente); tw, th = bb[2] - bb[0], bb[3] - bb[1]
                nm = pr["estacion"] if nombres else ""
                bn = dr.textbbox((0, 0), nm, font=fuente_n) if nm else (0, 0, 0, 0); nw, nh = bn[2] - bn[0], bn[3] - bn[1]
                caja_w = max(tw, nw) + 3 * k; alto_n = (nh + 1.2 * k) if nm else 0
                dr.rounded_rectangle([x - caja_w / 2, y - th - alto_n - 2.4 * k, x + caja_w / 2, y + 1.2 * k], radius=1.8 * k, fill=(255, 255, 255, 225))
                if nm:
                    dr.text((x - nw / 2, y - th - alto_n - 1.6 * k - bn[1]), nm, font=fuente_n, fill=(70, 84, 90))
                dr.text((x - tw / 2, y - th - 1.6 * k - bb[1]), t, font=fuente, fill=(20, 35, 28))
        buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
        return RLImage(buf, width=ancho, height=ancho * H / W)

    def dibujo(self, ancho, colores, etiquetas=None, flechas=None, titulo=None, letra=6.3):
        """colores: {estación: Color}; etiquetas: {estación: texto}; flechas: {estación: (dirección, rojo?)}."""
        tit_h = 11 if titulo else 0
        esc = ancho / ((self.x1 - self.x0) * self.kx)
        alto = (self.y1 - self.y0) * esc
        d = Drawing(ancho, alto + tit_h)
        P_ = lambda x, y: ((x - self.x0) * self.kx * esc, (y - self.y0) * esc)
        for f in self.zonas["features"]:
            c = colores.get(f["properties"]["estacion"]) or colors.HexColor("#c9d0cc")
            for r in self._anillos(f["geometry"]):
                d.add(Polygon([v for p in r for v in P_(*p[:2])], fillColor=c, strokeColor=colors.white, strokeWidth=0.5))
        if self.contorno:
            for f in self.contorno["features"]:
                for r in self._anillos(f["geometry"]):
                    d.add(Polygon([v for p in r for v in P_(*p[:2])], fillColor=None, strokeColor=TINTA, strokeWidth=0.8))
        for f in self.zonas["features"]:
            pr = f["properties"]
            if pr.get("lat") is None:
                continue
            x, y = P_(pr["lon"], pr["lat"])
            if flechas and pr["estacion"] in flechas and flechas[pr["estacion"]][0] is not None:
                g, roja = flechas[pr["estacion"]]
                a = math.radians(g + 180)                       # hacia dónde va el viento
                ux, uy = math.sin(a), math.cos(a); s = 6.5
                pts = [(0, s), (s * .45, -s * .5), (0, -s * .15), (-s * .45, -s * .5)]
                rot = [(x + px * uy + py * ux, y - px * ux + py * uy) for px, py in pts]
                d.add(Polygon([v for p in rot for v in p], fillColor=colors.HexColor("#d9382b") if roja else TINTA,
                              strokeColor=colors.white, strokeWidth=0.4))
                y -= 9
            if etiquetas and pr["estacion"] in etiquetas:
                t = etiquetas[pr["estacion"]]
                w = pdfmetrics.stringWidth(t, "DVB", letra) + 3
                d.add(Rect(x - w / 2, y - 2, w, letra + 2.5, rx=1.5, ry=1.5, fillColor=colors.Color(1, 1, 1, 0.85), strokeColor=None))
                d.add(String(x, y, t, fontName="DVB", fontSize=letra, fillColor=TINTA, textAnchor="middle"))
        if titulo:
            d.add(String(0, alto + 2, titulo, fontName="DVB", fontSize=8, fillColor=TINTA))
        return d


def rgb_hex(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def color_indice(nombre):
    idxf = INDICES[nombre][1]
    return lambda v: rgb_hex(COL[idxf(v)])


def color_meteo(var):
    return lambda v: tuple(int(round(c * 255)) for c in color_tramo(var, v).rgb())


def leyenda_niveles(nombre):
    items = INDICES[nombre][3]
    celdas = [[Paragraph(f'<font color="{FG[i]}"><b>{r}</b></font><br/><font size="6" color="{FG[i]}">'
                         f'{(NIV_ICO if nombre == "ICONA" else NIV)[i]}</font>', ST["c"]) for i, r in items]]
    t = Table(celdas, colWidths=[174 * mm / len(items)] * len(items))
    t.setStyle(TableStyle([*[("BACKGROUND", (k, 0), (k, 0), colors.HexColor(COL[i])) for k, (i, _) in enumerate(items)],
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def leyenda_tramos(var, ancho=84 * mm):
    t = TRAMOS[var]; n = len(t) - 1
    d = Drawing(ancho, 20)
    w = (ancho - 22) / n
    for i in range(n):
        d.add(Rect(i * w, 9, w, 7, fillColor=color_tramo(var, (t[i] + t[i + 1]) / 2), strokeColor=colors.white, strokeWidth=0.4))
    paso = 1 if ancho >= 70 * mm else (2 if ancho >= 40 * mm else 3)   # leyendas pequeñas: menos valores
    for i, v in enumerate(t):
        if paso > 1 and i != n and (i % paso or i > n - paso):  # sin pisar el último valor
            continue
        d.add(String(i * w, 1, fnum(v, 0 if float(v).is_integer() else 1), fontName="DV", fontSize=5.5, fillColor=TINTA,
                     textAnchor="start" if i == 0 else ("end" if i == n else "middle")))
    d.add(String(ancho, 9, METEO[var][1], fontName="DV", fontSize=6, fillColor=GRIS, textAnchor="end"))
    return d


# ---------------------------------------------------------------- datos
def dias_informe(d):
    """[(fecha, {estación: datos})]: último dato medido y los 3 días siguientes de previsión."""
    ests = d["estaciones"]
    ult = max((e["dias"][-1]["fecha"] for e in ests if e.get("dias")), default=None)
    salida = [(ult, {nombre(e): next((x for x in reversed(e["dias"]) if x["fecha"] == ult), None) for e in ests})]
    fechas = sorted({p["fecha"] for e in ests for p in e.get("prevision", []) if p["fecha"] > ult})[:3]
    for f in fechas:
        salida.append((f, {nombre(e): next((p for p in e.get("prevision", []) if p["fecha"] == f), None) for e in ests}))
    return salida


def nombre(e):
    return "GIPUZKOA" if e.get("resumen") else e["nombre"]


def tabla_resumen(dias, ests):
    cab1 = [P("Estazioa<br/>Estación", "ch")] + [P(("<b>Azken datua / Último dato</b>" if i == 0 else "<b>Iragarpena / Previsión</b>")
                                                     + "<br/>" + ffecha(f), "ch") for i, (f, _) in enumerate(dias)]
    filas = [[c for c in cab1 for _ in ((0,) if c is cab1[0] else (0, 1, 2))]]
    filas[0] = [cab1[0]] + sum([[c, "", ""] for c in cab1[1:]], [])
    filas.append([""] + ["FWI", "Basugix", "ICONA"] * len(dias))
    estilo = [("BACKGROUND", (0, 0), (-1, 1), VERDE), ("TEXTCOLOR", (0, 1), (-1, 1), colors.white), ("FONTNAME", (0, 0), (-1, -1), "DV"),
              ("FONTSIZE", (0, 1), (-1, -1), 7), ("ALIGN", (1, 1), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("SPAN", (0, 0), (0, 1)), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cfd6da")),
              ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for k in range(len(dias)):
        estilo.append(("SPAN", (1 + 3 * k, 0), (3 + 3 * k, 0)))
    for r, e in enumerate(ests, start=2):
        n = nombre(e); fila = [P(f"<b>{n}</b>" if e.get("resumen") else n, "cl")]
        for k, (f, datos) in enumerate(dias):
            x = datos.get(n)
            for j, ind in enumerate(("FWI", "Basugix", "ICONA")):
                val, idxf, fmtf, _ = INDICES[ind]
                v = val(x) if x else None
                fila.append(fmtf(v) if v is not None else "—")
                if v is not None:
                    i = idxf(v); c = 1 + 3 * k + j
                    estilo += [("BACKGROUND", (c, r), (c, r), colors.HexColor(COL[i])), ("TEXTCOLOR", (c, r), (c, r), colors.HexColor(FG[i]))]
        filas.append(fila)
    t = Table(filas, colWidths=[24 * mm] + [12.5 * mm] * (3 * len(dias)), repeatRows=2)
    t.setStyle(TableStyle(estilo))
    return t


# ---------------------------------------------------------------- informe (2 páginas)
def leyenda_niveles_compacta(nombre, ancho):
    items = INDICES[nombre][3]
    d = Drawing(ancho, 11)
    w = ancho / len(items)
    for k, (i, r) in enumerate(items):
        d.add(Rect(k * w, 0, w - 1, 10, fillColor=colors.HexColor(COL[i]), strokeColor=None))
        d.add(String(k * w + w / 2 - 0.5, 3, r + "  " + (NIV_ICO if nombre == "ICONA" else NIV)[i],
                     fontName="DV", fontSize=5.3, fillColor=colors.HexColor(FG[i]), textAnchor="middle"))
    return d


from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend

COL_DIAS = ["#1f5f46", "#6f9e8c", "#a3c2b6", "#d0e2db"]     # dato real (oscuro) y 3 días de previsión (más claros)


def grafico_barras(dias, var, titulo, ancho, alto=46 * mm):
    """Barras agrupadas: una estación por grupo, una barra por día (dato real + previsión)."""
    nombres = sorted({n for _, datos in dias for n, x in datos.items() if n != "GIPUZKOA" and x and x.get(var) is not None})
    series = [[(datos.get(n) or {}).get(var) or 0 for n in nombres] for _, datos in dias]
    d = Drawing(ancho, alto)
    c = VerticalBarChart()
    c.x, c.y, c.width, c.height = 22, 30, ancho - 30, alto - 44
    c.data = series
    c.categoryAxis.categoryNames = nombres
    c.categoryAxis.labels.angle = 40; c.categoryAxis.labels.boxAnchor = "ne"; c.categoryAxis.labels.dx = 2; c.categoryAxis.labels.dy = -2
    c.categoryAxis.labels.fontName = "DV"; c.categoryAxis.labels.fontSize = 5.5
    c.valueAxis.valueMin = 0
    c.valueAxis.labels.fontName = "DV"; c.valueAxis.labels.fontSize = 5.5
    c.valueAxis.visibleGrid = True; c.valueAxis.gridStrokeColor = colors.HexColor("#dfe4e7"); c.valueAxis.gridStrokeWidth = 0.4
    c.categoryAxis.strokeColor = colors.HexColor("#8a969c"); c.valueAxis.strokeColor = colors.HexColor("#8a969c")
    c.barSpacing = 0.4; c.groupSpacing = 4; c.barWidth = 4
    for i in range(len(series)):
        c.bars[i].fillColor = colors.HexColor(COL_DIAS[i]); c.bars[i].strokeColor = None
    d.add(c)
    d.add(String(0, alto - 9, titulo, fontName="DVB", fontSize=8, fillColor=TINTA))
    return d


def leyenda_dias(dias, ancho):
    """Leyenda común de los gráficos: dato real y días de previsión."""
    d = Drawing(ancho, 10)
    x = 0
    for k, (f, _) in enumerate(dias):
        t = ("Gaurko datua · " if k == 0 else "Iragarpena · ") + ffecha(f)
        d.add(Rect(x, 1.5, 8, 6, fillColor=colors.HexColor(COL_DIAS[k]), strokeColor=None))
        d.add(String(x + 11, 2.5, t, fontName="DV", fontSize=6.5, fillColor=TINTA))
        x += 11 + pdfmetrics.stringWidth(t, "DV", 6.5) + 14
    return d


METODO_INDIZEAK = [
    "<b>Datuak.</b> Euskalmeten estazioak, eguzki-eguerdian (13:00 neguan, 14:00 udan). Tenperatura, hezetasun erlatiboa eta haizea "
    "ordu horretakoak dira; euria, aurreko 24 orduetan metatutakoa. Mutriku: Open-Meteo eredua (ez dago estaziorik); Altzola: haizea "
    "eredutik; Zarautz: euria Inurritzatik.",
    "<b>FWI</b> (Fire Weather Index, Kanadako sistema): erregai finaren, humus-geruzaren eta lehortearen hezetasun-kodeak (FFMC, DMC, DC), "
    "hedapen-indizea (ISI) eta erregai erabilgarria (BUI) konbinatzen ditu. Mailak: EFFIS (Europako Baso Suteen Informazio Sistema). "
    "<b>DC</b>: lur-geruza sakonen lehortea, aste eta hilabeteetako euririk ezak metatua (geldo aldatzen da). <b>ISI</b>: suaren hasierako "
    "hedapen-abiadura, erregai finaren hezetasunaren eta haizearen araberakoa (egunetik egunera asko aldatzen da).",
    "<b>Basugix</b>: Gipuzkoarako egokitutako indizea. Egun ertainarekiko sute-probabilitatea adierazten du, EGIF 2010-2025 sute-erregistroarekin "
    "kalibratua (FWI, abendutik apirilera bitarteko garaia eta hego haizea). 20 = egun ertaina; 10 puntu gehiago = probabilitatea bikoitza.",
    "<b>ICONA</b>: ICONAren indize sintetiko aldatua (1968). Lehortea, euria, hezetasuna eta haizea taulen bidez konbinatzen ditu (oinarria 0-16), "
    "eta lehorte luzearen eta hego haize lehorraren zuzenketak gehitzen zaizkio. Urtaroko taulak Gipuzkoara egokituta daude (larriena "
    "udazken-neguan). 13 edo gehiago = muturrekoa.",
    "<b>Iragarpena</b>: Open-Meteo eredua, egun bakoitzeko eguzki-eguerdirako, estazio bakoitzaren portaerarekin zuzendua. Gaurko "
    "estimazioan, dagoeneko neurtutako euria benetakoa da. <b>Mapak</b>: estazioen balioen arteko interpolazioa (distantziaren alderantzizkoa), "
    "Gipuzkoako mugarekin moztua; joera orokorrak erakusten dituzte, ez haran bakoitzeko xehetasuna.",
]
METODO_EGURALDIA = [
    "<b>Neurketak.</b> Euskalmeten estazioak, eguzki-eguerdian (13:00 neguan, 14:00 udan). Tenperatura, hezetasun erlatiboa eta haizea "
    "(abiadura eta norabidea) ordu horretakoak dira; euria, berriz, aurreko 24 orduetan metatutakoa (aurreko eguneko eguzki-eguerditik "
    "egun horretakora arte). Mutriku: Open-Meteo eredua; Altzola: haizea eredutik; Zarautz: euria Inurritzatik.",
    "<b>Iragarpena.</b> Open-Meteo eredua (CC BY 4.0): tenperatura, hezetasuna eta haizea egun bakoitzeko eguzki-eguerdirako, eta euria "
    "aurreko 24 orduetarako, neurketen irizpide berarekin.",
    "<b>Mapak.</b> Estazioen balioen arteko interpolazioa (distantziaren alderantzizkoa), Gipuzkoako mugarekin moztua, legendako tarteen "
    "koloreekin. Haizea: geziek haizeak nora jotzen duen adierazten dute (gorriz, hegoaldekoa). Joera orokorrak erakusten dituzte, ez haran "
    "bakoitzeko xehetasuna.",
]


def generar(d, ruta, zonas_path="docs/data/zonas.geojson", contorno_path="docs/data/gipuzkoa.geojson"):
    zonas = json.loads(Path(zonas_path).read_text(encoding="utf-8"))
    contorno = json.loads(Path(contorno_path).read_text(encoding="utf-8")) if Path(contorno_path).exists() else None
    mapa = Mapa(zonas, contorno)
    dias = dias_informe(d)
    hoy = dias[0][0]
    doc = SimpleDocTemplate(str(ruta), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=11 * mm, bottomMargin=12 * mm,
                            title=f"Gipuzkoako baso sute arriskua · {hoy}")

    def pie(c, doc_):
        c.saveState(); c.setFont("DV", 6.5); c.setFillColor(GRIS)
        c.drawString(12 * mm, 6.5 * mm, f"Gipuzkoako baso sute arriskua · {ffecha(hoy)} · Datuak: Euskalmet, Open-Meteo")
        c.drawRightString(A4[0] - 12 * mm, 6.5 * mm, f"{doc_.page}/2"); c.restoreState()

    est_m = ParagraphStyle("m", fontName="DV", fontSize=7, leading=9, textColor=TINTA, spaceAfter=3)
    GRIS_HOY = colors.HexColor("#eef1f3")

    def separar(estilo, filas_mapa):
        """Columna del dato real (columna 1): fondo gris claro. Entre ella y las previsiones hay dos columnas
        estrechas vacías (2 y 3) y la línea va entre ellas, así nunca toca los mapas. Solo en la cabecera y en
        las filas de mapas, no en las leyendas."""
        for r in [0] + filas_mapa:
            estilo += [("BACKGROUND", (1, r), (1, r), GRIS_HOY), ("LINEAFTER", (2, r), (2, r), 1.2, colors.HexColor("#8a969c"))]
        estilo += [("LEFTPADDING", (1, 0), (-1, -1), 2), ("RIGHTPADDING", (1, 0), (-1, -1), 2)]
        return estilo

    def cab(primera):
        c = [""] + [P((f"<b>{primera}</b>" if k == 0 else "<b>Iragarpena</b>") + "<br/>" + ffecha(f), "c") for k, (f, _) in enumerate(dias)]
        return c[:2] + ["", ""] + c[2:]                     # hueco de separación tras el dato real
    con_hueco = lambda fila: fila[:2] + ["", ""] + fila[2:]
    s = []
    # ---------- hoja 1: índices
    s.append(P("Baso sute arriskua Gipuzkoan", "t"))
    s.append(P(f"Azken datua: <b>{ffecha(hoy)}</b> (eguzki-eguerdia) · Iragarpena: {', '.join(ffecha(f) for f, _ in dias[1:]) or '—'}", "sub"))
    s.append(P("Indizeak: gaurko datua eta 3 eguneko iragarpena", "h"))
    ancho_m = 39 * mm
    filas, estilo = [cab("Gaurko datua")], [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for ind in ("FWI", "Basugix", "ICONA"):
        val, idxf, fmtf, _ = INDICES[ind]
        fila = [P(f"<b>{ind}</b>", "cl")]
        for f, datos in dias:
            vals, etq = {}, {}
            for n, x in datos.items():
                v = val(x) if x else None
                if v is not None and n != "GIPUZKOA":
                    vals[n] = v; etq[n] = fmtf(v)
            fila.append(mapa.continuo(ancho_m, vals, color_indice(ind), etq, letra=4.8))
        fila += [""] * (5 - len(fila))
        filas.append(con_hueco(fila))
        filas.append(["", leyenda_niveles_compacta(ind, 164 * mm), "", "", "", "", ""])
        r = len(filas) - 1
        estilo += [("SPAN", (1, r), (6, r)), ("BOTTOMPADDING", (0, r), (-1, r), 8)]
    estilo = separar(estilo, list(range(1, len(filas), 2)))
    t = Table(filas, colWidths=[18 * mm, 41 * mm, 2 * mm, 2 * mm, 41 * mm, 41 * mm, 41 * mm])
    t.setStyle(TableStyle(estilo))
    s.append(t)
    # DC eta ISI estazioz estazio: gaurko datua eta iragarpena
    s.append(Spacer(1, 2))
    gt = Table([[grafico_barras(dias, "dc", "DC — lehorte-kodea (Drought Code)", 91 * mm),
                 grafico_barras(dias, "isi", "ISI — hasierako hedapen-indizea (Initial Spread Index)", 91 * mm)],
                [leyenda_dias(dias, 184 * mm), ""]],
               colWidths=[93 * mm, 93 * mm])
    gt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("SPAN", (0, 1), (1, 1)), ("TOPPADDING", (0, 1), (-1, 1), 0)]))
    s.append(gt)
    s.append(Spacer(1, 2))
    s.append(P("Metodologia: indizeak", "h"))
    s += [Paragraph(x, est_m) for x in METODO_INDIZEAK]

    # ---------- hoja 2: meteorología
    s.append(PageBreak())
    s.append(P("Eguraldia: eguzki-eguerdiko neurketa eta 3 eguneko iragarpena", "h"))
    ancho_p = 32 * mm
    filas, estilo = [cab("Neurketa") + [""]], [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                               ("LEFTPADDING", (0, 0), (0, -1), 1), ("RIGHTPADDING", (0, 0), (0, -1), 1)]
    for var in ("T", "H", "W", "R"):
        fila = [P(f"<font size='6.5'><b>{METEO[var][0]}</b></font>", "cl")]
        for f, datos in dias:
            vals, etq, fl = {}, {}, {}
            for n, x in datos.items():
                if not x or n == "GIPUZKOA" or x.get(var) is None:
                    continue
                v = x[var]; vals[n] = v; etq[n] = fnum(v, 0 if var in ("H", "W") else 1)
                if var == "W":
                    fl[n] = (x.get("dir"), sector8(x.get("dir")) in ("SE", "S", "SO") and v >= 3)
            fila.append(mapa.continuo(ancho_p, vals, color_meteo(var), etq, flechas=fl if var == "W" else None, letra=4.6))
        fila += [""] * (5 - len(fila))
        fila = con_hueco(fila)
        fila.append(leyenda_tramos(var, ancho=22 * mm))
        filas.append(fila)
    estilo = separar(estilo, list(range(1, len(filas))))
    t = Table(filas, colWidths=[22 * mm, 34 * mm, 2 * mm, 2 * mm, 34 * mm, 34 * mm, 34 * mm, 24 * mm])
    t.setStyle(TableStyle(estilo))
    s.append(t)
    s.append(Spacer(1, 4))
    s.append(P("Metodologia: eguraldia", "h"))
    s += [Paragraph(x, est_m) for x in METODO_EGURALDIA]
    doc.build(s, onFirstPage=pie, onLaterPages=pie)
    return ruta
