# -*- coding: utf-8 -*-
"""Lettura di un singolo interpello: dal PDF ai campi che contano.

I campi vengono estratti con pattern validati su avvisi reali dell'ATS Cagliari
(I.C. Selargius 1 marzo 2026, I.I.S. Dessì Villaputzu maggio 2026). Quando un
campo non è leggibile con certezza resta None: il sorvegliante lo segnala invece
di tirare a indovinare.
"""
from __future__ import annotations   # il Mac ha Python 3.9

import re
import datetime as dt
from dataclasses import dataclass, field

from pypdf import PdfReader

# --- pattern ----------------------------------------------------------------
CDC = re.compile(
    r"\b("
    r"A[0-9]{3}|A-[0-9]{2}|"          # A027, A-19
    r"AS[0-9]{2}|AM[0-9][A-Z]|"       # AS12, AM2A
    r"AD(?:SS|MM|EE|AA)|"             # sostegno
    r"EEEE|"                          # primaria posto comune
    r"B[A-Z0-9]{3}|BD[0-9]{2}"        # laboratori, conversazione
    r")\b")

ORA = re.compile(r"ore\s*(\d{1,2})[.:](\d{2})", re.I)
DATA_IT = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
SCADENZA = re.compile(
    r"(?:entro|termine).{0,80}?ore\s*(\d{1,2})[.:](\d{2}).{0,40}?"
    r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", re.I | re.S)
SCADENZA_INV = re.compile(
    r"(?:entro|termine).{0,80}?(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}).{0,40}?"
    r"ore\s*(\d{1,2})[.:](\d{2})", re.I | re.S)

ORE_SETT = re.compile(r"n?\.?\s*(\d{1,2})\s*ore\s*settimanal", re.I)
SEDE = re.compile(r"sede\s+di\s+servizio:?\s*([^\n]{3,90})", re.I)

# --- durata del contratto: da quando a quando -------------------------------
# Va cercata PRIMA della scadenza, perché "entro il ..." è un'altra cosa.
D_DAL_AL = re.compile(
    r"dal\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\s*(?:al|fino\s+al)\s*"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})", re.I)
D_FINO_AL = re.compile(
    r"(?:fino|sino)\s+al\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})", re.I)
D_TERMINE = re.compile(
    r"(?:fino|sino)\s+al\s+termine\s+(?:del(?:le)?\s+)?"
    r"(attivit[àa]\s+didattich[ae]|lezioni)", re.I)
D_AVENTE = re.compile(r"avente\s+termine\s+il\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})", re.I)

# --- orario settimanale ------------------------------------------------------
# Raro: su 21 avvisi reali solo 2 lo contenevano. Quando c'è, lo prendo.
GIORNO_ORE = re.compile(
    r"(luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato)['\u2019]?\s*"
    r"(\d{1,2}[:.]\d{2})\s*[-\u2013/ ]\s*(\d{1,2}[:.]\d{2})", re.I)
ORARIO_UNICO = re.compile(
    r"dal\s+luned[iì]\s+al\s+(venerd[iì]|sabato)[^.]{0,40}?dalle\s*"
    r"(\d{1,2}[.:]\d{2})\s*alle\s*(\d{1,2}[.:]\d{2})", re.I)

# fasce ammesse
F_ABIL = re.compile(r"docenti\s+abilitati", re.I)
F_ACCESSO = re.compile(r"titolo\s+di\s+accesso", re.I)
F_AFFINI = re.compile(r"titoli?\s+di\s+studio\s+affini|titolo\s+di\s+studio\s+attinente", re.I)

# esclusione di chi ha già un contratto a tempo determinato (nota MIM 115135/2024)
ESCLUSI_TD = re.compile(
    r"non\s+è\s+consentito\s+partecipare.{0,160}?(?:individuati|destinatari).{0,80}?"
    r"contratto\s+a\s+tempo\s+determinato", re.I | re.S)

# --- che cosa l'avviso chiede di allegare -----------------------------------
# Ogni scuola chiede cose diverse. Vanno lette una per una, non indovinate.
RICHIESTE = [
    ("curriculum",       re.compile(r"curriculum(?:\s+vitae)?", re.I)),
    ("documento d'identità", re.compile(r"(?:copia|fotocopia).{0,30}documento\s+"
                                        r"d[i'’]\s*identit|carta\s+d[i'’]\s*identit", re.I)),
    ("modulo allegato",  re.compile(r"(?:allegat[oi]\s+[A-C1-3]|modello\s+di\s+candidatura|"
                                    r"modulo\s+(?:di\s+)?(?:partecipazione|domanda|allegato))", re.I)),
    ("titolo di accesso", re.compile(r"(?:copia|certificat|attestazione).{0,40}"
                                     r"(?:titolo\s+di\s+accesso|titolo\s+di\s+studio|"
                                     r"abilitazione|laurea)", re.I)),
    ("codice fiscale",   re.compile(r"codice\s+fiscale", re.I)),
    ("dichiarazione DPR 445", re.compile(r"autocertificazion|D\.?P\.?R\.?\s*n?\.?\s*445", re.I)),
]

# la sezione in cui si spiega come rispondere: lì stanno le richieste vere
COME_RISPONDERE = re.compile(
    r"(?:inviare|trasmettere|far\s+pervenire|presentare|allegando|corredat|"
    r"la\s+domanda\s+dovr|dovr[àa]\s+contenere)(.{0,900})", re.I | re.S)

ARGO = re.compile(r"madinterpello\.portaleargo\.it", re.I)
EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.(?:it|edu\.it|gov\.it|com)", re.I)
PEC = re.compile(r"[a-z0-9._%+-]+@pec\.[a-z0-9.-]+\.[a-z]{2,}", re.I)


# Indirizzi che NON sono la scuola: l'ATS, la direzione regionale, i protocolli.
# Mandare lì la candidatura significa non candidarsi.
NON_SCUOLA = re.compile(r"^(usp|uspca|drsa|direzione|protocollo|urp)", re.I)
# Le caselle delle scuole statali hanno per nome il codice meccanografico:
# caic89900e, cais004004, caps02000b. È il segnale più affidabile che esista.
COD_MECC = re.compile(r"^[a-z]{2}[a-z]{2}[a-z0-9]{5,6}@(?:pec\.)?istruzione\.it$", re.I)


def _destinatario(t):
    """(canale, indirizzo) a cui va davvero mandata la candidatura.

    Preferisce la casella il cui nome è un codice meccanografico, perché è la
    scuola con certezza. In mancanza, prende un indirizzo nominato nella parte
    che spiega come rispondere. Se resta ambiguo torna None: meglio chiedere
    ad Alessandro che spedire all'indirizzo sbagliato.
    """
    m = COME_RISPONDERE.search(t)
    zona = m.group(1) if m else ""

    tutti = EMAIL.findall(t) + PEC.findall(t)
    puliti = [e for e in dict.fromkeys(tutti) if not NON_SCUOLA.match(e.split("@")[0])]

    # 1. codice meccanografico, prima quello ordinario poi la PEC
    mecc = [e for e in puliti if COD_MECC.match(e)]
    ordinarie = [e for e in mecc if "@pec." not in e.lower()]
    if ordinarie:
        return "email", ordinarie[0]
    if mecc:
        return "PEC", mecc[0]

    # 2. un indirizzo citato dove si spiega come rispondere
    in_zona = [e for e in puliti if e in zona]
    if in_zona:
        return ("PEC" if "@pec." in in_zona[0].lower() else "email"), in_zona[0]

    return "?", None


def _testo(pdf_path):
    t = "".join((p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages)
    return re.sub(r"[ \t]+", " ", t)


@dataclass
class Avviso:
    titolo: str = ""
    scuola: str = ""
    classe: str | None = None
    ore: str | None = None
    durata: str | None = None
    sede: str | None = None
    estratto: str | None = None
    orario: str | None = None
    scadenza: dt.datetime | None = None
    canale: str = "?"
    destinatario: str | None = None
    fasce: list = field(default_factory=list)
    richiede: list = field(default_factory=list)
    esclude_gia_incaricati: bool = False
    incerti: list = field(default_factory=list)
    testo: str = ""

    @property
    def ore_alla_scadenza(self):
        if not self.scadenza:
            return None
        return (self.scadenza - dt.datetime.now()).total_seconds() / 3600

    @property
    def scaduto(self):
        o = self.ore_alla_scadenza
        return o is not None and o < 0


def leggi(pdf_path, titolo=""):
    t = _testo(pdf_path)
    a = Avviso(titolo=titolo, testo=t)

    # scuola: la prima riga con un istituto riconoscibile
    m = re.search(r"(Istituto[^\n]{0,80}|I\.I\.S\.[^\n]{0,60}|Liceo[^\n]{0,60}|"
                  r"ISTITUTO[^\n]{0,80}|CONVITTO[^\n]{0,60})", t)
    if m:
        a.scuola = re.sub(r"\s+", " ", m.group(1)).strip()

    # classe di concorso: la più frequente nell'oggetto, altrimenti nel testo
    ogg = t[:1600]
    trovate = CDC.findall(ogg) or CDC.findall(t)
    if trovate:
        a.classe = max(set(trovate), key=trovate.count)
    else:
        a.incerti.append("classe di concorso")

    m = ORE_SETT.search(t)
    if m:
        a.ore = "%s ore settimanali" % m.group(1)

    m = SEDE.search(t)
    if m:
        a.sede = re.sub(r"\s+", " ", m.group(1)).strip(" .;")

    # L'estratto: il pezzo dopo EMETTE, dove la scuola descrive il posto.
    # Le durate sono scritte in troppi modi per prenderle tutte con un pattern,
    # quindi il testo originale viaggia sempre insieme ai campi estratti.
    m = re.search(r"\bEMETTE\b(.{40,900})", t, re.S)
    if not m:
        m = re.search(r"(?:avviso|reclutamento|conferimento)(.{40,700})", t, re.S | re.I)
    if m:
        e = re.sub(r"\s+", " ", m.group(1)).strip()
        e = re.split(r"Dato il carattere|Si precisa|gli aspiranti interessati", e)[0].strip()
        a.estratto = e[:420].rstrip() + ("…" if len(e) > 420 else "")

    # orario settimanale, quando la scuola si degna di scriverlo
    giorni = GIORNO_ORE.findall(t)
    if giorni:
        a.orario = " · ".join("%s %s–%s" % (g.capitalize().rstrip("'\u2019"),
                                            i.replace(".", ":"), f.replace(".", ":"))
                              for g, i, f in giorni)
    else:
        m = ORARIO_UNICO.search(t)
        if m:
            a.orario = "dal lunedì al %s, %s–%s" % (
                m.group(1).lower(), m.group(2).replace(".", ":"), m.group(3).replace(".", ":"))

    # durata: cercata solo dove NON si sta parlando del termine per candidarsi
    corpo = re.sub(r"(?:entro|termine perentorio).{0,120}", " ", t, flags=re.I | re.S)
    m = D_DAL_AL.search(corpo)
    if m:
        a.durata = "dal %s al %s" % (m.group(1), m.group(2))
    elif D_TERMINE.search(corpo):
        a.durata = "fino al termine delle %s" % D_TERMINE.search(corpo).group(1).lower()
    else:
        m = D_AVENTE.search(corpo) or D_FINO_AL.search(corpo)
        if m:
            a.durata = "fino al %s" % m.group(1)

    # scadenza: provo entrambi gli ordini (ora-data e data-ora)
    m = SCADENZA.search(t)
    if m:
        hh, mm, g, me, aa = m.groups()
        a.scadenza = dt.datetime(int(aa), int(me), int(g), int(hh), int(mm))
    else:
        m = SCADENZA_INV.search(t)
        if m:
            g, me, aa, hh, mm = m.groups()
            a.scadenza = dt.datetime(int(aa), int(me), int(g), int(hh), int(mm))
    if not a.scadenza:
        a.incerti.append("scadenza")

    # canale di risposta
    if ARGO.search(t):
        a.canale = "portale Argo"
        a.destinatario = "https://madinterpello.portaleargo.it/"
    else:
        a.canale, a.destinatario = _destinatario(t)
        if not a.destinatario:
            a.incerti.append("indirizzo a cui rispondere")

    # che cosa chiede di allegare: si guarda solo nella parte che spiega come
    # rispondere, altrimenti una citazione qualsiasi verrebbe scambiata per obbligo
    m = COME_RISPONDERE.search(t)
    zona = m.group(1) if m else t
    for etichetta, pattern in RICHIESTE:
        if pattern.search(zona):
            a.richiede.append(etichetta)
    if not a.richiede:
        a.incerti.append("documenti da allegare")

    if F_ABIL.search(t):
        a.fasce.append("abilitati")
    if F_ACCESSO.search(t):
        a.fasce.append("titolo di accesso")
    if F_AFFINI.search(t):
        a.fasce.append("titoli affini")

    a.esclude_gia_incaricati = bool(ESCLUSI_TD.search(t))
    return a


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        a = leggi(p)
        print("=" * 70)
        print("file      :", p)
        print("scuola    :", a.scuola[:70])
        print("classe    :", a.classe)
        print("ore       :", a.ore)
        print("durata    :", a.durata)
        print("sede      :", a.sede)
        print("scadenza  :", a.scadenza)
        print("canale    :", a.canale, "->", a.destinatario)
        print("fasce     :", a.fasce or "non dichiarate")
        print("esclude chi ha già un contratto TD:", a.esclude_gia_incaricati)
        print("campi incerti:", a.incerti or "nessuno")
