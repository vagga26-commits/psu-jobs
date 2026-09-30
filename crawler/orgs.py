"""Canonical PSU registry: alias -> (short name, full name, sector).

Aggregators spell organisations many ways ("Bank of India", "BOI"); everything is
mapped to one short key here so dedup and filters work. Unknown orgs are kept
under their raw name with sector "Other PSU" unless a source sets
`only_known_orgs`.
"""
import re

# short: (full name, sector, [aliases])
REGISTRY = {
    # Energy – oil & gas
    "IOCL": ("Indian Oil Corporation Ltd", "Oil & Gas", ["indian oil", "iocl", "ioc"]),
    "ONGC": ("Oil and Natural Gas Corporation", "Oil & Gas", ["ongc"]),
    "GAIL": ("GAIL (India) Ltd", "Oil & Gas", ["gail"]),
    "BPCL": ("Bharat Petroleum Corporation Ltd", "Oil & Gas", ["bpcl", "bharat petroleum"]),
    "HPCL": ("Hindustan Petroleum Corporation Ltd", "Oil & Gas", ["hpcl", "hindustan petroleum"]),
    "Oil India": ("Oil India Ltd", "Oil & Gas", ["oil india", "oil"]),
    "CPCL": ("Chennai Petroleum Corporation Ltd", "Oil & Gas", ["cpcl", "chennai petroleum"]),
    "NRL": ("Numaligarh Refinery Ltd", "Oil & Gas", ["nrl", "numaligarh"]),
    "EIL": ("Engineers India Ltd", "Oil & Gas", ["eil", "engineers india"]),
    "BCPL": ("Brahmaputra Cracker and Polymer Ltd", "Oil & Gas", ["bcpl"]),
    "IRPL": ("IRPL", "Other PSU", ["irpl"]),
    # Power
    "NTPC": ("NTPC Ltd", "Power", ["ntpc"]),
    "POWERGRID": ("Power Grid Corporation of India", "Power", ["powergrid", "pgcil", "power grid"]),
    "GRID India": ("Grid Controller of India Ltd", "Power", ["grid india", "grid-india", "posoco"]),
    "NHPC": ("NHPC Ltd", "Power", ["nhpc"]),
    "NLC": ("NLC India Ltd", "Power", ["nlc", "nlc india", "neyveli"]),
    "PFC": ("Power Finance Corporation", "Finance", ["pfc", "power finance"]),
    "REC": ("REC Ltd", "Finance", ["rec", "rec ltd"]),
    "BHAVINI": ("Bharatiya Nabhikiya Vidyut Nigam Ltd", "Power", ["bhavini"]),
    "WAPCOS": ("WAPCOS Ltd", "Engineering & Consultancy", ["wapcos"]),
    # Coal, mining & steel
    "Coal India": ("Coal India Ltd", "Mining & Steel", ["coal india", "cil"]),
    "ECL": ("Eastern Coalfields Ltd", "Mining & Steel", ["eastern coalfields", "ecl"]),
    "NCL": ("Northern Coalfields Ltd", "Mining & Steel", ["ncl", "northern coalfields"]),
    "SAIL": ("Steel Authority of India Ltd", "Mining & Steel", ["sail", "sail iisco steel plant", "sail bhilai", "sail rourkela", "sail bokaro"]),
    "MOIL": ("MOIL Ltd", "Mining & Steel", ["moil"]),
    "MECL": ("Mineral Exploration & Consultancy Ltd", "Mining & Steel", ["mecl"]),
    "HCL": ("Hindustan Copper Ltd", "Mining & Steel", ["hcl", "hindustan copper"]),
    # Defence & heavy engineering
    "BEL": ("Bharat Electronics Ltd", "Defence & Engineering", ["bel", "bharat electronics"]),
    "HAL": ("Hindustan Aeronautics Ltd", "Defence & Engineering", ["hal", "hindustan aeronautics"]),
    "BHEL": ("Bharat Heavy Electricals Ltd", "Defence & Engineering", ["bhel"]),
    "BEML": ("BEML Ltd", "Defence & Engineering", ["beml"]),
    "Mazagon Dock": ("Mazagon Dock Shipbuilders Ltd", "Defence & Engineering", ["mazagon dock", "mdl", "mazagon"]),
    "CSL": ("Cochin Shipyard Ltd", "Defence & Engineering", ["csl", "cochin shipyard"]),
    "UCSL": ("Udupi Cochin Shipyard Ltd", "Defence & Engineering", ["ucsl"]),
    "GSL": ("Goa Shipyard Ltd", "Defence & Engineering", ["gsl", "goa shipyard"]),
    "Munitions India": ("Munitions India Ltd", "Defence & Engineering", ["munitions india", "mil"]),
    "AWEIL": ("Advanced Weapons & Equipment India Ltd", "Defence & Engineering", ["aweil"]),
    "India Optel": ("India Optel Ltd", "Defence & Engineering", ["india optel", "iol"]),
    "HMT": ("HMT Ltd", "Defence & Engineering", ["hmt"]),
    # Transport & infra
    "AAI": ("Airports Authority of India", "Transport & Infra", ["aai", "airports authority"]),
    "Alliance Air": ("Alliance Air Aviation Ltd", "Transport & Infra", ["alliance air aviation", "alliance air", "aaal"]),
    "RITES": ("RITES Ltd", "Transport & Infra", ["rites"]),
    "IRCON": ("IRCON International Ltd", "Transport & Infra", ["ircon"]),
    "IRCTC": ("Indian Railway Catering & Tourism Corp", "Transport & Infra", ["irctc"]),
    "IRFC": ("Indian Railway Finance Corporation", "Finance", ["irfc"]),
    "KRCL": ("Konkan Railway Corporation Ltd", "Transport & Infra", ["krcl", "konkan railway"]),
    "RLDA": ("Rail Land Development Authority", "Transport & Infra", ["rlda"]),
    "CONCOR": ("Container Corporation of India", "Transport & Infra", ["concor"]),
    "SCI": ("Shipping Corporation of India", "Transport & Infra", ["shipping corporation of india", "sci"]),
    "DCI": ("Dredging Corporation of India", "Transport & Infra", ["dredging corporation of india", "dci"]),
    "AIESL": ("AI Engineering Services Ltd", "Transport & Infra", ["aiesl"]),
    "Balmer Lawrie": ("Balmer Lawrie & Co Ltd", "Engineering & Consultancy", ["balmer lawrie"]),
    "AYCL": ("AYCL", "Other PSU", ["aycl"]),
    "HITES": ("HLL Infra Tech Services Ltd", "Transport & Infra", ["hites"]),
    # Telecom, IT, other
    "TCIL": ("Telecommunications Consultants India Ltd", "Telecom & IT", ["tcil"]),
    "BECIL": ("Broadcast Engineering Consultants India", "Telecom & IT", ["becil"]),
    "HLL": ("HLL Lifecare Ltd", "Health & Chemicals", ["hll", "hll lifecare"]),
    "RCFL": ("Rashtriya Chemicals & Fertilizers Ltd", "Health & Chemicals", ["rcfl", "rcf"]),
    "SPM": ("Security Paper Mill, Narmadapuram (SPMCIL)", "Other PSU", ["security paper mill narmadapuram", "spmcil"]),
    # Banks, insurance & financial institutions
    "SBI": ("State Bank of India", "Banking & Insurance", ["sbi", "state bank of india"]),
    "Bank of Baroda": ("Bank of Baroda", "Banking & Insurance", ["bank of baroda", "bob"]),
    "Bank of India": ("Bank of India", "Banking & Insurance", ["boi", "bank of india"]),
    "Canara Bank": ("Canara Bank", "Banking & Insurance", ["canara bank"]),
    "Central Bank": ("Central Bank of India", "Banking & Insurance", ["central bank of india"]),
    "IOB": ("Indian Overseas Bank", "Banking & Insurance", ["iob", "indian overseas bank"]),
    "PNB": ("Punjab National Bank", "Banking & Insurance", ["pnb", "punjab national bank"]),
    "Union Bank": ("Union Bank of India", "Banking & Insurance", ["union bank of india", "union bank"]),
    "Indian Bank": ("Indian Bank", "Banking & Insurance", ["indian bank"]),
    "Indbank": ("Indbank Merchant Banking Services", "Banking & Insurance", ["indbank"]),
    "UIIC": ("United India Insurance Co", "Banking & Insurance", ["uiic", "united india insurance"]),
    "LIC": ("Life Insurance Corporation of India", "Banking & Insurance", ["lic"]),
    "Exim Bank": ("Export-Import Bank of India", "Banking & Insurance", ["exim bank"]),
    "SIDBI": ("Small Industries Development Bank of India", "Banking & Insurance", ["sidbi"]),
    "NHB": ("National Housing Bank", "Banking & Insurance", ["nhb"]),
    "NABFINS": ("NABARD Financial Services", "Banking & Insurance", ["nabfins"]),
    "RBI": ("Reserve Bank of India", "Banking & Insurance", ["rbi", "rbi jammu"]),
}

_ALIAS = {}
for short, (_full, _sector, aliases) in REGISTRY.items():
    _ALIAS[short.lower()] = short
    for a in aliases:
        _ALIAS[a] = short

# Private / co-operative employers that aggregators mix into government listings
EXCLUDE = re.compile(
    r"\b(tmb|tamilnad mercantile|bassein|rnsb|abhyudaya|repco|jain university|bits pilani|cbit|davcmc|"
    r"jagat mata mahila|co-?operative credit)\b", re.I)


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9 &-]", "", s.lower()).strip()


def resolve(raw: str):
    """Return (short, full, sector, known) for a raw organisation string."""
    k = _key(raw)
    if k in _ALIAS:
        s = _ALIAS[k]
        full, sector, _ = REGISTRY[s]
        return s, full, sector, True
    # longest alias contained in the string ("SAIL Bhilai Steel Plant")
    hits = [a for a in _ALIAS if len(a) > 3 and re.search(rf"\b{re.escape(a)}\b", k)]
    if hits:
        s = _ALIAS[max(hits, key=len)]
        full, sector, _ = REGISTRY[s]
        return s, full, sector, True
    return raw.strip(), raw.strip(), "Other PSU", False
