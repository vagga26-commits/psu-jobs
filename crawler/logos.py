"""Organisation → website domain, used to show each employer's logo.

Only domains we are sure of are listed; anything else falls back to an initials
tile on the site. Family rules (AIIMS, DRDO, CSIR, railway zones…) point to the
parent body's site.
"""
import re

DOMAINS = {
    "AAI": "aai.aero", "AIESL": "aiesl.in", "Alliance Air": "allianceair.in", "AWEIL": "aweil.in",
    "BCPL": "bcplonline.co.in", "BEL": "bel-india.in", "BEML": "bemlindia.in", "BHAVINI": "bhavini.nic.in",
    "BHEL": "bhel.com", "BPCL": "bharatpetroleum.in", "Balmer Lawrie": "balmerlawrie.com",
    "Bank of Baroda": "bankofbaroda.in", "Bank of India": "bankofindia.co.in", "BOBCAPS": "bobcaps.in",
    "C-DAC": "cdac.in", "CBI": "cbi.gov.in", "CMRL": "chennaimetrorail.org", "CONCOR": "concorindia.co.in",
    "Coal India": "coalindia.in", "CPCL": "cpcl.co.in", "CPRI": "cpri.res.in", "CRPF": "crpf.gov.in",
    "CSL": "cochinshipyard.in", "UCSL": "cochinshipyard.in", "Canara Bank": "canarabank.com",
    "Central Bank": "centralbankofindia.co.in", "Central Silk Board": "csb.gov.in", "DCI": "dredge-india.com",
    "DIAT": "diat.ac.in", "DMRC": "delhimetrorail.com", "ECL": "easterncoal.nic.in", "EIL": "engineersindia.com",
    "ESIC": "esic.gov.in", "Exim Bank": "eximbankindia.in", "GAIL": "gailonline.com",
    "GMRC": "gujaratmetrorail.com", "GRID India": "grid-india.in", "GSL": "goashipyard.in", "GSRTC": "gsrtc.in",
    "HAL": "hal-india.co.in", "HCL": "hindustancopper.com", "HLL": "lifecarehll.com", "HMT": "hmtindia.com",
    "HPCL": "hindustanpetroleum.com", "ICMR": "icmr.gov.in", "IGNOU": "ignou.ac.in", "IIFCL Projects": "iifcl.in",
    "IIIT Delhi": "iiitd.ac.in", "IIM Kozhikode": "iimk.ac.in", "IIT ISM Dhanbad": "iitism.ac.in",
    "IIT Kanpur": "iitk.ac.in", "IIT Kharagpur": "iitkgp.ac.in", "IIT Tirupati": "iittp.ac.in", "IOB": "iob.in",
    "IOCL": "iocl.com", "IRCON": "ircon.org", "IRCTC": "irctc.co.in", "IRFC": "irfc.co.in",
    "ITBP": "itbpolice.nic.in", "Indbank": "indbankonline.com", "Indian Army": "joinindianarmy.nic.in",
    "Indian Coast Guard": "indiancoastguard.gov.in", "Indian Navy": "joinindiannavy.gov.in",
    "JMI": "jmi.ac.in", "Jawahar Navodaya Vidyalaya": "navodaya.gov.in", "KRCL": "konkanrailway.com",
    "KVIC": "kvic.gov.in", "Kerala PSC": "keralapsc.gov.in", "Kerala University": "keralauniversity.ac.in",
    "MECL": "mecl.co.in", "MOIL": "moil.nic.in", "MPMRCL": "mpmetrorail.com", "Madras High Court": "mhc.tn.gov.in",
    "Mazagon Dock": "mazagondock.in", "Munitions India": "munitionsindia.in", "NABFINS": "nabfins.org",
    "NCL": "nclcil.in", "NCRTC": "ncrtc.in", "NHB": "nhb.org.in", "NHPC": "nhpcindia.com", "NIC": "nic.in",
    "NIT Agartala": "nita.ac.in", "NLC": "nlcindia.in", "NRL": "nrl.co.in", "NTPC": "ntpc.co.in",
    "National Book Trust": "nbtindia.gov.in", "ONGC": "ongcindia.com", "Oil India": "oil-india.com",
    "PFC": "pfcindia.com", "PGIMER": "pgimer.edu.in", "PMBI": "janaushadhi.gov.in", "POWERGRID": "powergrid.in",
    "RBI": "rbi.org.in", "RCFL": "rcfltd.com", "REC": "recindia.nic.in", "RITES": "rites.com", "SAIL": "sail.co.in",
    "SBI": "sbi.co.in", "SCI": "shipindia.com", "SIDBI": "sidbi.in", "SPM": "spmcil.com", "SSC": "ssc.gov.in",
    "STPI": "stpi.in", "SVNIT Surat": "svnit.ac.in", "Sahitya Akademi": "sahitya-akademi.gov.in",
    "TIFR": "tifr.res.in", "TISS": "tiss.ac.in", "UIIC": "uiic.co.in", "UPSC": "upsc.gov.in",
    "UPSSSC": "upsssc.gov.in", "Visakhapatnam Port Authority": "vizagport.com", "Visva Bharati": "visvabharati.ac.in",
    "WAPCOS": "wapcos.co.in", "APPSC": "psc.ap.gov.in", "GPSC": "gpsc.gujarat.gov.in", "BPSC": "bpsc.bih.nic.in",
    "GSSSB": "gsssb.gujarat.gov.in", "CGPSC": "psc.cg.gov.in", "Gujarat High Court": "gujarathighcourt.nic.in",
    "HPSCB": "hpscb.com", "APCOB": "apcob.org", "CSJMU": "csjmu.ac.in", "CUSAT": "cusat.ac.in", "OUAT": "ouat.ac.in",
    "TANUVAS": "tanuvas.ac.in", "MPKV": "mpkv.ac.in", "MAKAUT": "makautwb.ac.in", "RUHS": "ruhsraj.org",
    "Allahabad University": "allduniv.ac.in", "ANGRAU": "angrau.ac.in", "Assam Rifles": "assamrifles.gov.in",
    "MPESB": "esb.mp.gov.in", "GMCH Chandigarh": "gmch.gov.in",
}

# (pattern on org name, domain) – checked in order when there is no exact entry
FAMILIES = [
    (r"^aiims\b", "aiims.edu"), (r"drdo", "drdo.gov.in"), (r"^csir\b", "csir.res.in"), (r"^isro\b", "isro.gov.in"),
    (r"^icar\b", "icar.org.in"), (r"^esic\b", "esic.gov.in"), (r"^echs\b", "echs.gov.in"),
    (r"railway|^rrb\b|^rrc\b|^blw\b", "indianrailways.gov.in"), (r"^naval\b", "indiannavy.nic.in"),
    (r"kendriya vidyalaya", "kvsangathan.nic.in"), (r"^dlsa\b", "nalsa.gov.in"),
    (r"income tax", "incometaxindia.gov.in"),
]
FAMILIES = [(re.compile(rx, re.I), d) for rx, d in FAMILIES]


def logo_domain(org):
    if org in DOMAINS:
        return DOMAINS[org]
    for rx, d in FAMILIES:
        if rx.search(org):
            return d
    return None
