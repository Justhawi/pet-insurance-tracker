#!/usr/bin/env python3
"""
Pet Insurance Live Data Fetcher — v3
Trustpilot  : navigates search page to find exact company, then extracts score
Google Maps : uses JavaScript evaluation for reliable score + review count
"""

import json, re, time, os, sys, urllib.parse, random, urllib.request, urllib.error
from datetime import datetime
# NOTE: playwright is imported lazily inside run_fetch (browser mode only),
# so this module also runs on servers that have no browser installed.

HERE      = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "companies_data.json")
HTML_PATH = os.path.join(HERE, "pet_insurance_tracker.html")
LOG_PATH  = os.path.join(HERE, "fetch_log.txt")

# ── Cloud sync config ─────────────────────────────────────────
# Set these to your Render URL and secret key after deployment.
# Leave blank to skip cloud upload.
CLOUD_URL = os.environ.get("CLOUD_URL", "")   # e.g. https://pet-tracker.onrender.com
CLOUD_KEY = os.environ.get("CLOUD_KEY", "")   # must match UPLOAD_KEY on Render

_progress_cb = None
def set_progress_callback(fn):
    global _progress_cb
    _progress_cb = fn

def log(msg):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if _progress_cb:
        _progress_cb(line)

# ─────────────────────────────────────────────────────────────
# COMPANY LIST  (website = used as hint only; search is primary)
# ─────────────────────────────────────────────────────────────
COMPANIES = [
    {"country":"USA","company":"Prudent Pet Insurance","website":"www.prudentpet.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Pumpkin","website":"www.pumpkin.care","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"Kennel Club Pet Insurance","website":"www.kcinsurance.co.uk","opType":"Only Sale","group":"","link":"https://www.petinsurancereview.co.uk/insurer/royal-kennel-club-pet-insurance","underwriter":"Agria"},
    {"country":"Italy","company":"Baboop Italy","website":"www.baboop.it","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Petplan UK","website":"www.petplan.co.uk","opType":"Full Service","group":"","link":"","underwriter":"Allianz"},
    {"country":"Ireland","company":"Agria PetInsure","website":"www.agria.ie","opType":"Full Service","group":"Agria","link":"","underwriter":""},
    {"country":"Sweden","company":"Lassie","website":"www.lassie.co","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Petplan Spain","website":"www.petplan.es","opType":"Full Service","group":"","link":"","underwriter":"Telefonica"},
    {"country":"Germany","company":"Santevet Germany","website":"www.santevet.de","opType":"Full Service","group":"Santevet","link":"","underwriter":"Allianz"},
    {"country":"USA","company":"Fetch by The Dodo","website":"www.fetchpet.com","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Australia","company":"Bow Wow Meow Pet Insurance","website":"bowwowinsurance.com.au","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Spot Pet Insurance","website":"spotpet.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"Spot On Pet Insurance","website":"www.spotonpetinsurance.co.uk","opType":"Only Sale","group":"","link":"https://tradersunion.com/reviews/spotonpetinsurance-co-uk/","underwriter":""},
    {"country":"France","company":"kozoo.eu","website":"www.kozoo.eu","opType":"Only Sale","group":"Correlation","link":"https://www.assurland.com/assurance/assureurs/kozoo.html","underwriter":""},
    {"country":"UK","company":"Vetsure Pet Insurance","website":"www.vetsure.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Germany","company":"Petolo","website":"www.petolo.de","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Barkibu","website":"www.barkibu.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"France","company":"Dalma","website":"www.dalma.co","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Napo Pet Insurance","website":"www.napo.pet","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"ManyPets USA","website":"www.manypets.com","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"New Zealand","company":"PD Insurance","website":"www.pdinsurance.co.nz","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Germany","company":"AGILA Haustierversicherung","website":"www.agila.de","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"USA","company":"MetLife Pet Insurance","website":"www.metlifepetinsurance.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Only Paws Pet Insurance","website":"www.onlypawspetinsurance.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Miwuki Shelter & Insurance","website":"www.miwuki.com","opType":"Only Sale","group":"","link":"https://play.google.com/store/apps/details?id=com.miwuki.petshelter","underwriter":""},
    {"country":"France","company":"Agria Assurance pour Animaux","website":"www.agria.fr","opType":"Only Sale","group":"Agria","link":"","underwriter":""},
    {"country":"UK","company":"PDSA Pet Insurance","website":"www.pdsa.org.uk","opType":"Only Sale","group":"","link":"https://www.pet-insurance-guide.co.uk/provider-ratings/pdsa-pet-insurance-review/","underwriter":""},
    {"country":"Italy","company":"ConTe.it Cane e Gatto","website":"www.canegatto.conte.it","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Switzerland","company":"Animalia Switzerland","website":"www.animalia.ch","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Germany","company":"Figo Pet Tierkrankenversicherung","website":"www.figopet.de","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"Agria Pet Insurance","website":"www.agriapet.co.uk","opType":"Full Service","group":"Agria","link":"","underwriter":"Agria"},
    {"country":"UK","company":"Argos Pet Insurance","website":"www.argospetinsurance.co.uk","opType":"Only Sale","group":"","link":"https://www.pet-insurance-guide.co.uk/provider-ratings/argos-pet-insurance-how-good-is-it/","underwriter":""},
    {"country":"UK","company":"Waggel","website":"www.waggel.co.uk","opType":"Only Sale","group":"Correlation","link":"","underwriter":""},
    {"country":"Belgium","company":"Santevet Belgium","website":"www.santevet.be","opType":"Only Sale","group":"Santevet","link":"","underwriter":""},
    {"country":"USA","company":"Pet Insurance U","website":"www.petinsuranceu.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Trupanion","website":"www.trupanion.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Now Pet","website":"www.nowpet.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Denmark","company":"Agria Dyreforsikring DK","website":"www.agria.dk","opType":"Only Sale","group":"Agria","link":"","underwriter":""},
    {"country":"Netherland","company":"Figo pet Nederland","website":"www.figopet.nl","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"France","company":"SantéVet","website":"www.santevet.com","opType":"Only Sale","group":"Santevet","link":"","underwriter":""},
    {"country":"USA","company":"Embrace Pet Insurance","website":"www.embracepetinsurance.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Italy","company":"Santevet Italy","website":"www.santevet.it","opType":"Only Sale","group":"Santevet","link":"","underwriter":""},
    {"country":"UK","company":"Pet Protect","website":"www.petprotect.co.uk","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Spain","company":"Santevet Spain","website":"www.santevet.es","opType":"Only Sale","group":"Santevet","link":"","underwriter":""},
    {"country":"UK","company":"Perfect Pet","website":"www.perfectpetinsurance.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"The Insurance Emporium","website":"www.theinsuranceemporium.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Pets Best Pet Health Insurance","website":"www.petsbest.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"4Paws Pet Insurance","website":"www.4paws.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Healthy Paws Pet Insurance","website":"www.healthypawspetinsurance.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"France","company":"Assur O'Poil","website":"www.assuropoil.fr","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Italy","company":"Assur O'Poil Italy","website":"www.assuropoil.it","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"Animal Friends Insurance","website":"www.animalfriends.co.uk","opType":"Full Service","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"ManyPets","website":"www.manypets.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"France","company":"Fidanimo","website":"www.fidanimo.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Hartville Pet Insurance","website":"www.hartvillepetinsurance.com","opType":"Only Sale","group":"JAB","link":"https://www.petinsurancereview.com/insurers/hartville","underwriter":""},
    {"country":"Sweden","company":"Agria Djurförsäkring","website":"www.agria.se","opType":"Only Sale","group":"Agria","link":"","underwriter":""},
    {"country":"Australia","company":"Knose Pet Insurance","website":"www.knose.com.au","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Lifetimepetcover","website":"www.lifetimepetcover.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Everypaw","website":"www.everypaw.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"AKC Pet Insurance","website":"www.akcpetinsurance.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"Frank Pet Insurance","website":"www.frankpetinsurance.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Healthy Pets Insurance","website":"www.healthy-pets.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Figo Pet Insurance","website":"www.figopetinsurance.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Ireland","company":"PetInsurance.ie","website":"www.petinsurance.ie","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Scratch & Patch","website":"www.scratchandpatch.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"New Zealand","company":"Pet-n-Sur","website":"www.petnsur.co.nz","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Nationwide pet insurance","website":"www.petinsurance.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"ASPCA Pet Health Insurance","website":"www.aspcapetinsurance.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"UK","company":"Purely Pets Insurance","website":"www.purelypetsinsurance.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Petwise Insurance","website":"www.petwise-insurance.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Germany","company":"Balunos Germany","website":"www.balunos.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Switzerland","company":"epona.ch","website":"www.epona.ch","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Sweden","company":"ManyPets Sverige","website":"www.manypets.se","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Belgium","company":"Figo pet België","website":"www.figopet.be","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Czech Republic","company":"Petexpert by trupanion CZ","website":"www.petexpert.cz","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Petguard","website":"www.petguard.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Australia","company":"Petsy Pet Insurance","website":"www.petsy.com.au","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Pet Insurance","website":"www.pet-insurance.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Australia","company":"Pet Insurance Australia","website":"www.petinsuranceaustralia.com.au","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Canada","company":"Furkin Pet Insurance","website":"www.furkin.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Australia","company":"PetSecure Australia","website":"www.petsecure.com.au","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Norway","company":"Agria Dyreforsikring NO","website":"www.agria.no","opType":"Only Sale","group":"Agria","link":"","underwriter":""},
    {"country":"Spain","company":"Mascota y Salud","website":"www.mascotaysalud.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Canada","company":"Pets Plus Us","website":"www.petsplusus.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Germany","company":"Agria Germany","website":"agriatierversicherung.de","opType":"Only Sale","group":"Agria","link":"","underwriter":""},
    {"country":"UK","company":"Whistle & Wag","website":"www.whistleandwag.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Veteasy","website":"www.veteasy.es","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"TrustedPals Pet Insurance","website":"www.trustedpals.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Japan","company":"Anicom","website":"www.anicom-sompo.co.jp","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"South Africa","company":"MediPet","website":"www.medipet.co.za","opType":"Only Sale","group":"","link":"https://www.hellopeter.com/medipet-animal-health-insurance-brokers-pty-ltd","underwriter":""},
    {"country":"New Zealand","company":"Petcover New Zealand","website":"www.petcovergroup.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Odie Pet Insurance","website":"www.getodie.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Rainwalk Pet Insurance","website":"rainwalkpetinsurance.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Switzerland","company":"Wau Miau Switzerland","website":"www.wau-miau.ch","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Felix Pet Insurance","website":"www.felixcatinsurance.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Italy","company":"Zampol Italy","website":"www.zampol.it","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"PetPartners","website":"www.petpartners.com","opType":"Only Sale","group":"JAB","link":"https://www.petinsurancereview.com/insurers/pet-partners","underwriter":""},
    {"country":"UK","company":"VetsMediCover","website":"www.vetsmedicover.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"South Africa","company":"Cat and Dogsure","website":"www.catanddogsure.co.za","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"MiPet Cover","website":"www.mipetcover.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Animalia Pet Insurance","website":"www.animalia.pet","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Japan","company":"ipet Insurance","website":"www.ipet-ins.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Doggo","website":"www.trydoggo.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Argentina","company":"HolaVet","website":"www.holavet.com.ar","opType":"Only Sale","group":"","link":"https://www.facebook.com/p/HolaVet-AR-Vida-Seguros-100072144546199/","underwriter":""},
    {"country":"UK","company":"RSPCA Pet Insurance","website":"www.rspca-petinsurance.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Japan","company":"Pshoken Japan","website":"www.pshoken.co.jp","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"PetInsuranceQuotes.com","website":"www.petinsurancequotes.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"México","company":"MediPet MX","website":"www.medipet.mx","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"South Africa","company":"Petsure ZA","website":"www.petsure.co.za","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Argentina","company":"Fielpet","website":"www.fielpet.com.ar","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"France","company":"Animalia Protect","website":"www.animalia-protect.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"South Africa","company":"PawPaw Pet Health Insurance","website":"www.pawpawpets.co.za","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"France","company":"Zoola","website":"www.zoola.fr","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Kalibo","website":"www.kalibo.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Switzerland","company":"SmartPaws CH","website":"www.smartpaws.ch","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Heckin Good","website":"www.heckingood.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Germany","company":"SmartPaws Germany","website":"www.smartpaws.de","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Buddies Pet Insurance","website":"www.buddies.co.uk","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Canada","company":"PHI Direct","website":"www.phidirect.com","opType":"Only Sale","group":"Trupanion","link":"https://www.reviews.io/company-reviews/store/phidirect","underwriter":""},
    {"country":"Japan","company":"Rakuten Japan","website":"www.rakuten-ssi.co.jp","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Germany","company":"Paw Protect Germany","website":"www.paw-protect.de","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"USA","company":"Toto Pet Insurance","website":"www.totopetinsurance.com","opType":"Only Sale","group":"JAB","link":"","underwriter":""},
    {"country":"Belgium","company":"Petexpert by trupanion BE","website":"www.petexpert.be","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Segurvet España","website":"www.segurvet.es","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Chile","company":"Pawer Chile","website":"www.somospawer.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Perú","company":"Pawer Perú","website":"www.somospawer.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Colombia","company":"Seguro Salud Mascotas SURA","website":"aseguratupeludo.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Chile","company":"Woof! Seguros de mascotas","website":"woof.cl","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Brazil","company":"Petlove","website":"saude.petlove.com.br","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Musky","website":"musky.es","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Milopet","website":"milopet.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Mapfre","website":"www.mapfre.es","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Santalucia","website":"www.santalucia.es","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Sanitas","website":"www.sanitas.es","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Linea Directa","website":"www.lineadirecta.com","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Generali","website":"www.generali.es","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"AXA España","website":"www.axa.es","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Caser","website":"www.caser.es","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Verti","website":"www.verti.es","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Tuio","website":"tuio.com","opType":"Full Service","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Terranea","website":"www.terranea.es","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"UK","company":"Petsure UK","website":"www.petsure.com","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Swipet","website":"swipet.es","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"Mascotasegura","website":"mascotasegura.es","opType":"Only Sale","group":"","link":"","underwriter":""},
    {"country":"Spain","company":"DKV Seguros España","website":"www.dkv.es","opType":"Full Service","group":"","link":"","underwriter":""},
]

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _int(s):
    m = re.search(r'\d+', str(s).replace(',','').replace('.',''))
    return int(m.group()) if m else 0

# Generic words that appear in many company names — they must NOT be used on
# their own to confirm a match, otherwise unrelated "... Pet Insurance" listings
# get accepted as the right company (this was the main Google Maps bug).
_GENERIC_WORDS = {
    "pet","pets","insurance","insurances","assurance","assurances","seguro",
    "seguros","seguranca","versicherung","versicherungen","assicurazione",
    "animal","animals","animaux","mascota","mascotas","health","cover","care",
    "haustier","haustierversicherung","tierversicherung","tierkrankenversicherung",
    "the","and","for","por","para","della","delle","cane","gatto","dog","dogs",
    "cat","cats","group","ltd","limited","plc","inc","sa","srl","gmbh","by",
    # generic business/sector words that wrongly matched unrelated companies
    "direct","online","plus","vet","vets","veterinario","veterinaria",
    "veterinary","veterinaire","salud","saude","sante","santé","tier","tiere",
    "shelter","quotes","quote","comparador","comparateur","seguri","aseguradora",
    # geographic words — a country/region name must NEVER confirm a match
    # (this caused "Pshoken JAPAN"->"JAPAN Experience", "Paw Protect GERMANY"->"Lebara GERMANY")
    "japan","germany","deutschland","france","spain","espana","espagne",
    "italy","italia","ireland","eire","sweden","sverige","norway","norge",
    "denmark","danmark","netherlands","nederland","holland","belgium","belgique",
    "belgie","switzerland","suisse","schweiz","svizzera","austria","osterreich",
    "canada","australia","aussie","mexico","peru","colombia","chile","brazil",
    "brasil","argentina","portugal","usa","uk","europe","european","czech",
    "czechia","cesko","poland","polska","newzealand","zealand","africa",
}

def _deaccent(s):
    """Lowercase and strip accents so 'SantéVet' == 'santevet'."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()

def brand_tokens(company_name):
    """Distinctive (non-generic) lowercase, accent-free tokens for the brand."""
    norm = _deaccent(company_name)
    toks = [w for w in re.findall(r"[a-z0-9]+", norm)
            if len(w) > 2 and w not in _GENERIC_WORDS]
    # If a name is ENTIRELY generic (rare), fall back to all words >2 chars
    if not toks:
        toks = [w for w in re.findall(r"[a-z0-9]+", norm) if len(w) > 2]
    return toks

def domain_tokens(website):
    """Tokens from the registrable domain, e.g. 'petplan.co.uk' -> ['petplan']."""
    if not website:
        return []
    d = re.sub(r'^https?://', '', website).rstrip('/').split('/')[0]
    d = re.sub(r'^www\.', '', d)
    parts = d.split('.')
    core = parts[0] if parts else d
    return [t for t in re.findall(r"[a-z0-9]+", core.lower()) if len(t) > 2]

def label_matches_company(label, company_name, website=""):
    """
    True when an aria-label / title plausibly belongs to this company.

    Matching rules (deliberately strict, to avoid wrong-company matches such as
    "Pshoken Japan"->"Japan Experience" or "PHI Direct"->"Philip Morris Direct"):
      1. A DISTINCTIVE brand/domain token must appear as a WHOLE WORD in the label
         (exact word match, not a substring — so 'phi' no longer matches 'philip',
         and 'direct' no longer matches 'philipmorrisdirect').
      2. Generic and geographic words ('japan', 'germany', 'direct', 'pet', …)
         never count toward a match.
      3. A long compound brand (>=6 chars, e.g. 'lifetimepetcover') may match the
         label with spacing removed, and the full collapsed name (>=8 chars) may
         match too — both safe because they are long and specific.
    """
    if not label:
        return False
    nlabel = _deaccent(label)
    label_words = set(re.findall(r"[a-z0-9]+", nlabel))     # whole words in the label
    collapsed_label = re.sub(r'[^a-z0-9]', '', nlabel)      # spacing/punct removed

    btoks = brand_tokens(company_name)
    dtoks = [t for t in domain_tokens(website) if t not in _GENERIC_WORDS]
    for t in set(btoks + dtoks):
        if not t:
            continue
        # exact whole-word match — the reliable signal
        if t in label_words:
            return True
        # long, specific tokens may match a spaced-out compound label
        if len(t) >= 6 and t in collapsed_label:
            return True

    # Spacing/punctuation-tolerant full-name match, e.g. company "Lifetimepetcover"
    # vs label "Lifetime Pet Cover". Raised to >=8 chars so short generic names
    # can't produce accidental matches.
    collapsed_company = re.sub(r'[^a-z0-9]', '', _deaccent(company_name))
    if len(collapsed_company) >= 8 and collapsed_company in collapsed_label:
        return True
    return False

def _domain_core(s):
    """Registrable-name core of a URL or domain: 'www.agria.dk' -> 'agria'."""
    if not s:
        return ""
    d = re.sub(r'^https?://', '', str(s)).rstrip('/').split('/')[0]
    d = re.sub(r'^www\.', '', d)
    return (d.split('.')[0] if d else "").lower()

def _tp_profile_domain(tp_url):
    """Reviewed-domain core inside a Trustpilot URL:
    '.../review/www.agria.dk' -> 'agria'."""
    m = re.search(r'/review/([^/?#]+)', str(tp_url or ""))
    return _domain_core(m.group(1)) if m else ""

def tp_profile_belongs_to(tp_url, website):
    """Strict guard for search-fallback matches: a Trustpilot profile is only
    accepted if its reviewed domain core EQUALS the company's own website core.
    This stops same-name profiles from another country/parent being attached
    (e.g. Pawer Perú must not borrow 'pawer.fr', Colombia 'SURA' must not borrow
    'sura.co.uk', Petexpert BE/CZ must not borrow 'trupanion.com').
    When the company has no website on file we cannot domain-check, so we allow
    the name match to stand."""
    wc = _domain_core(website)
    if not wc:
        return True
    pc = _tp_profile_domain(tp_url)
    if not pc:
        return False
    if pc == wc:
        return True
    # Accept a MORE-SPECIFIC sub-brand domain that contains the website core,
    # e.g. website 'agria.ie' vs profile 'agriapetinsure.ie' (the real Irish
    # sub-brand). Still rejects shorter/foreign same-name domains: a Perú site
    # 'somospawer.com' will NOT match 'pawer.fr', and 'aseguratupeludo.com'
    # will NOT match 'sura.co.uk'.
    if len(wc) >= 4 and wc in pc:
        return True
    return False

def calc(tp_s, tp_r, g_s, g_r):
    total = tp_r + g_r
    pond  = round((tp_s*tp_r + g_s*g_r)/total, 2) if total else 0.0
    avg   = round((tp_s+g_s)/2, 2) if tp_s and g_s else (tp_s or g_s or 0.0)
    return pond, avg, total

def accept_consent(page):
    for sel in [
        'button[aria-label*="Accept all"]','button[aria-label*="Accepter"]',
        'button[aria-label*="Aceitar"]','button[jsname="b3VHJd"]',
        '#L2AGLb','button.tHlp8d','form[action*="consent"] button:last-child',
    ]:
        try:
            b = page.query_selector(sel)
            if b: b.click(); page.wait_for_timeout(800); return
        except Exception: pass

# ─────────────────────────────────────────────────────────────
# TRUSTPILOT  — search-first approach
# ─────────────────────────────────────────────────────────────
def _parse_tp_html(content):
    """Extract (score, reviews) from Trustpilot page HTML. Pure string parsing,
    no browser — usable both from Playwright (page.content()) and plain HTTP."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.DOTALL)
    if m:
        try:
            text = m.group(1)
            sc = re.search(r'"trustScore"\s*:\s*([\d.]+)', text)
            ct = re.search(r'"numberOfReviews"\s*:\s*(\d+)', text)
            if sc and float(sc.group(1)) > 0:
                return round(float(sc.group(1)), 1), int(ct.group(1) if ct else 0)
        except Exception: pass
    for raw in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', content, re.DOTALL):
        try:
            data  = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                ar = item.get("aggregateRating") or {}
                rv = ar.get("ratingValue") or ar.get("ratingvalue")
                rc = ar.get("reviewCount") or ar.get("ratingCount") or ar.get("numberOfRatings")
                if rv and float(rv) > 0:
                    return round(float(rv), 1), _int(rc or 0)
        except Exception: pass
    m_s = re.search(r'"ratingValue"\s*:\s*"?([\d.]+)"?', content)
    m_c = re.search(r'"(?:reviewCount|numberOfRatings|ratingCount|numberOfReviews)"\s*:\s*"?(\d[\d,]*)"?', content)
    if m_s and float(m_s.group(1)) > 0:
        return round(float(m_s.group(1)), 1), _int(m_c.group(1) if m_c else 0)
    return 0.0, 0

def _extract_tp(page):
    """Browser version: parse the page HTML, then a DOM fallback."""
    s, c = _parse_tp_html(page.content())
    if s > 0:
        return s, c
    try:
        r = page.eval_on_selector('[data-rating-typography="true"]', 'el => el.textContent.trim()')
        if r:
            score = float(r.replace(',', '.'))
            if 1 <= score <= 5:
                ct = 0
                try:
                    ct_t = page.eval_on_selector('[data-reviews-count-typography="true"]', 'el => el.textContent.trim()')
                    ct = _int(ct_t or 0)
                except Exception: pass
                return round(score, 1), ct
    except Exception: pass
    return 0.0, 0

def fetch_trustpilot(page, company_name, website):
    """
    Fetch Trustpilot score + review count.
    Returns (status, score, reviews, url) where status is:
      "ok"          a profile that MATCHES this company was found
      "not_listed"  Trustpilot reachable but the company has no profile
      "error"       navigation/network failure (caller keeps previous value)
    `url` is the exact Trustpilot profile URL of the matched company (so the
    dashboard source link goes to the right company), or "" when not found.

    Strategy:
      1. Direct URL via website domain (fastest)
      2. Trustpilot search by company name (brand-token validated)
    """
    reached_page = False

    # Build candidate domains from website
    domains = []
    if website:
        d = re.sub(r'^https?://', '', website).rstrip('/').split('/')[0]
        domains.append(d)
        if d.startswith('www.'):
            domains.append(d[4:])

    for domain in domains:
        try:
            url = f"https://www.trustpilot.com/review/{domain}"
            resp = page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if resp is not None:
                reached_page = True
                if resp.status in (200, 304):
                    page.wait_for_timeout(random.randint(800, 1400))
                    s, c = _extract_tp(page)
                    if s > 0:
                        return "ok", s, c, url
                # 404 etc. → this domain has no profile; try the next candidate
        except Exception:
            pass
        time.sleep(0.3)

    # Search fallback — find the company by name and validate the match
    search_queries = [company_name]
    simple = ' '.join(company_name.split()[:3])
    if simple != company_name:
        search_queries.append(simple)

    for query in search_queries:
        try:
            q   = urllib.parse.quote_plus(query)
            url = f"https://www.trustpilot.com/search?query={q}"
            page.goto(url, wait_until="domcontentloaded", timeout=18000)
            reached_page = True
            page.wait_for_timeout(random.randint(1000, 1800))

            # Pick the first review link whose label matches a brand token.
            links = page.query_selector_all('a[href*="/review/"]')
            best_link = None
            for link in links[:8]:
                try:
                    label = (link.get_attribute('aria-label') or
                             link.inner_text() or '')
                    if label_matches_company(label, company_name, website):
                        best_link = link
                        break
                except Exception:
                    pass

            if best_link:
                href = best_link.get_attribute('href') or ''
                if '/review/' in href:
                    full = href if href.startswith('http') else 'https://www.trustpilot.com' + href
                    # Strict: the matched profile's domain must be THIS company's
                    # own domain — otherwise it's a same-name profile from another
                    # country/parent and we must not attach it.
                    if not tp_profile_belongs_to(full, website):
                        log(f"            TP search: {full.split('/review/')[-1]} "
                            f"!= {website} — rejecting (wrong domain)")
                        continue
                    page.goto(full, wait_until="domcontentloaded", timeout=18000)
                    page.wait_for_timeout(random.randint(800, 1400))
                    s, c = _extract_tp(page)
                    if s > 0:
                        return "ok", s, c, full
        except Exception:
            pass

    # Reached Trustpilot but found no matching profile → genuinely not listed.
    return ("not_listed" if reached_page else "error"), 0.0, 0, ""

# ─────────────────────────────────────────────────────────────
# GOOGLE MAPS  — official Google Places API (exact, reliable)
# ─────────────────────────────────────────────────────────────
# Why the API instead of scraping: the Places API returns the EXACT current
# rating and review count, plus the canonical Google Maps URL of the matched
# place — so the dashboard's source link goes to the right company, and the
# numbers always match what you see on Google.
#
# Get a key:  https://console.cloud.google.com/google/maps-apis
#   1. Create a project, enable "Places API (New)".
#   2. Create an API key (billing must be on; the free monthly credit easily
#      covers a daily run of ~145 companies).
#   3. Put the key in google_api_key.txt next to this script, OR in config.json
#      as {"google_places_api_key": "..."}, OR set env GOOGLE_PLACES_API_KEY.

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELDS = ("places.id,places.displayName,places.rating,"
                 "places.userRatingCount,places.googleMapsUri,"
                 "places.websiteUri,places.formattedAddress,places.types")

def _load_google_api_key():
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if key:
        return key
    for fname in ("google_api_key.txt", "GOOGLE_API_KEY.txt"):
        p = os.path.join(HERE, fname)
        if os.path.exists(p):
            try:
                k = open(p, encoding="utf-8").read().strip()
                if k:
                    return k
            except Exception:
                pass
    cfg = os.path.join(HERE, "config.json")
    if os.path.exists(cfg):
        try:
            data = json.load(open(cfg, encoding="utf-8"))
            k = (data.get("google_places_api_key") or "").strip()
            if k:
                return k
        except Exception:
            pass
    return ""

GOOGLE_API_KEY = _load_google_api_key()

def _places_search(query, region=None):
    body = {"textQuery": query, "maxResultCount": 5}
    if region:
        body["regionCode"] = region
    req = urllib.request.Request(
        PLACES_URL, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Goog-Api-Key", GOOGLE_API_KEY)
    req.add_header("X-Goog-FieldMask", PLACES_FIELDS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

# Map of country name -> ISO region code to bias the search to the right place.
_REGION = {
    "USA":"US","UK":"GB","Ireland":"IE","France":"FR","Germany":"DE","Italy":"IT",
    "Spain":"ES","Sweden":"SE","Norway":"NO","Denmark":"DK","Switzerland":"CH",
    "Belgium":"BE","Netherland":"NL","Netherlands":"NL","Australia":"AU",
    "New Zealand":"NZ","Canada":"CA","Japan":"JP","South Africa":"ZA",
    "Czech Republic":"CZ","Argentina":"AR","Chile":"CL","Colombia":"CO",
    "Brazil":"BR","México":"MX","Mexico":"MX","Perú":"PE","Peru":"PE",
}

def _place_matches(place, company_name, website):
    """A place is the right company if its name OR website domain matches."""
    name = (place.get("displayName") or {}).get("text", "") or ""
    if label_matches_company(name, company_name, website):
        return True
    wuri = (place.get("websiteUri") or "").lower()
    dtoks = domain_tokens(website)
    if wuri and dtoks and dtoks[0] in wuri:
        return True
    return False

def fetch_google_maps(company_name, country, website=""):
    """
    Fetch Google rating + review count via the official Places API.
    Returns (status, score, reviews, maps_url):
      "ok"          a place matching this company was found
      "not_listed"  the API returned results but none match this company
                    (or the company has no Google place) → "Not on Google Maps"
      "error"       no API key, or an API/network error → keep previous value
    """
    if not GOOGLE_API_KEY:
        return "error", 0.0, 0, ""

    region = _REGION.get((country or "").strip())
    queries = [f"{company_name} {country}".strip(),
               f"{company_name} pet insurance {country}".strip()]
    reached = False
    for q in queries:
        try:
            data = _places_search(q, region=region)
            reached = True
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")[:160]
            except Exception:
                pass
            log(f"            Google Places HTTP {e.code}: {detail}")
            if e.code in (400, 401, 403):   # key/billing/setup problem → stop
                return "error", 0.0, 0, ""
            continue
        except Exception as e:
            log(f"            Google Places error: {e}")
            continue

        places = data.get("places") or []
        for p in places:
            if _place_matches(p, company_name, website):
                rating = p.get("rating")
                count = p.get("userRatingCount")
                url = p.get("googleMapsUri", "") or ""
                if rating is not None:
                    return "ok", round(float(rating), 1), int(count or 0), url
                # Place exists but has no rating yet
                return "ok", 0.0, 0, url
        # results came back but none matched → try the next query
    return ("not_listed" if reached else "error"), 0.0, 0, ""


# ─────────────────────────────────────────────────────────────
# EMERGING COMPANIES  — auto-discover new insurers with 500+ opinions
# ─────────────────────────────────────────────────────────────
_KNOWN_NAMES_CACHE: set = set()

def _known_names():
    global _KNOWN_NAMES_CACHE
    if not _KNOWN_NAMES_CACHE:
        _KNOWN_NAMES_CACHE = {c["company"].lower() for c in COMPANIES}
        if os.path.exists(JSON_PATH):
            try:
                with open(JSON_PATH, encoding="utf-8") as f:
                    for c in json.load(f):
                        _KNOWN_NAMES_CACHE.add(c["company"].lower())
            except Exception:
                pass
    return _KNOWN_NAMES_CACHE


def _walk_business_units(obj, out):
    """Recursively pull (name, domain, score, reviews) business units from any
    nested Trustpilot __NEXT_DATA__ JSON structure."""
    if isinstance(obj, dict):
        name = obj.get("displayName") or obj.get("name")
        nrev = obj.get("numberOfReviews")
        if isinstance(nrev, dict):
            nrev = nrev.get("total")
        score = obj.get("trustScore")
        if score is None:
            score = obj.get("stars")
        dom = obj.get("identifyingName") or obj.get("websiteUrl") or obj.get("domain") or ""
        if name and nrev is not None and score is not None:
            try:
                out.append({"name": str(name), "website": str(dom),
                            "score": float(score or 0), "reviews": int(nrev or 0)})
            except (TypeError, ValueError):
                pass
        for v in obj.values():
            _walk_business_units(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_business_units(v, out)

def discover_emerging_companies(page, existing_results, min_opinions=500, max_pages=4):
    """
    Scrape Trustpilot's 'pet_insurance_agency' category for companies not yet tracked
    that have at least min_opinions total reviews.  Returns a list of new company dicts.
    """
    log(f"\n🔍 Discovering emerging companies online (> {min_opinions-1} reviews)…")
    known   = _known_names()
    found   = []
    base_url = "https://www.trustpilot.com/categories/pet_insurance_agency"

    for pg in range(1, max_pages + 1):
        url = base_url if pg == 1 else f"{base_url}?page={pg}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(random.randint(1200, 2000))
            content = page.content()

            # Each business card has JSON-LD or embedded data-business-unit attributes
            # Extract all (name, reviewCount, ratingValue) triples visible on the page
            cards = page.evaluate("""
                () => Array.from(document.querySelectorAll('[data-business-unit-display-name]'))
                        .map(el => ({
                            name:    el.getAttribute('data-business-unit-display-name') || '',
                            website: el.getAttribute('data-website-url') || '',
                            score:   parseFloat(el.getAttribute('data-trustscore') || '0'),
                            reviews: parseInt(el.getAttribute('data-number-of-reviews') || '0'),
                        }))
            """) or []

            # Primary modern method: parse the Next.js __NEXT_DATA__ payload
            if not cards:
                mnd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                                content, re.DOTALL)
                if mnd:
                    try:
                        nd = json.loads(mnd.group(1))
                        tmp = []
                        _walk_business_units(nd, tmp)
                        seen = set()
                        for bu in tmp:
                            k = bu["name"].lower()
                            if k in seen:
                                continue
                            seen.add(k)
                            cards.append(bu)
                    except Exception:
                        pass

            # Also try JSON-LD blocks (fallback)
            if not cards:
                for raw in re.findall(
                    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                    content, re.DOTALL
                ):
                    try:
                        data = json.loads(raw)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get('@type') in ('LocalBusiness', 'Organization', 'InsuranceAgency'):
                                ar = item.get('aggregateRating', {})
                                name = item.get('name', '')
                                reviews = int(ar.get('reviewCount', 0) or ar.get('ratingCount', 0) or 0)
                                score   = float(ar.get('ratingValue', 0) or 0)
                                web     = item.get('url', '')
                                if name:
                                    cards.append({'name': name, 'website': web,
                                                  'score': score, 'reviews': reviews})
                    except Exception:
                        pass

            for card in cards:
                name    = (card.get('name') or '').strip()
                reviews = int(card.get('reviews') or 0)
                score   = float(card.get('score') or 0)
                web     = (card.get('website') or '').strip()

                if not name or name.lower() in known:
                    continue
                if reviews < min_opinions:
                    continue

                log(f"   ✨ New company found: {name}  ({reviews:,} reviews, {score} TP score)")
                known.add(name.lower())
                found.append({
                    "country":       "Unknown",   # will be inferred if possible
                    "company":       name,
                    "website":       web,
                    "opType":        "Only Sale",
                    "group":         "",
                    "link":          "",
                    "underwriter":   "",
                    "tpScore":       round(score, 1),
                    "tpReviews":     reviews,
                    "gScore":        0.0,
                    "gReviews":      0,
                    "pondScore":     round(score, 1),
                    "avgScore":      round(score, 1),
                    "totalOpinions": reviews,
                    "date":          datetime.now().strftime("%Y-%m-%d"),
                    "_auto_discovered": True,
                })

        except Exception as e:
            log(f"   ⚠️  Emerging-company page {pg} error: {e}")

    log(f"🔍 Discovery done — {len(found)} new emerging companies added.")
    return found

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
_HTTP_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=_HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read().decode("utf-8", "ignore")

def fetch_trustpilot_http(company_name, website):
    """Browser-free Trustpilot fetch (cloud server). Returns (status, score, reviews, url).
    Key rule: a BLOCK (403/429/5xx/network) is NOT 'not_listed' — we return 'error'
    so the caller keeps the previous real value. Only a clean 404 (or a search that
    finds nothing) counts as genuinely not on Trustpilot."""
    domains = []
    if website:
        d = re.sub(r'^https?://', '', website).rstrip('/').split('/')[0]
        domains.append(d)
        domains.append(d[4:] if d.startswith('www.') else 'www.' + d)

    state = {"saw_404": False, "saw_block": False}

    def _try(url):
        try:
            code, html = _http_get(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                state["saw_404"] = True
            else:                       # 403 / 429 / 5xx => blocked, not "missing"
                state["saw_block"] = True
            return None
        except Exception:
            state["saw_block"] = True
            return None
        sc, ct = _parse_tp_html(html)
        return (sc, ct) if sc > 0 else None

    # 1) Direct profile by website domain
    for dom in domains:
        url = f"https://www.trustpilot.com/review/{dom}"
        r = _try(url)
        if r:
            return "ok", r[0], r[1], url

    # 2) Search fallback (only worth trying if we were not blocked)
    if not state["saw_block"]:
        try:
            code, html = _http_get(
                "https://www.trustpilot.com/search?query=" + urllib.parse.quote_plus(company_name))
            mnd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if mnd:
                units = []
                _walk_business_units(json.loads(mnd.group(1)), units)
                for u in units:
                    if label_matches_company(u.get("name", ""), company_name, website):
                        dom = (u.get("website") or "").strip()
                        # Strict: the matched profile's domain must be THIS
                        # company's own domain (reject same-name foreign/parent).
                        if not tp_profile_belongs_to(f"/review/{dom}", website):
                            continue
                        sc = float(u.get("score") or 0); ct = int(u.get("reviews") or 0)
                        url = f"https://www.trustpilot.com/review/{dom}" if dom else \
                              "https://www.trustpilot.com/search?query=" + urllib.parse.quote_plus(company_name)
                        if sc > 0:
                            return "ok", round(sc, 1), ct, url
        except urllib.error.HTTPError as e:
            if e.code != 404:
                state["saw_block"] = True
        except Exception:
            pass

    if state["saw_block"]:
        return "error", 0.0, 0, ""        # blocked -> keep previous real value
    if state["saw_404"]:
        return "not_listed", 0.0, 0, ""   # genuinely no profile
    return "error", 0.0, 0, ""

def discover_emerging_companies_http(existing_results, min_opinions=501, max_pages=4):
    """Browser-free version of emerging-company discovery (Trustpilot category)."""
    log(f"\n🔍 Discovering emerging companies online (> {min_opinions-1} reviews)…")
    known = _known_names()
    found = []
    base  = "https://www.trustpilot.com/categories/pet_insurance_agency"
    for pg in range(1, max_pages + 1):
        url = base if pg == 1 else f"{base}?page={pg}"
        try:
            code, content = _http_get(url, timeout=20)
        except Exception as e:
            log(f"   ⚠️  category page {pg} error: {e}")
            continue
        cards = []
        mnd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.DOTALL)
        if mnd:
            try:
                nd = json.loads(mnd.group(1)); tmp = []; _walk_business_units(nd, tmp)
                seen = set()
                for bu in tmp:
                    k = bu["name"].lower()
                    if k in seen: continue
                    seen.add(k); cards.append(bu)
            except Exception: pass
        for card in cards:
            name = (card.get("name") or "").strip()
            reviews = int(card.get("reviews") or 0)
            score = float(card.get("score") or 0)
            web = (card.get("website") or "").strip()
            if not name or name.lower() in known: continue
            if reviews < min_opinions: continue
            log(f"   ✨ New: {name} ({reviews:,} reviews)")
            known.add(name.lower())
            found.append({
                "country": "Unknown", "company": name, "website": web, "opType": "Only Sale",
                "group": "", "link": "", "underwriter": "",
                "tpScore": round(score, 1), "tpReviews": reviews,
                "gScore": 0.0, "gReviews": 0, "tpStatus": "ok", "gStatus": "not_listed",
                "tpUrl": (f"https://www.trustpilot.com/review/{web}" if web else ""), "gUrl": "",
                "pondScore": round(score, 1), "avgScore": round(score, 1),
                "totalOpinions": reviews, "date": datetime.now().strftime("%Y-%m-%d"),
                "_auto_discovered": True,
            })
    log(f"🔍 Discovery done — {len(found)} new emerging companies added.")
    return found

def _finalize(c, tp_res, g_res, old, today):
    """Apply not_listed/error rules + recompute scores. Returns (result, tp_status, g_status)."""
    tp_status, tp_s, tp_r, tp_url = tp_res
    if tp_status == "not_listed":
        tp_s, tp_r, tp_url = 0.0, 0, ""
    elif tp_status == "error":
        ps = old.get("tpScore", 0) or 0; pr = old.get("tpReviews", 0) or 0
        if ps > 0: tp_status, tp_s, tp_r, tp_url = "ok", ps, pr, (old.get("tpUrl", "") or "")
        else: tp_status, tp_s, tp_r, tp_url = "error", 0.0, 0, ""
    g_status, g_s, g_r, g_url = g_res
    if g_status == "not_listed":
        g_s, g_r, g_url = 0.0, 0, ""
    elif g_status == "error":
        ps = old.get("gScore", 0) or 0; pr = old.get("gReviews", 0) or 0
        if ps > 0: g_status, g_s, g_r, g_url = "ok", ps, pr, (old.get("gUrl", "") or "")
        else: g_status, g_s, g_r, g_url = "error", 0.0, 0, ""
    pond, avg, total = calc(tp_s, tp_r, g_s, g_r)
    return ({**c, "tpScore": tp_s, "tpReviews": tp_r, "gScore": g_s, "gReviews": g_r,
             "tpStatus": tp_status, "gStatus": g_status, "tpUrl": tp_url, "gUrl": g_url,
             "pondScore": pond, "avgScore": avg, "totalOpinions": total, "date": today},
            tp_status, g_status)

_GM_JS = r"""
() => {
    function num(s){ return parseFloat((s||'').replace(',','.').replace(/[^\d.]/g,'')) || 0; }
    function cnt(s){ return parseInt((s||'').replace(/[^\d]/g,'')) || 0; }
    const main = document.querySelector('[role="main"]') || document.body;
    const h1 = main.querySelector('h1');
    const title = (h1 ? h1.textContent : (document.title || '')).trim();
    const f7 = main.querySelector('.F7nice');
    if (f7) {
        let rating = 0;
        for (const sp of f7.querySelectorAll('span[aria-hidden="true"]')) {
            const v = num(sp.textContent);
            if (v >= 1 && v <= 5) { rating = v; break; }
        }
        // Review count — handle European formats too: (11.686), 11 686, 1,234 …
        let count = 0;
        const scopes = [f7, f7.parentElement].filter(Boolean);
        for (const scope of scopes) {
            const txt = scope.innerText || '';
            let m = txt.match(/[\(\[]\s*(\d[\d.,\s ]*\d)\s*[\)\]]/);   // (11.686)
            if (m && cnt(m[1]) > 0) { count = cnt(m[1]); break; }
            m = txt.match(/(\d[\d.,\s ]*\d|\d)\s*(?:reviews?|rese|opinion|avis|recension|bewertung|valoracion|avalia)/i);
            if (m && cnt(m[1]) > 0) { count = cnt(m[1]); break; }
            for (const el of scope.querySelectorAll('[aria-label]')) {
                const lbl = el.getAttribute('aria-label') || '';
                if (/review|rese|opinion|avis|recension|bewertung|valoracion|avalia/i.test(lbl)) {
                    const mm = lbl.match(/(\d[\d.,\s ]*\d|\d)/);
                    if (mm && cnt(mm[1]) > 0) { count = cnt(mm[1]); break; }
                }
            }
            if (count) break;
        }
        if (rating >= 1 && rating <= 5) return {rating, count, title};
    }
    const starEl = main.querySelector('[aria-label$=" stars"]') || main.querySelector('[role="img"][aria-label*="star"]');
    if (starEl) {
        const lbl = starEl.getAttribute('aria-label') || '';
        const mR  = lbl.match(/([1-5][.,]\d)/);
        if (mR) {
            const rating = num(mR[1]); let count = 0; let node = starEl.parentElement;
            for (let i = 0; i < 5 && node; i++) {
                const mT = node.innerText.match(/[\(\[]\s*(\d[\d.,\s ]*\d)\s*[\)\]]/);
                if (mT && cnt(mT[1]) > 0) { count = cnt(mT[1]); break; }
                node = node.parentElement;
            }
            if (rating >= 1 && rating <= 5) return {rating, count, title};
        }
    }
    const mC = main.innerText.match(/\b([1-5][.,]\d)\s*[\(\[](\d[\d,\.\s]{0,9})[\)\]]/);
    if (mC) return {rating: num(mC[1]), count: cnt(mC[2]), title};
    return null;
}
"""

def _pick_best_maps_listing(page, company_name, website=""):
    """Index of the search result whose label matches the company by a brand
    token; -1 if none match (so we never click an unrelated listing)."""
    try:
        labels = page.evaluate("""
            () => Array.from(document.querySelectorAll('a.hfpxzc, .Nv2PK a, [role="article"] a'))
                    .slice(0,8).map((el,i)=>({i, label:(el.getAttribute('aria-label')||el.innerText||'').toLowerCase()}))
        """) or []
    except Exception:
        return -1
    for item in labels:
        if label_matches_company(item.get('label',''), company_name, website):
            return item.get('i', 0)
    return -1

def fetch_google_maps_browser(page, company_name, country, website=""):
    """Free Google Maps fetch via the browser (PC mode), with validation.
    Returns (status, score, reviews, url). Only accepts a listing that matches
    the company; otherwise reports not_listed ('Not on Google Maps')."""
    domain = ""
    if website:
        domain = re.sub(r'^https?://', '', website).rstrip('/').split('/')[0]
    queries = []
    if domain:
        queries.append(domain)
    queries.append(f'"{company_name}" {country} pet insurance')
    reached = False
    for query in queries:
        url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            reached = True
            accept_consent(page)
            page.wait_for_timeout(1500)
            has_panel = bool(page.query_selector('.F7nice, [data-item-id="rating"]'))
            if not has_panel:
                best_idx = _pick_best_maps_listing(page, company_name, website)
                listings = page.query_selector_all('a.hfpxzc, .Nv2PK a, [role="article"] a')
                if not listings:
                    continue
                if best_idx < 0 or best_idx >= len(listings):
                    continue
                listings[best_idx].click()
                try:
                    page.wait_for_selector('.F7nice, [aria-label$=" stars"]', timeout=5000)
                except Exception:
                    page.wait_for_timeout(2500)
            result = page.evaluate(_GM_JS)
            if result:
                r = float(result.get('rating', 0)); c = int(result.get('count', 0))
                title = result.get('title', '') or ''
                if not label_matches_company(title, company_name, website):
                    log(f"            Maps: '{title[:40]}' != {company_name} — rejecting")
                    continue
                # Reject single branch/office listings (e.g. "Oficina Sanitas
                # Sevilla Bellavista") — these are one local office, not the
                # company's representative rating. Big multi-branch insurers
                # therefore correctly show "Not on Google Maps".
                _t = _deaccent(title)
                _branch = ("oficina", "sucursal", "agencia ", "agence ", "filiale")
                if _t.startswith(_branch) and not _deaccent(company_name).startswith(_branch):
                    log(f"            Maps: '{title[:40]}' is a branch office — rejecting")
                    continue
                if 1.0 <= r <= 5.0:
                    return "ok", round(r, 1), c, page.url
        except Exception as e:
            log(f"            Maps error: {e}")
    return ("not_listed" if reached else "error"), 0.0, 0, ""


def run_fetch(companies=None, progress_cb=None, discover=True, use_browser=True,
              google_only=False):
    """
    Main fetch loop.
    - companies : list of company dicts (default: COMPANIES)
    - progress_cb : callable(str) for live log streaming
    - discover : whether to auto-discover emerging companies (≥500 opinions)
    - use_browser : True = PC mode (browser scrape both sources, free).
                    False = server mode (HTTP / Places API).
    - google_only : server mode only. Refresh GOOGLE live via the Places API and
                    KEEP the existing Trustpilot numbers untouched (with their
                    original 'as of' date). This is the hands-off cloud setup:
                    Trustpilot can't be scraped reliably from a data-center, so
                    we never overwrite good Trustpilot data with a blocked fetch.
    """
    if progress_cb:
        set_progress_callback(progress_cb)
    if companies is None:
        companies = COMPANIES

    today = datetime.now().strftime("%Y-%m-%d")

    # Load previous values — used ONLY as a last resort when live fetch
    # returns 0 AND no alternative query succeeded.
    prev = {}
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, encoding="utf-8") as f:
                for c in json.load(f):
                    prev[c["company"]] = c
        except Exception:
            pass

    log("=" * 60)
    log(f"LIVE FETCH  {today}  |  {len(companies)} companies")
    log("=" * 60)
    if use_browser:
        log("Google: free browser check (validated). No API key needed in PC mode.")
    elif GOOGLE_API_KEY:
        log("Google: using Places API key ✅")
    else:
        log("⚠️  Server mode without a Places API key — Google will keep previous "
            "values. Run the fetch on your PC (browser mode) for free Google data.")

    results = []
    tp_ok = tp_fail = gm_ok = gm_fail = 0

    if use_browser:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-blink-features=AutomationControlled",
                      "--window-size=1400,900"]
            )
            ctx = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"),
                viewport={"width": 1400, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
            )
            tp_page  = ctx.new_page()
            gm_page  = ctx.new_page()
            disc_page = ctx.new_page()   # separate page for discovery, doesn't interfere
            log("Browser ready (Trustpilot + Google Maps + Discovery) — free PC fetch.")

            for i, c in enumerate(companies, 1):
                name    = c["company"]
                website = c.get("website", "")
                country = c.get("country", "")
                old     = prev.get(name, {})

                log(f"\n[{i:3d}/{len(companies)}] {name}  ({country})")

                # ── Trustpilot ────────────────────────────────────────────
                tp_status, tp_s, tp_r, tp_url = fetch_trustpilot(tp_page, name, website)
                if tp_status == "ok":
                    tp_ok += 1
                    old_s = old.get("tpScore", 0)
                    changed = f"  [was {old_s}]" if old_s and old_s != tp_s else ""
                    log(f"         ✅ TP  score={tp_s}  reviews={tp_r:,}{changed}")
                elif tp_status == "not_listed":
                    tp_s, tp_r, tp_url = 0.0, 0, ""
                    tp_fail += 1
                    log(f"         🚫 TP  Not on Trustpilot")
                else:  # error — keep previous value only if we actually have one
                    prev_s = old.get("tpScore", 0) or 0
                    prev_r = old.get("tpReviews", 0) or 0
                    if prev_s > 0:
                        tp_status, tp_s, tp_r = "ok", prev_s, prev_r
                        tp_url = old.get("tpUrl", "") or ""
                        log(f"         ⚠️  TP  fetch error — kept previous {tp_s} / {tp_r:,}")
                    else:
                        tp_status, tp_s, tp_r, tp_url = "error", 0.0, 0, ""
                        log(f"         ⚠️  TP  fetch error — no data")
                    tp_fail += 1
                time.sleep(random.uniform(0.4, 0.8))

                # ── Google Maps (free browser fetch, validated) ────────────
                g_status, g_s, g_r, g_url = fetch_google_maps_browser(gm_page, name, country, website=website)
                if g_status == "ok":
                    gm_ok += 1
                    old_gs = old.get("gScore", 0)
                    changed = f"  [was {old_gs}]" if old_gs and old_gs != g_s else ""
                    log(f"         ✅ GM  score={g_s}  reviews={g_r:,}{changed}")
                elif g_status == "not_listed":
                    g_s, g_r, g_url = 0.0, 0, ""
                    gm_fail += 1
                    log(f"         🚫 GM  Not on Google Maps")
                else:  # error — keep previous value only if we actually have one
                    prev_gs = old.get("gScore", 0) or 0
                    prev_gr = old.get("gReviews", 0) or 0
                    if prev_gs > 0:
                        g_status, g_s, g_r = "ok", prev_gs, prev_gr
                        g_url = old.get("gUrl", "") or ""
                        log(f"         ⚠️  GM  fetch error — kept previous {g_s} / {g_r:,}")
                    else:
                        g_status, g_s, g_r, g_url = "error", 0.0, 0, ""
                        log(f"         ⚠️  GM  fetch error / no API key — no data")
                    gm_fail += 1
                time.sleep(random.uniform(0.2, 0.4))

                pond, avg, total = calc(tp_s, tp_r, g_s, g_r)
                log(f"         📊 Pond={pond}  Avg={avg}  Total={total:,}")

                results.append({**c,
                    "tpScore": tp_s,   "tpReviews": tp_r,
                    "gScore":  g_s,    "gReviews":  g_r,
                    "tpStatus": tp_status, "gStatus": g_status,
                    "tpUrl": tp_url,   "gUrl": g_url,
                    "pondScore": pond, "avgScore": avg,
                    "totalOpinions": total, "date": today,
                    "tpDate": today,   "gDate": today,
                })

            # ── Emerging companies discovery ───────────────────────────
            if discover:
                emerging = discover_emerging_companies(
                    disc_page, results, min_opinions=501, max_pages=4
                )
                if emerging:
                    results = emerging + results
                    log(f"✨ {len(emerging)} emerging companies appended to dataset.")

            browser.close()
    elif google_only:
        # ── Hands-off cloud refresh: Google live, Trustpilot kept as snapshot ──
        log("Server mode (Google-only): refreshing Google live via Places API; "
            "Trustpilot kept as its existing dated snapshot.")
        for i, c in enumerate(companies, 1):
            name    = c["company"]
            website = c.get("website", "")
            country = c.get("country", "")
            old     = prev.get(name, {})
            log(f"\n[{i:3d}/{len(companies)}] {name}  ({country})")

            # Trustpilot: preserve previous values + their original 'as of' date.
            tp_s   = old.get("tpScore", c.get("tpScore", 0)) or 0
            tp_r   = old.get("tpReviews", c.get("tpReviews", 0)) or 0
            tp_url = old.get("tpUrl", c.get("tpUrl", "")) or ""
            tp_status = old.get("tpStatus", c.get("tpStatus", "ok")) or "ok"
            tp_date = old.get("tpDate") or old.get("date") or c.get("tpDate") or today

            # Google: live via Places API.
            g_res = fetch_google_maps(name, country, website=website)
            g_status, g_s, g_r, g_url = g_res
            if g_status == "not_listed":
                g_s, g_r, g_url = 0.0, 0, ""
            elif g_status == "error":   # API/network problem → keep previous Google value
                pgs = old.get("gScore", 0) or 0; pgr = old.get("gReviews", 0) or 0
                if pgs > 0:
                    g_status, g_s, g_r, g_url = "ok", pgs, pgr, (old.get("gUrl", "") or "")
                else:
                    g_status, g_s, g_r, g_url = "error", 0.0, 0, ""
            if g_status == "ok": gm_ok += 1
            else: gm_fail += 1
            if tp_status == "ok" and tp_s > 0: tp_ok += 1
            else: tp_fail += 1

            pond, avg, total = calc(tp_s, tp_r, g_s, g_r)
            results.append({**c,
                "tpScore": tp_s,   "tpReviews": tp_r,
                "gScore":  g_s,    "gReviews":  g_r,
                "tpStatus": tp_status, "gStatus": g_status,
                "tpUrl": tp_url,   "gUrl": g_url,
                "pondScore": pond, "avgScore": avg,
                "totalOpinions": total, "date": today,
                "tpDate": tp_date, "gDate": today,
            })
            log(f"         TP(kept {tp_date}) {tp_status} {tp_s}/{tp_r:,}  |  "
                f"G(live) {g_status} {g_s}/{g_r:,}")
            time.sleep(0.1)
        # No discovery in google_only mode (category scraping is also blocked on
        # data-center hosts and would just waste time).
    else:
        log("Server mode: browser-free fetch (Trustpilot via HTTPS, Google via Places API).")
        for i, c in enumerate(companies, 1):
            name    = c["company"]
            website = c.get("website", "")
            country = c.get("country", "")
            old     = prev.get(name, {})
            log(f"\n[{i:3d}/{len(companies)}] {name}  ({country})")
            tp_res = fetch_trustpilot_http(name, website)
            g_res  = fetch_google_maps(name, country, website=website)
            res, ts, gs = _finalize(c, tp_res, g_res, old, today)
            res["tpDate"] = today; res["gDate"] = today
            results.append(res)
            if ts == "ok": tp_ok += 1
            else: tp_fail += 1
            if gs == "ok": gm_ok += 1
            else: gm_fail += 1
            log(f"         TP {res['tpStatus']} {res['tpScore']}/{res['tpReviews']:,}  |  "
                f"G {res['gStatus']} {res['gScore']}/{res['gReviews']:,}")
            time.sleep(0.15)
        if discover:
            emerging = discover_emerging_companies_http(results, min_opinions=501)
            if emerging:
                results = emerging + results
                log(f"✨ {len(emerging)} emerging companies appended to dataset.")

    log("\n" + "=" * 60)
    log(f"Trustpilot  : {tp_ok} live  |  {tp_fail} kept previous")
    log(f"Google Maps : {gm_ok} live  |  {gm_fail} kept previous")
    log("=" * 60)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log(f"✅ Saved {len(results)} companies → {JSON_PATH}")

    if os.path.exists(HTML_PATH):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
        new_js = "const SEED_DATA = " + json.dumps(results, ensure_ascii=False, separators=(",", ":")) + ";"
        html   = re.sub(r"const SEED_DATA\s*=\s*\[.*?\];", new_js, html, flags=re.DOTALL)
        stamp  = datetime.now().strftime("%Y-%m-%d %H:%M")
        html   = re.sub(
            r"(getElementById\(\'lastUpdated\'\)\.textContent\s*=\s*')[^\']*(\')",
            f"\\1Updated: {stamp} (live)\\2", html)
        with open(HTML_PATH, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"✅ HTML updated with live data ({stamp})")

    log("🎉 Fetch complete!")

    # ── Auto-upload to cloud server ───────────────────────────
    if CLOUD_URL and CLOUD_KEY:
        try:
            log(f"☁️  Uploading to cloud: {CLOUD_URL} …")
            payload = json.dumps(results, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                f"{CLOUD_URL.rstrip('/')}/api/upload",
                data=payload,
                headers={"Content-Type": "application/json",
                         "X-Upload-Key": CLOUD_KEY},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                reply = json.loads(resp.read())
            log(f"☁️  Cloud updated ✅  companies={reply.get('companies')}  at {reply.get('updated','')[:16]}")
        except Exception as e:
            log(f"☁️  Cloud upload failed (data saved locally): {e}")
    else:
        log("ℹ️  CLOUD_URL/CLOUD_KEY not set — skipping cloud upload")

    return results


if __name__ == "__main__":
    run_fetch()
# end of file
