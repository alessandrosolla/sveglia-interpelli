# Sveglia

Un orologio, niente di più.

Questo repository esiste per una ragione sola: il `cron` di GitHub Actions è
dichiaratamente *best effort*, e sui repository privati arriva a saltare ore
intere — misurato su due giorni: sei esecuzioni in quarantotto ore, con buchi
di quattro o cinque ore.

Sui repository **pubblici** i minuti di esecuzione sono invece illimitati, e un
job può restare acceso fino a sei ore. Qui dentro c'è quindi un ciclo che ogni
cinque minuti manda un segnale di sveglia a un altro repository, e prima di
scadere rilancia sé stesso.

Non contiene dati personali, né logica applicativa: solo l'orologio.
Il destinatario della sveglia è configurato nei *Secrets*, che restano cifrati
anche in un repository pubblico.
