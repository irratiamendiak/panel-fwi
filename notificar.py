#!/usr/bin/env python3
"""
Notificaciones del panel FWI / Basugix (solo en euskera).

  * Correo: informe del día (PDF adjunto), una vez al día, al cerrarse el dato
    (hora del dato + 60 min: 15:00 en verano, 14:00 en invierno).
  * Telegram: el mismo informe PDF completo, una vez al día, en el chat de avisos (TELEGRAM_CHAT);
    y avisos técnicos en TELEGRAM_CHAT_TEC (estaciones sin datos, fallo del proceso, PDF no generado).

Lee docs/data/fwi.json (lo escribe actualizar_fwi.py) y guarda en datos/notificaciones.json lo ya
enviado, para no repetir: el correo y el Telegram, una vez al día cada uno.

Configuración (secretos de GitHub, como variables de entorno); si faltan, ese canal se omite:
  SMTP_USER, SMTP_PASS (contraseña de aplicación), EMAIL_TO (varios, separados por comas);
  opcionales: SMTP_HOST (por defecto smtp.gmail.com), SMTP_PORT (465), EMAIL_FROM
  TELEGRAM_TOKEN, TELEGRAM_CHAT (grupo o canal del boletín), TELEGRAM_CHAT_TEC (avisos técnicos; si
  falta, se usa TELEGRAM_CHAT)

Uso:
  python notificar.py                  # lo normal, tras actualizar_fwi.py
  python notificar.py --prueba         # no envía nada: escribe prueba_correo.html / prueba_*.pdf y muestra los mensajes
  python notificar.py --fallo URL      # aviso técnico de que el proceso ha fallado
"""
import argparse, html, json, math, os, smtplib, ssl, sys, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("Europe/Madrid")
DATOS = Path("docs/data/fwi.json")
ESTADO = Path("datos/notificaciones.json")
WEB = "https://irratiamendiak.github.io/panel-fwi/"
UMBRAL_BGX = 30.0      # Basugix "Handia"
UMBRAL_FWI = 21.3      # FWI "Handia" (EFFIS)
UMBRAL_ICO = 9         # ICONA "Alto" (9-12); 13 o más, "Extremo"
NOM_ICO = {"eu": ["Hutsa", "Baxua", "Ertaina", "Handia", "Muturrekoa"], "es": ["Nulo", "Bajo", "Moderado", "Alto", "Extremo"]}
COL_ICO = [0, 1, 2, 3, 5]   # colores de COL para Nulo, Bajo, Moderado, Alto y Extremo
SALTO_NIVELES = 2      # subida brusca: 2 niveles o más de un día para otro
MARGEN_CIERRE = 60     # minutos tras la hora del dato

CLASES = ["Muy bajo", "Bajo", "Moderado", "Alto", "Muy alto", "Extremo"]
NOM = {"eu": ["Oso baxua", "Baxua", "Ertaina", "Handia", "Oso handia", "Muturrekoa"],
       "es": ["Muy bajo", "Bajo", "Moderado", "Alto", "Muy alto", "Extremo"]}
COL = ["#2f8f5b", "#8fbf3f", "#f0c53b", "#ee8a2e", "#d9382b", "#7a1f4d"]
FG = ["#fff", "#14231c", "#14231c", "#14231c", "#fff", "#fff"]
EGUN = ["astelehena", "asteartea", "asteazkena", "osteguna", "ostirala", "larunbata", "igandea"]
HIL = ["urtarrilaren", "otsailaren", "martxoaren", "apirilaren", "maiatzaren", "ekainaren", "uztailaren",
       "abuztuaren", "irailaren", "urriaren", "azaroaren", "abenduaren"]
DIA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
       "noviembre", "diciembre"]


# ---------------------------------------------------------------- utilidades
IFG = (-7.335, 1.122, 1.156, 0.479, 497 / 63837)   # mismos coeficientes que actualizar_fwi.py


def ifg_de(u):
    """Multiplicador IFG del día; si no viene en los datos, se calcula a partir del FWI, la época y el viento sur."""
    if u.get("ifg") is not None:
        return u["ifg"]
    if u.get("fwi") is None or not u.get("fecha"):
        return None
    b0, b1, be, bs, media = IFG
    x = b0 + b1 * math.log1p(max(u["fwi"], 0)) + (be if int(u["fecha"][5:7]) in (12, 1, 2, 3, 4) else 0) + (bs if hay_sur(u) else 0)
    return math.exp(x) / media


def bgx(ifg):
    return None if ifg is None else max(0.0, 20 + 10 * math.log2(max(ifg, 1e-6)))


def idx_bgx(v):
    v = round(v, 1)
    return 0 if v < 10 else 1 if v < 20 else 2 if v < 30 else 3 if v < 40 else 4 if v < 50 else 5


def idx_fwi(v):
    return 0 if v <= 5.2 else 1 if v <= 11.2 else 2 if v <= 21.3 else 3 if v <= 38 else 4 if v <= 50 else 5


def idx_fwi_de(u):
    """Nivel del FWI tal como lo calcula el proceso (con el valor sin redondear); si no viene, por umbrales."""
    return CLASES.index(u["clase"]) if u.get("clase") in CLASES else idx_fwi(u["fwi"])


def nivel_ico(v):
    """0 Nulo, 1 Bajo (1-4), 2 Moderado (5-8), 3 Alto (9-12), 4 Extremo (13 o más)."""
    v = round(v)
    return 0 if v <= 0 else 1 if v <= 4 else 2 if v <= 8 else 3 if v <= 12 else 4


def celda_ico(v, extra=""):
    if v is None:
        return "<td>—</td>"
    i = COL_ICO[nivel_ico(v)]
    txt = str(int(round(v)))
    return (f'<td style="padding:4px 6px;text-align:center"><span style="display:inline-block;min-width:34px;padding:2px 8px;'
            f'border-radius:999px;background:{COL[i]};color:{FG[i]};font-weight:700">{txt}</span>{extra}</td>')


def fnum(v, dec=1):
    return "—" if v is None else f"{v:.{dec}f}".replace(".", ",")


def ffecha(iso, l, larga=True):
    d = date.fromisoformat(iso)
    if l == "eu":
        return f"{EGUN[d.weekday()]}, {d.year}ko {HIL[d.month-1]} {d.day}a" if larga else f"{HIL[d.month-1].replace('aren','a').replace('ren','a')} {d.day}"
    return f"{DIA[d.weekday()]}, {d.day} de {MES[d.month-1]} de {d.year}" if larga else f"{DIA[d.weekday()][:3]}. {d.day}"


def sector(g):
    if g is None:
        return ""
    return ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int(((g % 360) + 22.5) // 45) % 8]


def hay_sur(d):
    return d.get("dir") is not None and -math.cos(math.radians(d["dir"])) >= 0.5 and (d.get("W") or 0) >= 3


def dias_sin_lluvia(dias):
    """Días seguidos (hasta el último, incluido) con lluvia de 24 h < 1 mm. None si no se sabe."""
    n = 0
    ant = None
    for d in reversed(dias):
        if ant and (date.fromisoformat(ant) - date.fromisoformat(d["fecha"])).days != 1:
            return None
        if d.get("R") is None:
            return None
        if d["R"] >= 1:
            return n
        n += 1
        ant = d["fecha"]
    return None


def cargar_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_estado(e):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- envío
def enviar_telegram(texto, chat=None, prueba=False):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), chat or os.environ.get("TELEGRAM_CHAT")
    if prueba or not tok or not chat:
        print(("[prueba] " if prueba else "[Telegram sin configurar] ") + "mensaje:\n" + texto + "\n")
        return
    datos = urllib.parse.urlencode({"chat_id": chat, "text": texto, "parse_mode": "HTML",
                                    "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", datos, timeout=30) as r:
        r.read()


def enviar_telegram_documento(nombre, datos, caption, chat=None, prueba=False):
    """Envía un PDF (bytes) al chat de Telegram, con un pie de texto (HTML, máx. 1024 caracteres)."""
    import uuid
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), chat or os.environ.get("TELEGRAM_CHAT")
    if prueba or not tok or not chat:
        if prueba:
            Path("prueba_telegram_" + nombre).write_bytes(datos)
        print(("[prueba] " if prueba else "[Telegram sin configurar] ") + f"documento: {nombre} ({len(datos)} bytes)\n{caption}\n")
        return
    borde = "----fwi" + uuid.uuid4().hex
    cuerpo = b""
    for k, v in (("chat_id", chat), ("caption", caption[:1024]), ("parse_mode", "HTML")):
        cuerpo += f'--{borde}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
    cuerpo += (f'--{borde}\r\nContent-Disposition: form-data; name="document"; filename="{nombre}"\r\n'
               f'Content-Type: application/pdf\r\n\r\n').encode("utf-8") + datos + f"\r\n--{borde}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendDocument", cuerpo,
                                 {"Content-Type": f"multipart/form-data; boundary={borde}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()


def enviar_correo(asunto, cuerpo_html, prueba=False, adjuntos=None):
    """adjuntos: [(nombre_fichero, bytes)] (p. ej. el informe PDF)."""
    # Gmail por defecto: basta con SMTP_USER, SMTP_PASS (contraseña de aplicación) y EMAIL_TO
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    usu, pw, dest = (os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASS", "EMAIL_TO"))
    pw = (pw or "").replace(" ", "")
    if prueba or not (host and usu and pw and dest):
        Path("prueba_correo.html").write_text(cuerpo_html, encoding="utf-8")
        for nom, datos in adjuntos or []:
            Path("prueba_" + nom).write_bytes(datos)
        print(("[prueba] " if prueba else "[correo sin configurar] ") + f"asunto: {asunto} -> prueba_correo.html"
              + "".join(f", prueba_{n}" for n, _ in adjuntos or []))
        return
    m = MIMEMultipart("mixed")
    m["Subject"], m["From"] = asunto, os.environ.get("EMAIL_FROM") or f"Basugix <{usu}>"
    lista = [x.strip() for x in dest.split(",") if x.strip()]
    m["To"] = m["From"]            # destinatarios en copia oculta, para no mostrar las direcciones
    m.attach(MIMEText(cuerpo_html, "html", "utf-8"))
    for nom, datos in adjuntos or []:
        parte = MIMEApplication(datos, _subtype="pdf" if nom.lower().endswith(".pdf") else "octet-stream")
        parte.add_header("Content-Disposition", "attachment", filename=nom)
        m.attach(parte)
    try:
        with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT") or 465), context=ssl.create_default_context(), timeout=60) as s:
            s.login(usu, pw)
            s.sendmail(usu, lista, m.as_string())
    except smtplib.SMTPAuthenticationError:
        raise
    except Exception:                                   # si se corta la conexión SSL, STARTTLS por el 587
        with smtplib.SMTP(host, 587, timeout=60) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(usu, pw)
            s.sendmail(usu, lista, m.as_string())


# ---------------------------------------------------------------- correo: informe del día y previsión
T = {
    "tit": {"eu": "Baso sute arriskua Gipuzkoan", "es": "Riesgo de incendio forestal en Gipuzkoa"},
    "sub": {"eu": "Eguzki-eguerdiko datuak", "es": "Datos del mediodía solar"},
    "est": {"eu": "Estazioa", "es": "Estación"}, "niv": {"eu": "Maila", "es": "Nivel"},
    "sinll": {"eu": "Euririk gabe", "es": "Sin lluvia"}, "dias": {"eu": "egun", "es": "días"},
    "viento": {"eu": "Haizea", "es": "Viento"}, "lluvia": {"eu": "Euria 24 h", "es": "Lluvia 24 h"},
    "prev": {"eu": "Hurrengo egunetako iragarpena", "es": "Previsión de los próximos días"},
    "sur": {"eu": "💨 hego haizea", "es": "💨 viento sur"}, "calc": {"eu": "kalkulatua", "es": "calculado"},
    "leyenda": {"eu": "FWI: nazioarteko indizea (EFFIS mailak). Basugix: Gipuzkoarako egokitua (20 = egun ertaina; 10 puntu gehiago = sute-probabilitatea bikoitza). ICONA: indize sintetikoa, 0-16 (hutsa 0, baxua 1-4, ertaina 5-8, handia 9-12, muturrekoa 13 edo gehiago).",
                "es": "FWI: índice internacional (niveles del EFFIS). Basugix: adaptado a Gipuzkoa (20 = día medio; 10 puntos más = el doble de probabilidad de incendio). ICONA: índice sintético, 0-16 (nulo 0, bajo 1-4, moderado 5-8, alto 9-12, extremo 13 o más)."},
    "web": {"eu": "Ikusi webgunean", "es": "Ver en la web"},
    "pie": {"eu": "Tresna orientagarria: ez ditu ordezkatzen abisu ofizialak. Datuak: Euskalmet; iragarpena: Open-Meteo.",
            "es": "Herramienta orientativa: no sustituye a los avisos oficiales. Datos: Euskalmet; previsión: Open-Meteo."},
}


def celda(v, i, extra=""):
    return (f'<td style="padding:4px 6px;text-align:center"><span style="display:inline-block;min-width:44px;padding:2px 8px;'
            f'border-radius:999px;background:{COL[i]};color:{FG[i]};font-weight:700">{fnum(v)}</span>{extra}</td>')


def bloque_correo(d, l, hoy):
    ests = d["estaciones"]
    th = 'style="padding:4px 6px;background:#eef1f4;font-size:12px;text-align:left"'
    h = [f'<h2 style="margin:0 0 2px;font:700 20px system-ui">{T["tit"][l]}</h2>',
         f'<p style="margin:0 0 10px;color:#444">{ffecha(hoy, l)} · {T["sub"][l]} ({d["hora_dato"]}:00)</p>',
         f'<table style="border-collapse:collapse;font:13px system-ui;width:100%"><tr><th {th}>{T["est"][l]}</th>'
         f'<th {th}>FWI</th><th {th}>Basugix</th><th {th}>ICONA</th><th {th}>T · HR</th><th {th}>{T["viento"][l]}</th><th {th}>{T["lluvia"][l]}</th><th {th}>{T["sinll"][l]}</th></tr>']
    for e in ests:
        u = e["dias"][-1] if e.get("dias") else None
        if not u or u["fecha"] != hoy:
            u = next((p for p in e.get("prevision", []) if p["fecha"] == hoy), None)   # aún sin medir: calculado
            calc = u is not None
        else:
            calc = False
        nom = "<b>GIPUZKOA</b>" if e.get("resumen") else html.escape(e["nombre"])
        if not u:
            h.append(f'<tr><td style="padding:4px 6px">{nom}</td><td colspan="7" style="color:#777">—</td></tr>')
            continue
        b = bgx(ifg_de(u))
        meteo = "" if e.get("resumen") else f'{fnum(u.get("T"))} °C · {fnum(u.get("H"),0)} %'
        vto = "" if e.get("resumen") or u.get("W") is None else f'{fnum(u["W"])} km/h {sector(u.get("dir"))}' + (f' {T["sur"][l]}' if hay_sur(u) else "")
        ll = "" if e.get("resumen") else f'{fnum(u.get("R"))} mm'
        sl = "" if e.get("resumen") else dias_sin_lluvia(e["dias"])
        sl = "" if sl in ("", None) else ("🌧️" if sl == 0 else f"{sl} {T['dias'][l]}")
        h.append(f'<tr style="border-bottom:1px solid #ddd"><td style="padding:4px 6px">{nom}'
                 f'{" <i style=color:#777>(" + T["calc"][l] + ")</i>" if calc else ""}</td>'
                 + celda(u["fwi"], idx_fwi_de(u)) + (celda(b, idx_bgx(b)) if b is not None else "<td>—</td>")
                 + celda_ico(u.get("icona"))
                 + f'<td style="padding:4px 6px">{meteo}</td><td style="padding:4px 6px">{vto}</td>'
                 f'<td style="padding:4px 6px">{ll}</td><td style="padding:4px 6px">{sl}</td></tr>')
    h.append("</table>")
    fechas = sorted({p["fecha"] for e in ests for p in e.get("prevision", []) if p["fecha"] > hoy})[:3]
    if fechas:
        h.append(f'<h3 style="margin:16px 0 4px;font:700 16px system-ui">{T["prev"][l]}</h3>'
                 f'<table style="border-collapse:collapse;font:13px system-ui;width:100%"><tr><th {th}>{T["est"][l]}</th>'
                 + "".join(f'<th {th} colspan="3">{ffecha(f, l, False)}<br><span style="font-weight:400">FWI · Basugix · ICONA</span></th>' for f in fechas) + "</tr>")
        for e in ests:
            pv = {p["fecha"]: p for p in e.get("prevision", [])}
            nom = "<b>GIPUZKOA</b>" if e.get("resumen") else html.escape(e["nombre"])
            fila = f'<tr style="border-bottom:1px solid #ddd"><td style="padding:4px 6px">{nom}</td>'
            for f in fechas:
                p = pv.get(f)
                if not p:
                    fila += '<td colspan="3" style="text-align:center;color:#777">—</td>'
                    continue
                b = bgx(ifg_de(p))
                fila += celda(p["fwi"], idx_fwi_de(p)) + (celda(b, idx_bgx(b), " 💨" if hay_sur(p) else "") if b is not None else "<td>—</td>")
                fila += celda_ico(p.get("icona"))
            h.append(fila + "</tr>")
        h.append("</table>")
    h.append(f'<p style="font:12px system-ui;color:#555;margin:10px 0 2px">{T["leyenda"][l]}</p>'
             f'<p style="font:12px system-ui;color:#555;margin:2px 0">{T["pie"][l]}</p>')
    return "\n".join(h)


MESES_EU = ["urtarrilaren", "otsailaren", "martxoaren", "apirilaren", "maiatzaren", "ekainaren", "uztailaren", "abuztuaren",
            "irailaren", "urriaren", "azaroaren", "abenduaren"]


def informe_pdf_bytes(d):
    """El informe PDF diario (informe_pdf.py) en memoria."""
    import tempfile, informe_pdf
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "informe.pdf"
        informe_pdf.generar(d, ruta)
        return ruta.read_bytes()


def preparar_boletin(d, hoy):
    """Datos del boletín del día: el PDF (o None si no se puede generar), los valores de GIPUZKOA y la fecha en euskera."""
    g = next((e for e in d["estaciones"] if e.get("resumen")), None)
    u = g["dias"][-1] if g and g.get("dias") else None
    valores = ""
    if u and u["fecha"] == hoy:
        b = bgx(ifg_de(u))
        valores = (f"FWI {fnum(u['fwi'])}" + (f" · Basugix {fnum(b)}" if b is not None else "")
                   + (f" · ICONA {int(round(u['icona']))}" if u.get("icona") is not None else ""))
    f = date.fromisoformat(hoy)
    try:
        pdf = informe_pdf_bytes(d)
    except Exception as e:
        print("No se ha podido generar el informe PDF:", type(e).__name__, e)
        pdf = None
    return {"pdf": pdf, "valores": valores, "fecha_eu": f"{f.year}ko {MESES_EU[f.month - 1]} {f.day}a", "u": u}


def correo_diario(d, hoy, prueba, bol):
    """Correo diario tras el cierre del dato: el informe PDF adjunto, con un texto breve en euskera.
    Si el PDF no se puede generar, se envía el correo de tablas (también en euskera)."""
    valores, fecha_eu, pdf = bol["valores"], bol["fecha_eu"], bol["pdf"]
    if pdf:
        cuerpo = ('<div style="max-width:640px;font-family:system-ui,Segoe UI,Roboto,sans-serif;color:#14231c;font-size:15px;line-height:1.5">'
                  f'<p style="font-size:18px;font-weight:700;margin:0 0 6px">Baso sute arriskua Gipuzkoan · {fecha_eu}</p>'
                  + (f'<p style="margin:0 0 10px">GIPUZKOA: <b>{valores}</b></p>' if valores else "")
                  + '<p style="margin:0 0 10px">Eranskinean, eguneko txostena (PDF, bi orri): FWI, Basugix eta ICONA indizeen mapak '
                  '(gaurko datua eta 3 eguneko iragarpena), DC eta ISI estazioz estazio, eta eguraldia (eguzki-eguerdiko neurketa eta '
                  '3 eguneko iragarpena), metodologiarekin.</p>'
                  '<p style="margin:0;color:#56636b;font-size:13px">Datuak: Euskalmet, Open-Meteo</p></div>')
        enviar_correo(f"Baso sute arriskua Gipuzkoan · {fecha_eu}" + (f" · {valores}" if valores else ""), cuerpo, prueba,
                      adjuntos=[(f"Basugix_{hoy}.pdf", pdf)])
        return
    cuerpo = ('<div style="max-width:760px;margin:0 auto;font-family:system-ui,Segoe UI,Roboto,sans-serif;color:#14231c">'
              + bloque_correo(d, "eu", hoy) + "</div>")
    enviar_correo(f"Baso sute arriskua · {hoy}" + (f" · GIPUZKOA {valores}" if valores else ""), cuerpo, prueba)


def telegram_boletin(hoy, prueba, bol, est):
    """Telegram: el mismo informe PDF completo que va por correo, con un pie breve en euskera.
    Devuelve True si se ha enviado; si no hay PDF, avisa (una vez al día) en el chat técnico."""
    if not bol["pdf"]:
        if est.get("tec_pdf") != hoy:
            est["tec_pdf"] = hoy
            aviso_tecnico("Ezin izan da gaurko txosten PDFa sortu. Ikusi GitHub-eko erregistroa.", prueba)
        return False
    pie = (f"🔥 <b>Baso sute arriskua Gipuzkoan</b>\n{bol['fecha_eu']}"
           + (f"\nGIPUZKOA: <b>{bol['valores']}</b>" if bol["valores"] else ""))
    enviar_telegram_documento(f"Basugix_{hoy}.pdf", bol["pdf"], pie, prueba=prueba)
    return True


# ---------------------------------------------------------------- Telegram: avisos técnicos
def aviso_tecnico(texto, prueba):
    enviar_telegram(f"🛠️ {texto}", os.environ.get("TELEGRAM_CHAT_TEC"), prueba)


def estaciones_sin_datos(d, hoy, est, prueba):
    lim = (date.fromisoformat(hoy) - timedelta(days=1)).isoformat()
    sin = [e["nombre"] for e in d["estaciones"] if not e.get("resumen") and not e.get("modelo")
           and (not e.get("dias") or e["dias"][-1]["fecha"] < lim)]
    if sin and est.get("tec_sin_datos") != hoy:
        est["tec_sin_datos"] = hoy
        aviso_tecnico("Egun bat baino gehiago daturik gabe: " + ", ".join(sin), prueba)


# ---------------------------------------------------------------- principal
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", help="No envía nada; muestra y guarda lo que enviaría")
    p.add_argument("--forzar", action="store_true", help="Envía aunque ya se haya enviado hoy o no sea la hora")
    p.add_argument("--fallo", metavar="URL", help="Aviso técnico: el proceso ha fallado")
    p.add_argument("--prueba-envio", action="store_true", help="Envía un correo y un Telegram de prueba (configuración)")
    a = p.parse_args()
    if a.prueba_envio:
        ok = True
        adj = []
        try:
            datos = json.loads(DATOS.read_text(encoding="utf-8"))
            adj = [(f"Basugix_proba_{datetime.now(ZONA).date().isoformat()}.pdf", informe_pdf_bytes(datos))]
        except Exception as e:
            print("Informe PDF: ERROR", type(e).__name__, e)
        try:
            enviar_telegram("✅ <b>Basugix</b>: Telegram abisuak ondo daude (GitHub-etik bidalia).")
            if adj:
                enviar_telegram_documento(adj[0][0], adj[0][1], "✅ <b>Basugix</b>: proba-txostena (PDF).")
            print("Telegram: bidalia" if os.environ.get("TELEGRAM_TOKEN") else "Telegram: sin configurar")
        except Exception as e:
            ok = False; print("Telegram: ERROR", e)
        try:
            if os.environ.get("SMTP_USER"):
                enviar_correo("Basugix: proba", "<p>✅ <b>Basugix</b>: posta elektronikoa ondo dago (GitHub-etik bidalia).</p>"
                              + ("<p>Eranskinean, azken datuekin egindako txostena (PDF).</p>" if adj else
                                 "<p>⚠️ Ezin izan da txosten PDFa sortu (ikus GitHub-eko erregistroa).</p>"), adjuntos=adj)
                print("Correo: enviado")
            else:
                print("Correo: sin configurar")
        except Exception as e:
            ok = False; print("Correo: ERROR", e)
        return 0 if ok else 1
    if a.fallo:
        aviso_tecnico(f"Eguneratze-prozesuak huts egin du. Ikusi: {a.fallo}", a.prueba)
        return 0
    d = json.loads(DATOS.read_text(encoding="utf-8"))
    ahora = datetime.now(ZONA)
    hoy = ahora.date().isoformat()
    cierre = ahora.replace(hour=int(d.get("hora_dato", 14)), minute=0, second=0, microsecond=0) + timedelta(minutes=MARGEN_CIERRE)
    est = cargar_estado()
    if ahora < cierre and not a.forzar:
        print("Aún no se ha cerrado el dato del día: no se notifica nada.")
        return 0
    nuevo_correo = est.get("correo") != hoy or a.forzar
    nuevo_tg = est.get("telegram") != hoy or a.forzar
    if nuevo_correo or nuevo_tg:
        bol = preparar_boletin(d, hoy)             # el PDF se genera una sola vez para los dos canales
        if nuevo_correo:
            try:
                correo_diario(d, hoy, a.prueba, bol)
                if not a.prueba:
                    est["correo"] = hoy
            except Exception as e:
                print("No se ha podido enviar el correo:", e)
        if nuevo_tg:
            try:
                if telegram_boletin(hoy, a.prueba, bol, est) and not a.prueba:
                    est["telegram"] = hoy
            except Exception as e:
                print("No se ha podido enviar el boletín por Telegram:", e)
    if est.get("avisos") != hoy or a.forzar:
        try:
            estaciones_sin_datos(d, hoy, est, a.prueba)
            if not a.prueba:
                est["avisos"] = hoy
        except Exception as e:
            print("No se han podido enviar los avisos técnicos:", e)
    if not a.prueba:
        guardar_estado(est)
    return 0


if __name__ == "__main__":
    sys.exit(main())
