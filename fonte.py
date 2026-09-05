# -*- coding: utf-8 -*-
"""Lettura della sezione Interpelli dell'ATS di Cagliari.

La pagina è servita lato server: ogni avviso è un <article class="article">
con la data in .article_data e il link nell'<h3><a>. Nessun browser necessario.
"""
import re
import html as htmllib
import urllib.request
import datetime as dt

import config

MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

ART = re.compile(r'<article class="article">(.*?)</article>', re.S)
DATA = re.compile(r'class="article_data"[^>]*>\s*(.*?)\s*<', re.S)
LINK = re.compile(r'<h3>\s*<a href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', re.S)


def _pulisci(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def _data(testo):
    """'29 maggio 2026' -> date(2026, 5, 29). None se non riconosciuta."""
    m = re.match(r"(\d{1,2})\s+([a-zà-ù]+)\s+(\d{4})", testo.strip().lower())
    if not m:
        return None
    g, mese, a = m.groups()
    if mese not in MESI:
        return None
    return dt.date(int(a), MESI[mese], int(g))


def scarica(url=None, timeout=40):
    req = urllib.request.Request(url or config.FONTE, headers={"User-Agent": config.UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def elenco(pagina_html=None):
    """Ritorna la lista degli avvisi pubblicati, dal più recente."""
    h = pagina_html if pagina_html is not None else scarica()
    fuori = []
    for blocco in ART.findall(h):
        ml = LINK.search(blocco)
        if not ml:
            continue
        url, titolo = ml.group(1).strip(), _pulisci(ml.group(2))
        md = DATA.search(blocco)
        pubblicato = _data(_pulisci(md.group(1))) if md else None
        if not titolo:
            continue
        fuori.append({
            "url": htmllib.unescape(url),
            "titolo": titolo,
            "pubblicato": pubblicato,
        })
    return fuori


def allegati(url_avviso, timeout=40):
    """Gli allegati di una scheda avviso: (nome, url). Il PDF dell'interpello e
    l'eventuale modulo di partecipazione stanno qui."""
    h = scarica(url_avviso, timeout=timeout)
    out, visti = [], set()
    for m in re.finditer(r'href="(https://www\.mim\.gov\.it/documents/[^"]+)"[^>]*>\s*(.*?)\s*<', h, re.S):
        u = htmllib.unescape(m.group(1))
        nome = _pulisci(m.group(2)) or u.rsplit("/", 1)[-1][:60]
        if u in visti:
            continue
        visti.add(u)
        out.append((nome, u))
    return out


if __name__ == "__main__":
    voci = elenco()
    print("avvisi trovati in pagina:", len(voci))
    for v in voci[:10]:
        print(" ", v["pubblicato"], "|", v["titolo"][:78])
