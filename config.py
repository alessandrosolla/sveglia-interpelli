# -*- coding: utf-8 -*-
"""Configurazione della parte pubblica del sorvegliante.

Qui dentro non c'è nulla di personale: l'indirizzo di una pagina pubblica del
Ministero, qualche soglia e le classi di concorso. Anagrafica, documenti e
spedizione stanno nel repository privato, che si accende solo su conferma.
"""
import os
import pathlib

BASE = pathlib.Path(__file__).resolve().parent

# --- fonte sorvegliata -------------------------------------------------------
FONTE = "https://www.mim.gov.it/web/cagliari/interpelli-docenti-e-personale-educativo"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"

# --- archivio e cartelle di lavoro -------------------------------------------
ARCHIVIO = BASE / "visti.json"
SCARICATI = BASE / "scaricati"
LOG = BASE / "sorveglia.log"

# --- il repository privato, che spedisce ------------------------------------
PRIVATO = os.environ.get("REPO_PRIVATO", "alessandrosolla/interpelli-cagliari")


def token():
    return os.environ["TELEGRAM_TOKEN"].strip()


def chat_id():
    return int(os.environ["TELEGRAM_CHAT_ID"].strip())


def token_dispatch():
    return os.environ["DISPATCH_TOKEN"].strip()


# --- come collocare Alessandro nelle fasce di un interpello ------------------
ABILITATO = {"A019", "A-19"}
DA_CONFERMARE = {"A018", "A-18", "A046", "A-46"}

# --- soglie ------------------------------------------------------------------
ROSSO_ORE = 12
GIALLO_ORE = 36
SILENZIO_SOSPETTO_GIORNI = 7
