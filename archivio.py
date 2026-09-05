# -*- coding: utf-8 -*-
"""Archivio degli avvisi già visti.

Un file JSON invece di un database: viaggia col repository, quindi il
sorvegliante in cloud ricorda cosa ha già notificato anche se la macchina
che lo esegue è diversa a ogni giro.
"""
import json
import datetime as dt

import config

VUOTO = {"visti": {}, "stato": {}}


def carica():
    if not config.ARCHIVIO.exists():
        return dict(VUOTO)
    try:
        d = json.loads(config.ARCHIVIO.read_text())
        d.setdefault("visti", {})
        d.setdefault("stato", {})
        return d
    except Exception:
        return dict(VUOTO)


def salva(d):
    config.ARCHIVIO.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True))


def gia_visto(d, url):
    return url in d["visti"]


def segna(d, url, voce, a=None, esito=""):
    d["visti"][url] = {
        "titolo": voce["titolo"],
        "pubblicato": str(voce.get("pubblicato") or ""),
        "classe": (a.classe if a else "") or "",
        "scadenza": str(a.scadenza) if (a and a.scadenza) else "",
        "esito": esito,
        "visto_il": dt.datetime.now().isoformat(timespec="seconds"),
    }


def get(d, chiave, default=None):
    return d["stato"].get(chiave, default)


def set(d, chiave, valore):
    d["stato"][chiave] = valore


def ha_contratto(d):
    """Con un contratto a tempo determinato in corso non si può partecipare agli
    interpelli che richiamano la nota MIM 115135 del 25/07/2024."""
    return get(d, "contratto_td", "no") == "si"
