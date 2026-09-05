# -*- coding: utf-8 -*-
"""Notifiche Telegram."""
import json
import urllib.request
import urllib.parse
import mimetypes
import uuid

import config

API = "https://api.telegram.org/bot%s/%s"


def _call(metodo, **campi):
    url = API % (config.token(), metodo)
    data = urllib.parse.urlencode(campi).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        return json.load(r)


def messaggio(testo, markup=None):
    campi = {"chat_id": config.chat_id(), "text": testo,
             "parse_mode": "HTML", "disable_web_page_preview": "true"}
    if markup:
        campi["reply_markup"] = json.dumps(markup)
    return _call("sendMessage", **campi)


def documento(percorso, didascalia=""):
    """Invio multipart di un allegato."""
    percorso = str(percorso)
    confine = uuid.uuid4().hex
    tipo = mimetypes.guess_type(percorso)[0] or "application/octet-stream"
    nome = percorso.rsplit("/", 1)[-1]

    parti = []
    for chiave, valore in (("chat_id", str(config.chat_id())),
                           ("caption", didascalia),
                           ("parse_mode", "HTML")):
        parti.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (confine, chiave, valore)).encode())
    parti.append(("--%s\r\nContent-Disposition: form-data; name=\"document\"; "
                  "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                  % (confine, nome, tipo)).encode())
    parti.append(open(percorso, "rb").read())
    parti.append(("\r\n--%s--\r\n" % confine).encode())
    corpo = b"".join(parti)

    req = urllib.request.Request(
        API % (config.token(), "sendDocument"), data=corpo,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % confine})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


# ---------------------------------------------------------------- la scheda
SEMAFORO = {"rosso": "🔴", "giallo": "🟡", "verde": "🟢", "grigio": "⚪️"}


def _colore(ore):
    if ore is None:
        return "grigio"
    if ore < config.ROSSO_ORE:
        return "rosso"
    if ore < config.GIALLO_ORE:
        return "giallo"
    return "verde"


def _resta(ore):
    if ore is None:
        return "scadenza non leggibile"
    if ore < 0:
        return "già scaduto"
    if ore < 1:
        return "scade tra %d minuti" % int(ore * 60)
    if ore < 48:
        return "scade tra %d ore" % int(ore)
    return "scade tra %d giorni" % int(ore / 24)


def scheda(a, fascia, motivo, url_avviso, url_pdf=None, modulo_scuola=False):
    """Compone il messaggio di un interpello. `a` è un avviso.Avviso."""
    ore = a.ore_alla_scadenza
    righe = ["%s <b>%s</b>" % (SEMAFORO[_colore(ore)], a.classe or "classe non letta")]
    if a.scuola:
        righe.append(a.scuola)
    dettaglio = " · ".join(x for x in (a.ore, a.durata, a.sede) if x)
    if dettaglio:
        righe.append(dettaglio)
    righe.append("")
    if a.orario:
        righe.append("🗓 <b>Orario:</b> %s" % a.orario)
    else:
        righe.append("🗓 <b>Orario:</b> non indicato nell'avviso — "
                     "va chiesto alla scuola")
    if a.estratto:
        righe.append("")
        righe.append("<i>Dall'avviso:</i> «%s»" % a.estratto)
    righe.append("")
    if a.scadenza:
        righe.append("<b>%s</b> — %s" % (_resta(ore), a.scadenza.strftime("%d/%m alle %H:%M")))
    else:
        righe.append("<b>Scadenza non leggibile</b> — controlla l'avviso originale")
    righe.append("Fascia: %s" % fascia)
    righe.append(motivo)
    righe.append("")
    if a.richiede:
        import documenti
        ok, mancanti = documenti.verifica(a.richiede)
        righe.append("<b>L'avviso chiede:</b> %s" % ", ".join(a.richiede))
        if ok:
            righe.append("✔️ Ho tutto: la candidatura parte completa.")
        else:
            righe.append("❗️ <b>Mi manca:</b> %s — la mando lo stesso ma "
                         "incompleta, oppure completala tu." % ", ".join(mancanti))
        if "modulo allegato" in a.richiede and modulo_scuola:
            righe.append("⚠️ <b>Questa scuola allega un suo modulo</b> e chiede "
                         "di usare quello. Io mando la mia domanda firmata, che "
                         "come autocertificazione è valida — ma se vuoi essere "
                         "inattaccabile compila il loro, te lo giro qui sotto.")
    else:
        righe.append("<b>Allegati richiesti:</b> non li ho letti con certezza, "
                     "controlla l'avviso")
    righe.append("")
    righe.append("Si risponde da: %s" % a.canale)
    if a.destinatario:
        righe.append("<code>%s</code>" % a.destinatario)
    if a.incerti:
        righe.append("")
        righe.append("⚠️ Non ho letto con certezza: %s" % ", ".join(a.incerti))
    righe.append("")
    righe.append('🔗 <a href="%s"><b>APRI L\'ANNUNCIO ORIGINALE</b></a>' % url_avviso)
    if url_pdf:
        righe.append('📄 <a href="%s">Scarica il PDF dell\'avviso</a>' % url_pdf)
    return "\n".join(righe)


if __name__ == "__main__":
    print(messaggio("Prova di collegamento del sorvegliante.").get("ok"))
