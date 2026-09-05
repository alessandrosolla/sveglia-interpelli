# -*- coding: utf-8 -*-
"""Il sorvegliante degli interpelli dell'ATS di Cagliari — parte pubblica.

Legge la sezione Interpelli, capisce che cosa dice ogni avviso nuovo e lo manda
su Telegram con i due bottoni. Quando Alessandro conferma, non spedisce lui:
sveglia il repository privato, che è l'unico posto dove stanno i suoi documenti.

    python3 sorveglia.py            un giro
    python3 sorveglia.py --primo    archivia il presente senza notificare
"""
from __future__ import annotations

import sys
import re
import json
import hashlib
import datetime as dt
import urllib.request
import urllib.parse
import traceback

import config
import archivio
import fonte
import avviso as lettore
import bot


# ------------------------------------------------------------------ giudizio
def valuta(a, con_contratto):
    """(ammesso, fascia, motivo).

    Non filtra per classe di concorso: ci si candida a tutto e sarà la scuola a
    collocarlo. La fascia serve a fargli capire le probabilità, non a nascondere.
    L'unica esclusione vera è quella della nota MIM 115135/2024.
    """
    if a.esclude_gia_incaricati and con_contratto:
        return False, "—", ("Escluso per legge: l'avviso richiama la nota MIM "
                            "115135/2024 e tu hai un contratto in corso.")

    cl = (a.classe or "").upper().replace("-", "")
    if cl in {x.replace("-", "") for x in config.ABILITATO}:
        return True, "A — abilitato", "Sei abilitato: prima fascia, hai la precedenza."
    if cl in {x.replace("-", "") for x in config.DA_CONFERMARE}:
        return True, "B — titolo di accesso probabile", (
            "Titolo di accesso verosimile viste le tue lauree.")
    if "titoli affini" in a.fasce:
        return True, "C — titolo affine", (
            "L'avviso ammette esplicitamente i titoli di studio affini: rientri.")
    return True, "D — fuori fascia", (
        "L'avviso nomina solo %s. Puoi candidarti lo stesso dichiarando il vero: "
        "ti valuteranno solo se le fasce sopra restano vuote."
        % " e ".join(a.fasce or ["fasce non dichiarate"]))


# ------------------------------------------------------------------ allegati
def scarica_file(url, destinazione):
    req = urllib.request.Request(url, headers={"User-Agent": config.UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        destinazione.write_bytes(r.read())
    return destinazione


def nome_da_url(url):
    """Nome file accorciato ma con l'estensione intatta: troncare senza riguardo
    faceva sparire il '.pdf' e l'avviso veniva scartato."""
    for pezzo in url.split("/"):
        p = urllib.parse.unquote_plus(pezzo)
        m = re.search(r"\.(pdf|docx?|zip|p7m)$", p, re.I)
        if m:
            ext = m.group(0)
            base = re.sub(r"[^\w.\-() ]", "_", p[:-len(ext)]).strip()[:100]
            return (base or "allegato") + ext
    return None


def estensione(url):
    n = nome_da_url(url) or ""
    return n.rsplit(".", 1)[-1].lower() if "." in n else ""


def pdf_dell_avviso(url_scheda):
    pdf = modulo = None
    for _, u in fonte.allegati(url_scheda):
        nome = nome_da_url(u)
        if not nome:
            continue
        basso = nome.lower()
        if "modul" in basso or "allegato" in basso or "domanda" in basso:
            if not modulo:
                modulo = (nome, u)
        elif estensione(u) == "pdf" and not pdf:
            pdf = (nome, u)
    if pdf is None and modulo and estensione(modulo[1]) == "pdf":
        pdf, modulo = modulo, None
    return pdf, modulo


# ------------------------------------------------------------------ conferme
def chiave(url):
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def tastiera(k, canale):
    if canale == "portale Argo":
        return {"inline_keyboard": [[
            {"text": "🔗 Apri Argo", "url": "https://madinterpello.portaleargo.it/"},
            {"text": "🗂 Archivia", "callback_data": "no:%s" % k},
        ]]}
    return {"inline_keyboard": [[
        {"text": "✅ Conferma e invia", "callback_data": "si:%s" % k},
        {"text": "🗂 Ignora", "callback_data": "no:%s" % k},
    ]]}


def _tg(metodo, **campi):
    url = "https://api.telegram.org/bot%s/%s" % (config.token(), metodo)
    data = urllib.parse.urlencode(campi).encode() if campi else None
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        return json.load(r)


def _rispondi(cq_id, testo):
    """Il riscontro sul bottone è una cortesia: se Telegram lo rifiuta perché il
    tocco è vecchio, non deve impedire la spedizione."""
    try:
        _tg("answerCallbackQuery", callback_query_id=cq_id, text=testo)
    except Exception:
        pass


def sveglia_privato(pendente):
    """Passa la candidatura al repository privato, l'unico che ha i documenti."""
    corpo = json.dumps({"event_type": "spedisci", "client_payload": pendente}).encode()
    req = urllib.request.Request(
        "https://api.github.com/repos/%s/dispatches" % config.PRIVATO,
        data=corpo, method="POST",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer %s" % config.token_dispatch(),
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.status


def raccogli(d):
    offset = archivio.get(d, "update_offset", 0)
    try:
        up = _tg("getUpdates", offset=offset, timeout=0,
                 allowed_updates='["callback_query"]')
    except Exception:
        return 0

    passate = 0
    for u in up.get("result", []):
        archivio.set(d, "update_offset", u["update_id"] + 1)
        cq = u.get("callback_query")
        if not cq or ":" not in cq.get("data", ""):
            continue
        azione, k = cq["data"].split(":", 1)

        # un tocco ripetuto non deve produrre una seconda candidatura
        gia = d.setdefault("inviati", {}).get(k)
        if gia:
            _rispondi(cq["id"], "Già inviata il %s." % gia.get("quando", "poco fa"))
            continue

        pend = d.get("pendenti", {}).get(k)
        if not pend:
            _rispondi(cq["id"], "Non trovo più questo avviso in memoria.")
            continue

        if azione == "no":
            d["pendenti"].pop(k, None)
            _rispondi(cq["id"], "Archiviato.")
            bot.messaggio("🗂 Archiviato senza inviare: %s%s"
                          % (pend["classe"], " — " + pend["scuola"] if pend["scuola"] else ""))
            continue

        if pend.get("scadenza"):
            scad = dt.datetime.fromisoformat(pend["scadenza"])
            if scad < dt.datetime.now():
                d["pendenti"].pop(k, None)
                _rispondi(cq["id"], "Troppo tardi: era scaduto.")
                bot.messaggio("⌛️ <b>Non inviata: scadenza superata</b>\n%s — scadeva il %s"
                              % (pend["classe"], scad.strftime("%d/%m alle %H:%M")))
                continue

        _rispondi(cq["id"], "Invio in corso…")
        try:
            sveglia_privato(dict(pend, chiave=k))
            # segnata subito: se la spedizione fallisce si riprova a mano, ma
            # non si rischia di mandarne due alla stessa scuola
            d["inviati"][k] = {"quando": dt.datetime.now().strftime("%d/%m alle %H:%M"),
                               "classe": pend["classe"], "scuola": pend["scuola"]}
            d["pendenti"].pop(k, None)
            passate += 1
        except Exception as e:
            bot.messaggio("❌ <b>Non sono riuscito a passare la candidatura</b>\n"
                          "%s — %s\n\n<code>%s</code>\n\nPuoi mandarla a mano a %s"
                          % (pend["classe"], pend["scuola"], str(e)[:200],
                             pend["destinatario"]))
    return passate


# ------------------------------------------------------------------ un avviso
def tratta(d, voce, notifica=True):
    url = voce["url"]
    pdf, modulo = pdf_dell_avviso(url)
    if not pdf:
        if notifica:
            bot.messaggio("⚪️ <b>Avviso senza PDF leggibile</b>\n%s\n\n"
                          '<a href="%s">Aprilo a mano</a>' % (voce["titolo"][:180], url))
        archivio.segna(d, url, voce, None, "senza_pdf")
        return "senza_pdf"

    config.SCARICATI.mkdir(exist_ok=True)
    percorso = scarica_file(pdf[1], config.SCARICATI / pdf[0])
    a = lettore.leggi(percorso, titolo=voce["titolo"])
    ammesso, fascia, motivo = valuta(a, archivio.ha_contratto(d))

    if a.scaduto:
        esito = "scaduto"
    elif not ammesso:
        esito = "non_ammesso"
    else:
        esito = "notificato"
        if notifica:
            k = chiave(url)
            d.setdefault("pendenti", {})[k] = {
                "url": url, "classe": a.classe or "", "scuola": a.scuola or "",
                "destinatario": a.destinatario or "", "canale": a.canale,
                "scadenza": a.scadenza.isoformat() if a.scadenza else "",
                "richiede": list(a.richiede), "ore": a.ore or "",
                "durata": a.durata or "", "sede": a.sede or "",
                "creato": dt.datetime.now().isoformat(timespec="seconds"),
            }
            testo = bot.scheda(a, fascia, motivo, url, pdf[1], modulo_scuola=bool(modulo))
            if not archivio.ha_contratto(d):
                testo += ("\n\n<i>Sei senza incarico: se ti individuano e poi "
                          "rinunci, perdi questa scuola per l'anno.</i>")
            bot.messaggio(testo, markup=tastiera(k, a.canale))
            bot.documento(percorso, "Avviso originale")
            if modulo:
                mp = scarica_file(modulo[1], config.SCARICATI / modulo[0])
                bot.documento(mp, "Il modulo della scuola, se preferisci il loro")

    archivio.segna(d, url, voce, a, esito)
    return esito


# ------------------------------------------------------------------ il giro
def giro(primo=False):
    d = archivio.carica()
    try:
        voci = fonte.elenco()
    except Exception as e:
        n = int(archivio.get(d, "fallimenti", 0)) + 1
        archivio.set(d, "fallimenti", n)
        if n == 5:
            bot.messaggio("⚠️ Non riesco a raggiungere la pagina dell'ATS da cinque "
                          "giri di fila.\n\n<code>%s</code>" % e)
        archivio.salva(d)
        return
    archivio.set(d, "fallimenti", 0)

    nuovi = [v for v in voci if not archivio.gia_visto(d, v["url"])]

    if primo:
        for v in voci:
            archivio.segna(d, v["url"], v, None, "preesistente")
        archivio.salva(d)
        print("archiviati %d avvisi come già visti" % len(voci))
        return

    conteggio = {}
    for v in nuovi:
        try:
            e = tratta(d, v)
        except Exception:
            e = "errore"
            bot.messaggio("⚠️ Errore leggendo un avviso:\n%s\n\n<code>%s</code>"
                          % (v["titolo"][:120], traceback.format_exc()[-400:]))
            archivio.segna(d, v["url"], v, None, "errore")
        conteggio[e] = conteggio.get(e, 0) + 1

    oggi = dt.date.today().isoformat()
    if nuovi:
        archivio.set(d, "ultimo_nuovo", oggi)
    else:
        ultimo = archivio.get(d, "ultimo_nuovo")
        if ultimo:
            giorni = (dt.date.today() - dt.date.fromisoformat(ultimo)).days
            if giorni >= config.SILENZIO_SOSPETTO_GIORNI and \
               archivio.get(d, "silenzio_segnalato") != ultimo:
                bot.messaggio("🔍 Sono <b>%d giorni</b> che non trovo un interpello "
                              "nuovo.\nCon una media di tre a settimana è insolito: o "
                              "è periodo morto, o mi si è rotto qualcosa nella lettura "
                              "della pagina." % giorni)
                archivio.set(d, "silenzio_segnalato", ultimo)

    try:
        passate = raccogli(d)
        if passate:
            conteggio["passate al privato"] = passate
    except Exception:
        bot.messaggio("⚠️ Errore raccogliendo le conferme:\n<code>%s</code>"
                      % traceback.format_exc()[-350:])

    archivio.set(d, "ultimo_giro", dt.datetime.now().isoformat(timespec="seconds"))
    archivio.salva(d)
    print("pagina=%d nuovi=%d %s" % (len(voci), len(nuovi), conteggio))


if __name__ == "__main__":
    giro(primo="--primo" in sys.argv)
