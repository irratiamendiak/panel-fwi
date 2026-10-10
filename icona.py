"""
Índice Sintético Modificado de peligro de incendios forestales del ICONA (peligro meteorológico diario).

Fuente: Manual de predicción del peligro de incendios forestales, ICONA (1982); tablas facilitadas por
el usuario (icona.xlsx). Cuatro tablas encadenadas:
  1. Índice de sequía de hoy (0-25): sequía de ayer + lluvia de 24 h (día seco: menos de 1,3 mm).
  2. Primera letra clave (a-t): índice de peligro de ayer + lluvia de 24 h.
  3. Letra clave final: primera letra + humedad relativa + velocidad del viento.
  4. Índice de peligro de hoy (0-16): letra final + sequía de hoy, con tablas de otoño-invierno y de
     primavera-verano (se toman los equinoccios: primavera-verano del 21 de marzo al 22 de septiembre).
Niveles: 0 Nulo · 1-4 Bajo · 5-8 Moderado · 9-12 Alto · 13 o más Extremo.
Las tablas no incluyen la corrección por dirección del viento (vientos terrales) de la versión de 1968.
"""

# 1) sequía: fila = sequía de ayer (0..25); columnas = lluvia <=1,3 | <=2,5 | <=3,6 | <=4,6 | <=5,6 | <=7,6 | <=9,6 | <=11,7 | <=13,5 | >=13,6 mm
SEQ_LIM = [1.3, 2.5, 3.6, 4.6, 5.6, 7.6, 9.6, 11.7, 13.5]
SEQ = [
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [2, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [3, 2, 1, 0, 0, 0, 0, 0, 0, 0],
    [4, 3, 1, 0, 0, 0, 0, 0, 0, 0],
    [5, 4, 2, 1, 0, 0, 0, 0, 0, 0],
    [6, 5, 3, 1, 0, 0, 0, 0, 0, 0],
    [7, 6, 4, 2, 1, 0, 0, 0, 0, 0],
    [8, 7, 5, 3, 2, 0, 0, 0, 0, 0],
    [9, 8, 6, 4, 2, 1, 0, 0, 0, 0],
    [10, 9, 7, 5, 3, 1, 0, 0, 0, 0],
    [11, 10, 8, 6, 4, 2, 0, 0, 0, 0],
    [12, 11, 9, 7, 5, 3, 0, 0, 0, 0],
    [13, 12, 10, 8, 6, 3, 1, 0, 0, 0],
    [14, 13, 11, 9, 7, 4, 1, 0, 0, 0],
    [15, 14, 12, 10, 8, 5, 2, 0, 0, 0],
    [16, 15, 13, 11, 9, 6, 3, 0, 0, 0],
    [17, 16, 14, 12, 10, 7, 4, 1, 0, 0],
    [18, 17, 15, 13, 11, 8, 4, 1, 0, 0],
    [19, 18, 16, 14, 12, 9, 5, 2, 0, 0],
    [20, 19, 17, 15, 13, 10, 6, 3, 0, 0],
    [21, 20, 18, 16, 14, 11, 7, 4, 1, 0],
    [22, 21, 19, 17, 15, 12, 8, 4, 1, 0],
    [23, 22, 20, 18, 16, 13, 9, 5, 2, 0],
    [24, 23, 21, 19, 17, 14, 10, 6, 3, 0],
    [25, 24, 22, 20, 18, 15, 11, 7, 3, 0],
    [25, 25, 23, 21, 19, 16, 12, 8, 4, 0],
]

# 2) primera letra: fila = peligro de ayer (0..16); columnas = lluvia 0 | 0,1-0,5 | 0,6-1 | 1,1-1,8 | 1,9-3 | 3,1-12,7 | >=12,8 mm
LL_LIM = [0.0, 0.5, 1.0, 1.8, 3.0, 12.7]
LL = [
    ['d', 'c', 'c', 'b', 'b', 'a', 'a'],
    ['e', 'd', 'd', 'b', 'b', 'b', 'a'],
    ['f', 'e', 'd', 'c', 'b', 'b', 'a'],
    ['g', 'e', 'd', 'c', 'c', 'b', 'a'],
    ['h', 'f', 'e', 'c', 'c', 'b', 'a'],
    ['i', 'f', 'e', 'c', 'c', 'b', 'a'],
    ['j', 'g', 'e', 'd', 'c', 'b', 'a'],
    ['k', 'g', 'e', 'd', 'c', 'b', 'a'],
    ['l', 'g', 'e', 'd', 'c', 'b', 'a'],
    ['m', 'g', 'e', 'd', 'c', 'b', 'a'],
    ['n', 'h', 'e', 'e', 'c', 'b', 'a'],
    ['o', 'h', 'f', 'e', 'c', 'b', 'a'],
    ['p', 'h', 'f', 'e', 'c', 'b', 'a'],
    ['q', 'i', 'f', 'e', 'c', 'b', 'a'],
    ['r', 'i', 'g', 'e', 'c', 'b', 'a'],
    ['s', 'i', 'g', 'e', 'c', 'b', 'a'],
    ['t', 'i', 'g', 'e', 'c', 'b', 'a'],
]

# 3) letra final: por primera letra; 25 columnas = 5 clases de HR (<=30, 31-40, 41-55, 56-75, >=76 %)
#    x 5 clases de viento (0-6, 7-13, 14-20, 21-28, >=29 km/h)
HV = {
    'a': ['f', 'f', 'g', 'g', 'h', 'e', 'e', 'f', 'f', 'g', 'e', 'e', 'f', 'f', 'g', 'c', 'e', 'e', 'f', 'g', 'b', 'c', 'd', 'd', 'e'],
    'b': ['g', 'g', 'h', 'h', 'i', 'f', 'f', 'g', 'g', 'h', 'f', 'f', 'g', 'g', 'h', 'd', 'e', 'f', 'f', 'g', 'c', 'd', 'e', 'e', 'f'],
    'c': ['h', 'h', 'i', 'j', 'k', 'g', 'g', 'h', 'i', 'j', 'f', 'g', 'h', 'h', 'i', 'e', 'f', 'g', 'g', 'h', 'e', 'e', 'e', 'e', 'f'],
    'd': ['i', 'i', 'j', 'k', 'l', 'g', 'h', 'i', 'j', 'k', 'f', 'g', 'h', 'i', 'j', 'e', 'f', 'g', 'g', 'h', 'e', 'f', 'f', 'f', 'g'],
    'e': ['j', 'j', 'k', 'l', 'm', 'h', 'i', 'j', 'k', 'l', 'g', 'h', 'j', 'j', 'k', 'f', 'g', 'g', 'g', 'h', 'f', 'f', 'f', 'f', 'g'],
    'f': ['k', 'k', 'l', 'l', 'm', 'i', 'j', 'k', 'k', 'l', 'g', 'h', 'k', 'k', 'l', 'f', 'h', 'h', 'h', 'i', 'f', 'g', 'g', 'g', 'h'],
    'g': ['l', 'm', 'm', 'n', 'o', 'j', 'k', 'l', 'l', 'm', 'h', 'i', 'k', 'l', 'm', 'g', 'h', 'h', 'h', 'i', 'g', 'g', 'g', 'h', 'i'],
    'h': ['m', 'n', 'n', 'o', 'p', 'k', 'l', 'm', 'n', 'o', 'i', 'j', 'l', 'l', 'm', 'g', 'h', 'i', 'i', 'j', 'g', 'h', 'h', 'h', 'i'],
    'i': ['m', 'n', 'o', 'p', 'q', 'k', 'l', 'm', 'n', 'o', 'j', 'k', 'm', 'm', 'n', 'h', 'i', 'j', 'j', 'k', 'g', 'h', 'h', 'i', 'j'],
    'j': ['n', 'o', 'p', 'q', 'r', 'l', 'm', 'n', 'o', 'p', 'k', 'l', 'm', 'm', 'n', 'i', 'j', 'k', 'k', 'l', 'g', 'h', 'h', 'i', 'j'],
    'k': ['o', 'p', 'q', 'r', 's', 'm', 'n', 'o', 'o', 'p', 'k', 'l', 'm', 'm', 'n', 'i', 'j', 'k', 'k', 'l', 'g', 'h', 'h', 'i', 'j'],
    'l': ['q', 'r', 's', 's', 't', 'n', 'o', 'p', 'q', 'r', 'k', 'l', 'n', 'n', 'o', 'j', 'k', 'k', 'l', 'm', 'h', 'i', 'i', 'j', 'k'],
    'm': ['r', 's', 't', 't', 't', 'o', 'p', 'q', 'r', 's', 'l', 'm', 'n', 'n', 'o', 'j', 'k', 'k', 'l', 'm', 'h', 'i', 'i', 'j', 'k'],
    'n': ['s', 't', 't', 't', 't', 'o', 'p', 'q', 'r', 's', 'l', 'm', 'n', 'n', 'o', 'k', 'l', 'l', 'm', 'n', 'i', 'j', 'j', 'j', 'k'],
    'o': ['t', 't', 't', 't', 't', 'p', 'q', 'r', 'r', 's', 'm', 'n', 'o', 'o', 'p', 'k', 'l', 'l', 'm', 'n', 'i', 'j', 'j', 'k', 'l'],
    'p': ['t', 't', 't', 't', 't', 'q', 'r', 'r', 's', 's', 'm', 'n', 'o', 'o', 'p', 'l', 'm', 'm', 'n', 'o', 'j', 'k', 'k', 'k', 'l'],
    'q': ['t', 't', 't', 't', 't', 'q', 'r', 's', 's', 't', 'n', 'o', 'p', 'p', 'q', 'l', 'm', 'm', 'n', 'o', 'j', 'k', 'k', 'l', 'm'],
    'r': ['t', 't', 't', 't', 't', 'r', 's', 's', 's', 't', 'n', 'o', 'p', 'p', 'q', 'm', 'n', 'n', 'n', 'o', 'k', 'l', 'l', 'l', 'm'],
    's': ['t', 't', 't', 't', 't', 'r', 's', 't', 't', 't', 'o', 'p', 'p', 'q', 'r', 'm', 'n', 'n', 'o', 'p', 'k', 'l', 'l', 'm', 'n'],
    't': ['t', 't', 't', 't', 't', 's', 't', 't', 't', 't', 'o', 'p', 'q', 'q', 'r', 'n', 'o', 'o', 'p', 'q', 'l', 'm', 'm', 'n', 'o'],
}

# 4) peligro de hoy: por letra final; 6 columnas = sequía 0-3, 4-6, 7-10, 11-16, 17-24, >=25
PEL_OI = {   # otoño-invierno
    'b': [0, 0, 1, 3, 4, 5],
    'c': [0, 0, 1, 3, 4, 5],
    'd': [0, 1, 2, 3, 4, 5],
    'e': [1, 2, 3, 4, 5, 6],
    'f': [3, 4, 5, 6, 7, 8],
    'g': [4, 5, 6, 7, 8, 9],
    'h': [5, 6, 7, 8, 9, 10],
    'i': [6, 7, 8, 9, 10, 11],
    'j': [6, 7, 8, 9, 10, 11],
    'k': [7, 8, 9, 10, 11, 12],
    'l': [8, 9, 10, 11, 12, 13],
    'm': [9, 10, 11, 12, 13, 14],
    'n': [9, 10, 11, 12, 13, 14],
    'o': [10, 11, 12, 13, 14, 15],
    'p': [10, 11, 12, 13, 14, 15],
    'q': [11, 12, 13, 14, 15, 16],
    'r': [11, 12, 13, 14, 15, 16],
    's': [12, 13, 14, 15, 16, 16],
    't': [12, 13, 14, 15, 16, 16],
}
PEL_PV = {   # primavera-verano
    'b': [0, 0, 1, 3, 4, 5],
    'c': [0, 0, 1, 3, 4, 5],
    'd': [0, 1, 2, 3, 4, 5],
    'e': [1, 2, 3, 4, 5, 6],
    'f': [2, 3, 4, 5, 6, 7],
    'g': [3, 4, 5, 6, 7, 8],
    'h': [4, 4, 5, 6, 7, 8],
    'i': [4, 5, 6, 7, 8, 9],
    'j': [5, 6, 7, 8, 8, 9],
    'k': [5, 7, 8, 9, 9, 10],
    'l': [6, 7, 8, 9, 10, 11],
    'm': [7, 8, 9, 9, 10, 11],
    'n': [7, 8, 9, 10, 11, 12],
    'o': [8, 9, 10, 11, 12, 13],
    'p': [9, 10, 11, 12, 13, 14],
    'q': [9, 10, 11, 12, 13, 14],
    'r': [10, 11, 12, 13, 14, 15],
    's': [11, 12, 13, 14, 15, 16],
    't': [11, 12, 13, 14, 15, 16],
}

NIVELES = [(0, "Nulo"), (4, "Bajo"), (8, "Moderado"), (12, "Alto"), (99, "Extremo")]


def _clase(v, lims):
    for i, l in enumerate(lims):
        if v <= l + 1e-9:
            return i
    return len(lims)


def _clase_hr(h):
    h = round(h)
    return 0 if h <= 30 else 1 if h <= 40 else 2 if h <= 55 else 3 if h <= 75 else 4


def _clase_viento(w):
    w = round(w)
    return 0 if w <= 6 else 1 if w <= 13 else 2 if w <= 20 else 3 if w <= 28 else 4


def _clase_seq(s):
    return 0 if s <= 3 else 1 if s <= 6 else 2 if s <= 10 else 3 if s <= 16 else 4 if s <= 24 else 5


def primavera_verano(d):
    return (3, 21) <= (d.month, d.day) <= (9, 22)


def paso(seq_ayer, pel_ayer, lluvia, hr, viento, dia):
    """Un día del índice: (sequía de hoy, peligro de hoy). lluvia: mm en 24 h; hr: %; viento: km/h."""
    r = round(max(lluvia or 0.0, 0.0), 1)
    seq = SEQ[min(int(seq_ayer), 25)][_clase(r, SEQ_LIM)]
    l1 = LL[min(int(round(pel_ayer)), 16)][_clase(r, LL_LIM)]
    lf = HV[l1][_clase_hr(hr) * 5 + _clase_viento(viento)]
    pel = (PEL_PV if primavera_verano(dia) else PEL_OI)[lf][_clase_seq(seq)]
    return seq, pel


def nivel(v):
    """Nivel oficial del índice (admite valores no enteros, como la media de GIPUZKOA)."""
    v = round(v)
    for tope, nombre in NIVELES:
        if v <= tope:
            return nombre
    return "Extremo"
