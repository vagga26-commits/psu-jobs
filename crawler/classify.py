"""Classify a notice into a government level (Central / State / PSU) and a department.

Rules run on the organisation name (and title for a few signals). Order matters:
the first matching department wins. Sources can pass a hint (e.g. a state page
says "State Govt") which is used when nothing else matches.
"""
import re

from orgs import resolve

LEVELS = ("Central Govt", "State Govt", "PSU")

DEPARTMENTS = [
    ("Banking & Finance", r"\bbank\b|\brbi\b|nabard|nabfins|sidbi|\bnhb\b|exim|apcob|hpscb|cooperative bank|bobcaps|iifcl|insurance|\blic\b|uiic|\bpfc\b|\brec\b|irfc"),
    ("UPSC, SSC & PSC", r"\bupsc\b|\bssc\b|\bpsc\b|appsc|cgpsc|gpsc|tgpsc|bpsc|\bsssb|gsssb|sssc|upsssc|\bbtsc\b|\bkea\b|vyapam|\bmpesb\b|\bessc\b|upessc|\bbpssc\b"),
    ("Judiciary & Legal", r"high court|district court|\bdlsa\b|legal services|\bcbi\b"),
    ("Railway", r"railway|\brrb\b|\brrc\b|metro|\bdmrc\b|\bcmrl\b|\bgmrc\b|mpmrcl|ncrtc|\bblw\b|\bkrcl\b|konkan|\brlda\b|irctc|rites|ircon"),
    ("Defence & Police", r"\barmy\b|\bnavy\b|naval|air force|coast guard|\bitbp|\bcrpf\b|\bbsf\b|\bcisf\b|\bssb\b|assam rifles|drdo|\bdiat\b|ordnance|\bgcf\b|police|prison|\bbpssc\b|\bdcpw\b|\bmpesb\b|casdic|dockyard|ship repair"),
    ("Medical & Health", r"aiims|aniims|pgimer|gmch|gmsh|hospital|\bcmho\b|\bdmho\b|\besic\b|\bechs\b|\bnhm\b|\bruhs\b|medical college|\bsdhm\b|bmhrc|hbchrc|\bpmbi\b"),
    ("Anganwadi & Social Welfare", r"anganwadi|icds|\bwcd\b|\bdcpu\b"),
    ("Municipal & Local Bodies", r"panchayat|municipal|city corporation|\bulb\b|local self|pourakarmika|\bbmc\b|dc office|district$|raichur district|koppal district"),
    ("Teaching & Research", r"univ|vishwavidyalaya|\biit\b|\bnit\b|iiit|\biim\b|iiser|\btiss\b|niper|icmr|\bicar\b|csir|isro|tifr|school|vidyalaya|kgbv|college|shiksha|\bessc\b|upessc|\bbseb\b|ignou|\bjmi\b|csjmu|ouat|tanuvas|angrau|mpkv|makaut|cusat|ncert|\biari\b|\bnii\b|rgniyd|svnirtar|svnit|\brari\b|gjust|skau|bknmu|kbcnmu|mpbou|cwssu|\bdbeo\b|\bitda\b|visva|c-dac|\bbsa\b|circot|ctil"),
]
DEPARTMENTS = [(name, re.compile(rx, re.I)) for name, rx in DEPARTMENTS]
TITLE_TEACH = re.compile(r"professor|teacher|lecturer|\bpgt\b|\btgt\b|\bprt\b|faculty|research fellow|\bjrf\b|\bsrf\b|research associate|\btet\b", re.I)
TITLE_POLICE = re.compile(r"police|constable|warder|jailor", re.I)
TITLE_MED = re.compile(r"medical officer|nurs|pharmacist|senior resident|doctor|specialist", re.I)

# State / UT bodies. Anything not matching is treated as a central body (or a PSU).
STATE_BODY = re.compile(
    r"\bpsc\b|appsc|cgpsc|gpsc|tgpsc|bpsc|\bsssb|gsssb|upsssc|upessc|vyapam|district|\bdlsa\b|\bdcpu\b|anganwadi|icds|"
    r"high court|panchayat|\bcmho\b|\bdmho\b|\bwcd\b|municipal|city corporation|\bulb\b|\bkea\b|\bbtsc\b|\bbseb\b|"
    r"bpssc|mpesb|gsrtc|ksrtc|samagra shiksha|govt medical college|prisons|local self government|kerala university|"
    r"kannur|cusat|mpkv|angrau|ouat|csjmu|kgbv|\bdbeo\b|\bitda\b|mpbou|tanuvas|\bgims\b|\bruhs\b|gmch|gmsh|lok nayak|"
    r"\bbmc\b|ut chandigarh|andaman and nicobar administration|aniims|skau|gjust|bknmu|gujarat university|kbcnmu|"
    r"makaut|\bsdhm\b|apcob|hpscb|pourakarmika|gadag|koppal|mysore|raichur|yadgir|arunachal|dlrs|kokrajhar|\brari\b|"
    r"namo hospital|central prison|kerala psc|\bbsa\b|\bcg\b|\bup\b|mp high court|madras|bpsc|cwssu", re.I)


def classify(org_raw, title="", hint=None):
    """Return (level, department, psu_sector_or_None)."""
    short, _full, sector, known = resolve(org_raw)
    text = f"{org_raw} {short}"
    if known:
        dept = "Banking & Finance" if sector in ("Banking & Insurance", "Finance") else "Public Sector Undertakings"
        level = "Central Govt" if short in ("RBI",) else "PSU"
        return level, dept, sector
    level = "State Govt" if STATE_BODY.search(text) else "Central Govt"
    for name, rx in DEPARTMENTS:
        if rx.search(text):
            return level, name, None
    if TITLE_POLICE.search(title):
        return level, "Defence & Police", None
    if TITLE_TEACH.search(title):
        return level, "Teaching & Research", None
    if TITLE_MED.search(title):
        return level, "Medical & Health", None
    if hint in dict(DEPARTMENTS) or hint in ("Railway", "Defence & Police", "Teaching & Research"):
        return level, hint, None
    return level, "Administration & Others", None
