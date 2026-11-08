#!/usr/bin/env python3
"""Veranstaltungsscanner Steiermark, täglicher Lauf.

Schritt 1:  python3 update.py fetch --prev PREV_DIR --work WORK
            Ruft die Quellen ab (robots.txt wird beachtet), übernimmt bekannte Termine
            aus dem letzten Lauf und legt neue Einträge zum Taggen ab:
            WORK/todo_mb.json (neue meinbezirk-Einträge) und WORK/todo_src/<quelle>.txt
            (geänderte Quellseiten).
Schritt 2:  KI taggt nach KATALOG.md und schreibt WORK/tags_mb.json und WORK/ext_<quelle>.json.
Schritt 3:  python3 update.py merge --work WORK --out OUT
            Prüft Belege, Orte, Dubletten und schreibt OUT/meta.json und OUT/parts/pN.json.
Nur Standardbibliothek und curl.
"""
import json, re, os, sys, time, subprocess, hashlib, html as H, unicodedata, argparse, glob
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
from urllib import robotparser

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Veranstaltungsscanner-Prototyp; Bewerbungsprojekt; ein Abruf pro Tag)"
GEM = json.load(open(os.path.join(HERE, 'gem.json')))
G = {g[0]: g for g in GEM['gem']}            # Name -> [name, id, bez, min, km, pop]
BEZ = {b[0]: b for b in GEM['bez']}
SLUG = {'graz': '601', 'graz-umgebung': '606', 'deutschlandsberg': '603', 'leibnitz': '610', 'voitsberg': '616',
        'hartberg-fuerstenfeld': '622', 'suedoststeiermark': '623', 'weiz': '617', 'bruck-an-der-mur': '621',
        'muerzzuschlag': '621', 'muerztal': '621', 'leoben': '611', 'liezen': '612', 'murau': '614', 'murtal': '620'}
SOURCES = {  # Schlüssel: (Name, URL)
    'tugraz': ('TU Graz', 'https://www.tugraz.at/news/tu-graz-events/monatsansicht'),
    'unigraz': ('Universität Graz', 'https://www.uni-graz.at/de/veranstaltungen/'),
    'greentech': ('Green Tech Valley Cluster', 'https://www.greentech.at/termine/'),
    'greentech2': ('Green Tech Valley Cluster', 'https://www.greentech.at/termine/page/2/'),
    'humantechnology': ('human.technology Styria', 'https://www.humantechnology.at/events/'),
    'humantechnology2': ('human.technology Styria', 'https://www.humantechnology.at/events/page/2/'),
    'wko': ('WKO Steiermark', 'https://www.wko.at/stmk/veranstaltungen/wirtschaft-und-branchen'),
    'kapfenberg': ('Stadt Kapfenberg', 'https://www.kapfenberg.gv.at/veranstaltungen'),
    'weiz': ('Stadtgemeinde Weiz', 'https://www.weiz.at/veranstaltungen'),
    'leoben': ('Stadt Leoben', 'https://www.leoben.at/events/'),
    'liezen': ('Stadtgemeinde Liezen', 'https://www.liezen.at/veranstaltungen'),
}
MK = 'Steirischer Marktkalender (WKO)'
MK_URL = 'https://www.wko.at/stmk/handel/markt-strassen-wanderhandel/steirischer-marktkalender-2026'
TOP = ['bildung', 'entlastung', 'gesundheit', 'politik', 'inklusion', 'energie', 'regionen', 'innovation', 'kultur']
FMT = ['Fachveranstaltung', 'Vortrag', 'Podium', 'Info-Abend', 'Fest', 'Markt', 'Messe', 'Sport', 'Konzert', 'Theater',
       'Ausstellung', 'Kurs', 'Empfang', 'Offene Tür', 'Gedenken', 'Sonstiges']
ZG = ['jugend', 'familien', 'senioren', 'unternehmen', 'fach', 'allgemein']
W8 = {'landesweit': 'land', 'regional': 'region', 'lokal': 'lokal'}
KW = {'bildung': r'schul|kindergart|krippe|bildung|lehrling|lehre\b|eltern|ausbildung|studi|hochschul|universit',
      'gesundheit': r'gesund|pflege|ärzt|arzt|medizin|psych|krebs|demenz|spital|klinik|vorsorge',
      'entlastung': r'wirtschaft|unternehm|betrieb|steuer|bürokrat|handel|gewerbe|arbeit|fachkr|gründ',
      'politik': r'demokrat|politik|wahl|transparenz|gemeinderat|bürgermeister|europa|eu-|recht|landtag',
      'inklusion': r'inklusion|barriere|behinder|integration|armut|sozial|caritas|lebenshilfe|senior',
      'energie': r'energie|klima|umwelt|natur|photovolt|solar|wärme|geotherm|mobilität|nachhaltig|wald|landwirt|bio',
      'regionen': r'feuerwehr|gemeinde|verein|ehrenamt|dorf|ort|kirtag|bürger|jubiläum|einweihung|eröffnung',
      'innovation': r'digital|ki\b|künstliche|innovation|forschung|technik|technolog|start-?up|wissenschaft|labor',
      'kultur': r'konzert|musik|theater|kabarett|lesung|ausstellung|kunst|kultur|fest|ball|sport|lauf|turnier|tanz|chor|kino|brauchtum|markt'}
ONL = r'\bonline\b|webinar|livestream|live-stream|zoom|ms teams|microsoft teams|hybrid|virtuell|stream'
BOIL = re.compile(r'peiq\.de|meinmed\.at/?$|meinmed\.at/newsletter|pexels\.com|pixabay\.com|unsplash\.com|folkart\.at/?$|facebook\.com/sharer|twitter\.com/intent|whatsapp|mailto:')
REGRE = re.compile(r'anmeld|ticket|regist|eventbrite|reservier|fairticket|forms\.cloud\.microsoft|forms\.office|buchen\.', re.I)
ONLRE = re.compile(r'zoom\.us|teams\.microsoft|teams\.live|webex|meet\.google|youtube\.com/live|vimeo\.com/event', re.I)
NONSTMK = re.compile(r'innsbruck|tirol|wien|kärnten|klagenfurt|lakeside|techendorf|weissensee|kötschach|hamburg|köln|deutschland|düsseldorf|münchen|berlin|linz|salzburg|lungau|tamsweg|burgenland|stegersbach', re.I)
OUTKNOWN = {'MEDICA': 'Messe Düsseldorf'}
KORR = {'Medical Science Talks 2026': ('Graz', 'laut humantechnology.at: Graz, 13. und 14.10.2026'),
        'Bits and Bytes - das Krankenhaus der Zukunft': ('Graz', 'laut humantechnology.at: Campus Med Uni Graz, 16. und 17.11.2026')}
FB = {'Fest': 'regionen', 'Markt': 'regionen', 'Messe': 'entlastung', 'Konzert': 'kultur', 'Theater': 'kultur', 'Ausstellung': 'kultur',
      'Sport': 'kultur', 'Kurs': 'bildung', 'Vortrag': 'bildung', 'Gedenken': 'politik', 'Empfang': 'entlastung', 'Offene Tür': 'bildung',
      'Podium': 'politik', 'Info-Abend': 'regionen', 'Fachveranstaltung': 'entlastung', 'Sonstiges': 'regionen'}
ENERGIE_OK = r'energie|strom|wärme|klima|photovolt|solar|wasserstoff|mobilität|umwelt|nachhaltig|kreislauf|sanier|heiz|fernwärme|energy|cetp|cycl|radverkehr|fahrrad|verkehr|natur|wald|grad-ziel|co2|erderwärm|bioökonom|bioeconom|repair|reparatur|bahn|zukunftsfähig'
POLITIK_OK = r'politik|demokrat|transparenz|wahl|bürger|gemeinde|landtag|europa|\beu\b|recht|korruption|kontrolle|beteiligung|versammlung|sicherheit|polizei|cops|parlament|gesellschaft|frieden|gedenk|menschenrecht'
MK_ALIAS = {'eggersdorf': 'Eggersdorf bei Graz', 'sanktveitamvogau': 'Sankt Veit in der Südsteiermark', 'irdningdonnersbachwald': 'Irdning-Donnersbachtal',
            'neumarkt': 'Neumarkt in der Steiermark', 'sanktmichael': 'Sankt Michael in Obersteiermark', 'sanktpeterfreienstein': 'Sankt Peter-Freienstein',
            'sanktlorenzenimmurztal': 'Sankt Lorenzen im Mürztal', 'pollau': 'Pöllau', 'sanktgallen': 'Sankt Gallen', 'veitsch': 'Sankt Barbara im Mürztal', 'wolfsbergimschwarzautal': 'Schwarzautal'}
MON = {'Jänner': 1, 'Januar': 1, 'Februar': 2, 'März': 3, 'April': 4, 'Mai': 5, 'Juni': 6, 'Juli': 7, 'August': 8, 'September': 9,
       'Oktober': 10, 'November': 11, 'Dezember': 12}

def vienna_now():
    now = datetime.now(timezone.utc)
    y = now.year
    def last_sun(m):
        d = (date(y, m + 1, 1) - timedelta(days=1)) if m < 12 else date(y, 12, 31)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    a = datetime(*last_sun(3).timetuple()[:3], 1, tzinfo=timezone.utc)
    b = datetime(*last_sun(10).timetuple()[:3], 1, tzinfo=timezone.utc)
    return now + timedelta(hours=2 if a <= now < b else 1)

def vienna_today(): return vienna_now().date()

def norm(s):
    s = (s or '').lower().replace('st.', 'sankt ').replace('–', '-').replace('—', '-')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z]', '', s)
NG = {norm(n): n for n in G}

def resolve(loc, code=None):
    if not loc: return None, 'none'
    k = norm(re.sub(r'\(.*?\)', '', loc))
    if k in NG and (code is None or G[NG[k]][2] == code): return NG[k], 'name'
    for nk, n in NG.items():
        if len(k) >= 5 and (nk.startswith(k) or k.startswith(nk)) and (code is None or G[n][2] == code): return n, 'prefix'
    return None, 'none'

def rtags(t):
    t = (t or '').lower(); return [k for k, v in KW.items() if re.search(v, t)]

def popf(gem):
    p = G[gem][5] if gem in G else 0
    return 2000 if p >= 10000 else 1200 if p >= 5000 else 600 if p >= 2000 else 300

def reach_est(fmt, w):
    base = {'Fest': 600, 'Markt': 800, 'Messe': 2000, 'Sport': 300, 'Konzert': 250, 'Theater': 150, 'Ausstellung': 120, 'Podium': 120,
            'Fachveranstaltung': 100, 'Vortrag': 60, 'Info-Abend': 80, 'Kurs': 20, 'Empfang': 150, 'Offene Tür': 500, 'Gedenken': 100, 'Sonstiges': 60}.get(fmt, 60)
    return int(base * {'land': 3, 'region': 1.6, 'lokal': 1}[w])

def stand(fmt, zg, src):
    if 'jugend' in zg or src in ('tugraz', 'unigraz'): return 'unueblich'
    return 'anfragen' if fmt in ('Markt', 'Fest', 'Messe') else 'unueblich'

def chk(x, vals, default): return x if x in vals else default
def sid(*parts): return hashlib.sha1('|'.join(parts).encode()).hexdigest()[:8]

# ---------------------------------------------------------------- Abruf
_robots = {}
_last = {}
def allowed(url):
    host = urlparse(url).scheme + '://' + urlparse(url).netloc
    if host not in _robots:
        rp = robotparser.RobotFileParser()
        txt = subprocess.run(['curl', '-sS', '-L', '-m', '20', '-A', UA, host + '/robots.txt'], capture_output=True, text=True).stdout
        rp.parse(txt.splitlines() if txt and '<html' not in txt[:200].lower() else [])
        _robots[host] = rp
    rp = _robots[host]
    return rp.can_fetch(UA, url), (rp.crawl_delay(UA) or 0)

def get(url, delay=1.3):
    ok, cd = allowed(url)
    if not ok: return None, 'robots.txt verbietet'
    host = urlparse(url).netloc
    wait = max(delay, cd) - (time.time() - _last.get(host, 0))
    if wait > 0: time.sleep(wait)
    r = subprocess.run(['curl', '-sS', '-L', '-m', '30', '-A', UA, url], capture_output=True, text=True)
    _last[host] = time.time()
    if r.returncode != 0: return None, 'Abruf fehlgeschlagen: ' + (r.stderr.strip()[:80] or str(r.returncode))
    return r.stdout, None

def clean(s): return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()

def totext(h, base):
    h = re.sub(r'<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    def a(m):
        href = H.unescape(m.group(1)); inner = re.sub(r'<[^>]+>', ' ', m.group(2)); inner = re.sub(r'\s+', ' ', H.unescape(inner)).strip()
        if len(inner) < 4 or href.startswith(('#', 'javascript', 'mailto', 'tel')): return ' ' + inner + ' '
        return ' ' + inner + ' [LINK ' + urljoin(base, href) + '] '
    h = re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', a, h, flags=re.S | re.I)
    h = re.sub(r'<br\s*/?>', '\n', h, flags=re.I)
    h = re.sub(r'</?(p|div|li|ul|ol|h[1-6]|tr|article|section|dd|dt|dl|table|time)\b[^>]*>', '\n', h, flags=re.I)
    t = H.unescape(re.sub(r'<[^>]+>', ' ', h))
    t = re.sub(r'[ \t ]+', ' ', t); t = re.sub(r'\n\s*\n+', '\n', t)
    return t.strip()

def pdate(t):
    m = re.search(r'(\d{1,2})\.\s*([A-Za-zäÄ]+)\s+(\d{4})(?:\s*um\s*(\d{1,2}):(\d{2}))?', t)
    if not m or m.group(2) not in MON: return None, None
    return f"{m.group(3)}-{MON[m.group(2)]:02d}-{int(m.group(1)):02d}", (f"{int(m.group(4)):02d}:{m.group(5)}" if m.group(4) else None)

MONL = {'jänner': 1, 'januar': 1, 'februar': 2, 'märz': 3, 'april': 4, 'mai': 5, 'juni': 6, 'juli': 7, 'august': 8, 'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12}
REC = r'jeweils|jeden|jede[rn]?\b|wöchentlich|monatlich|regelmäßig|weiteren termin|termine|saison|reihe|immer\s+(?:am|mon|die|mitt|don|frei|sams|sonn)'
def datecheck(text, d):
    """Hinweis, wenn der Text ein anderes Datum nennt als die Liste. Vorsichtig: Serientermine und Fristen lösen nichts aus."""
    t = (text or '')[:600]
    y, m0, d0 = map(int, d.split('-'))
    mname = '|'.join(k for k, v in MONL.items() if v == m0)
    if re.search(r'(?<!\d)0?' + str(d0) + r'\.(?:[\s,]*(?:und|bis|-|–|&)?[\s,]*\d{1,2}\.)*\s*(?:' + mname + r')\b', t, re.I): return None
    if re.search(r'(?<!\d)0?' + str(d0) + r'\.\s*0?' + str(m0) + r'\.', t): return None
    first = None
    for m in re.finditer(r'(?<!\d)(\d{1,2})\.\s*(' + '|'.join(MONL) + r')\b', t, re.I):
        pre = t[max(0, m.start() - 25):m.start()].lower()
        if re.search(r'bis|frist|anmeld|seit', pre): continue
        first = (int(m.group(1)), MONL[m.group(2).lower()], m.group(2).capitalize()); break
    if not first: return None
    dd, mm, nm = first
    msg = f'Text nennt {dd}. {nm}, Liste {d0}.{m0}.: Datum bitte prüfen'
    if dd == d0 and mm != m0: return msg
    if re.search(REC, t, re.I): return None
    later = (mm - m0) % 12 if mm != m0 else 0
    if (mm != m0 and 0 < later <= 3) or (mm == m0 and dd > d0): return msg
    return None

def load_prev(prev_dir):
    meta, events = {}, []
    if not prev_dir or not os.path.isdir(prev_dir): return meta, events
    for f in glob.glob(os.path.join(prev_dir, '**', '*.json'), recursive=True):
        try: j = json.load(open(f))
        except Exception: continue
        body = j.get('data', j) if isinstance(j, dict) else {}
        if isinstance(body, dict) and 'events' in body: events += body['events']
        elif isinstance(body, dict) and 'runId' in body: meta = body
    return meta, events

def cmd_fetch(a):
    today = vienna_today(); START = today.isoformat(); END = (today + timedelta(days=48)).isoformat()
    os.makedirs(a.work, exist_ok=True); os.makedirs(os.path.join(a.work, 'todo_src'), exist_ok=True)
    meta, prev = load_prev(a.prev)
    P = {e['id']: e for e in prev}
    flog = {'start': START, 'end': END, 'quellen': {}, 'fehler': []}
    # meinbezirk: Listen
    items, ok_dist = {}, set()
    for dist in SLUG:
        page = 1
        while page <= 40:
            url = f"https://www.meinbezirk.at/event/{dist}/list" if page == 1 else f"https://www.meinbezirk.at/event/{dist}/list/all/{page}"
            h, err = get(url)
            if err: flog['fehler'].append((url, err)); break
            arts = re.findall(r'<article class="content-list-item[^"]*" data-eventitem-id="(\d+)">(.*?)</article>', h, re.S)
            if not arts: break
            if page == 1: ok_dist.add(dist)
            firstd, new = None, 0
            for eid, art in arts:
                link = re.search(r'href="(/event/[^"]+_e' + eid + r')"', art)
                lis = [clean(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', re.search(r'content-card-date-location">(.*?)</ul>', art, re.S).group(1), re.S)] if 'content-card-date-location' in art else []
                title = clean(re.search(r'content-card-headline[^>]*>(.*?)</h3>', art, re.S).group(1)) if 'content-card-headline' in art else ''
                txt = clean(re.search(r'content-card-text">(.*?)</div>', art, re.S).group(1)) if 'content-card-text' in art else ''
                d, tm = pdate(lis[0]) if lis else (None, None)
                if d and firstd is None: firstd = d
                cat = re.search(r'/c-([a-z\-]+)/', link.group(1)).group(1) if link and '/c-' in link.group(1) else ''
                if 'mb' + eid not in items:
                    new += 1
                    items['mb' + eid] = {'id': 'mb' + eid, 'dist': dist, 'url': 'https://www.meinbezirk.at' + link.group(1) if link else None,
                                         'd': d, 's': tm, 'place': lis[1:], 'title': title, 'text': txt, 'cat': cat}
            if (firstd and firstd > END) or new == 0: break
            page += 1
    win = {k: v for k, v in items.items() if v['d'] and START <= v['d'] <= END}
    flog['quellen']['meinbezirk.at'] = {'roh': len(items), 'im_fenster': len(win)}
    keep, todo = [], []
    for k, it in win.items():
        if k in P:
            e = dict(P[k]); e['fl'] = dict(e.get('fl') or {})
            if e['d'] != it['d']:
                e['fl']['changed'] = 'Termin verschoben, vorher ' + e['d'][8:10] + '.' + e['d'][5:7] + '.'
                e['d'] = it['d']; e['s'] = it['s'] or e.get('s')
            keep.append(e)
        else:
            dd = {}
            if it['url']:
                h, err = get(it['url'], delay=3)
                if h:
                    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S):
                        try:
                            j = json.loads(m.group(1))
                            if isinstance(j, dict) and j.get('@type') == 'Event': dd['ld'] = j; break
                        except Exception: pass
                    dd['links'] = sorted(set(H.unescape(u) for u in re.findall(r'href="(https?://[^"]+)"', h) if not re.search(r'meinbezirk|regionalmedien|facebook\.com/sharer|twitter|whatsapp|google|apple|didomi|gstatic|iocnt|pinterest|linkedin\.com/share|mailto', u)))[:12]
            todo.append({'id': k, 'datum': it['d'], 'beginn': it['s'], 'bezirk_meinbezirk': it['dist'], 'ort_angaben': it['place'], 'kategorie': it['cat'],
                         'titel': it['title'], 'text': it['text'][:900], '_url': it['url'], '_detail': dd})
    # Termine verschwundener Bezirkslisten behalten (Abruf gescheitert)
    for e in prev:
        if e['id'].startswith('mb') and e['id'] not in win and START <= e['d'] <= END:
            dist_ok = any(SLUG[d] == (e.get('bz') or '') for d in ok_dist)
            if not dist_ok: keep.append(e)
    # weitere Quellen
    hashes = {}
    for key, (name, url) in SOURCES.items():
        urls = [url]
        h, err = get(url)
        if err or not h: flog['fehler'].append((url, err or 'leer')); continue
        texts = [totext(h, url)]
        if key == 'tugraz':  # Folgemonate über die Links der Seite
            months = set()
            dd = today
            while dd.isoformat() <= END: months.add((dd.year, dd.month)); dd = (dd.replace(day=1) + timedelta(days=32)).replace(day=1)
            for m in re.finditer(r'monatsansicht\?tx_news_pi1%5BoverwriteDemand%5D%5Bmonth%5D=(\d+)&amp;tx_news_pi1%5BoverwriteDemand%5D%5Byear%5D=(\d+)&amp;cHash=(\w+)', h):
                if (int(m.group(2)), int(m.group(1))) in months and (int(m.group(2)), int(m.group(1))) != (today.year, today.month):
                    u2 = urljoin(url, H.unescape(m.group(0)))
                    h2, e2 = get(u2)
                    if h2: texts.append(totext(h2, u2)); urls.append(u2)
        txt = '\n\n'.join(texts)
        hsh = hashlib.sha1(txt.encode()).hexdigest()
        hashes[key] = hsh
        old = (meta.get('hashes') or {}).get(key)
        if old == hsh:
            for e in prev:
                if e.get('_srckey') == key and START <= e['d'] <= END: keep.append(e)
        else:
            open(os.path.join(a.work, 'todo_src', key + '.txt'), 'w').write(f"QUELLE: {name}\nURL: {' | '.join(urls)}\nHEUTE: {START}, FENSTER bis {END}\n\n" + txt[:60000])
    json.dump(todo, open(os.path.join(a.work, 'todo_mb.json'), 'w'), ensure_ascii=False, indent=0)
    json.dump({'start': START, 'end': END, 'keep': keep, 'hashes': hashes, 'log': flog, 'prevRun': meta.get('runId')}, open(os.path.join(a.work, 'state.json'), 'w'), ensure_ascii=False)
    print(json.dumps({'fenster': [START, END], 'meinbezirk_im_fenster': len(win), 'uebernommen': len(keep), 'neu_zu_taggen': len(todo),
                      'quellseiten_neu_zu_lesen': sorted(os.path.basename(f)[:-4] for f in glob.glob(os.path.join(a.work, 'todo_src', '*.txt'))),
                      'fehler': flog['fehler']}, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- Zusammenführen
def mk_sum(pl, n):
    tage = {2: 'an zwei aufeinanderfolgenden Tagen', 3: 'an drei aufeinanderfolgenden Tagen'}.get(n, 'an mehreren Tagen') if n > 1 else ''
    return (f'Jahr- oder Krämermarkt in {pl}' + (' ' + tage if tage else '') + ', eingetragen im Steirischen Marktkalender 2026 der Wirtschaftskammer. '
            'Uhrzeit und Standplatz nennt der Kalender nicht; die Gemeinde gibt Auskunft.')

def cmd_merge(a):
    S = json.load(open(os.path.join(a.work, 'state.json')))
    START, END = S['start'], S['end']
    todo = {x['id']: x for x in json.load(open(os.path.join(a.work, 'todo_mb.json')))}
    tagp = os.path.join(a.work, 'tags_mb.json')
    tags = {x['id']: x for x in (json.load(open(tagp)) if os.path.exists(tagp) else [])}
    LOG = {'quellen': {}, 'verworfen': [], 'korrekturen': [], 'fehler': S['log']['fehler']}
    def add(src, k, n=1):
        LOG['quellen'].setdefault(src, {'roh': 0, 'im_fenster': 0, 'aufgenommen': 0}); LOG['quellen'][src][k] += n
    EV = []
    mbq = S['log']['quellen'].get('meinbezirk.at', {'roh': 0, 'im_fenster': 0})
    add('meinbezirk.at', 'roh', mbq['roh']); add('meinbezirk.at', 'im_fenster', mbq['im_fenster'])
    for e in S['keep']:
        EV.append(e)
        n = e['src'][0]['n'] if e.get('src') else '?'
        if n == 'meinbezirk.at': add(n, 'aufgenommen')
        elif n != MK: add(n, 'roh'); add(n, 'im_fenster'); add(n, 'aufgenommen')
    missing = [k for k in todo if k not in tags]
    if missing: print('WARNUNG: ohne Tags', len(missing), missing[:5])
    for k, it in todo.items():
        t = tags.get(k)
        if not t: LOG['verworfen'].append((it['titel'], 'kein Tag')); continue
        code = SLUG[it['bezirk_meinbezirk']]
        gem = t.get('gemeinde') if t.get('gemeinde') in G else None
        how = 'ki' if gem else 'none'
        ld = (it.get('_detail') or {}).get('ld') or {}
        loc = None
        if isinstance(ld.get('location'), list) and ld['location']:
            loc = (ld['location'][0].get('address') or {}).get('addressLocality')
        fl = {}
        d, s, e_ = it['datum'], it['beginn'], t.get('ende')
        if ld.get('startDate'):
            ldd = ld['startDate'][:10]
            if ldd > d: fl['datum'] = 'Detailseite nennt ' + ldd + ', bitte prüfen'
            if ld.get('endDate') and ld['endDate'][:10] == ldd == d and not e_ and len(ld['endDate']) > 15: e_ = ld['endDate'][11:16]
        dc = datecheck(it['text'], d)
        if dc and not fl.get('datum'): fl['datum'] = dc
        if not gem:
            gem, how = resolve(loc or (it['ort_angaben'][-1] if it['ort_angaben'] else None), code)
        if gem and G[gem][2] != code and how != 'ki': gem, how = None, 'none'
        txt = (it['titel'] + ' ' + it['text']).lower()
        if re.search(r'tamsweg|lungau|stegersbach|burgenland|salzburger land|kärnten|\bkroatien\b|\bslowenien\b|\bitalien\b|\bungarn\b|hafen von split', txt + ' ' + (t.get('ort') or '').lower() + ' ' + ' '.join(it['ort_angaben']).lower()) and not gem:
            LOG['verworfen'].append((it['titel'], 'außerhalb der Steiermark')); continue
        if not gem:
            nt = ' ' + re.sub(r'[^a-zäöüß]+', ' ', it['titel'].lower().replace('st.', 'sankt ')) + ' '
            hits = [n for n in G if ' ' + re.sub(r'[^a-zäöüß]+', ' ', n.lower()) + ' ' in nt and G[n][2] == code]
            if hits: gem = max(hits, key=len); how = 'titel'
        modus = chk(t.get('modus'), ('praesenz', 'hybrid', 'online'), 'praesenz')
        if re.search(ONL, txt) and modus == 'praesenz': fl['online'] = 'Text erwähnt Online-Teilnahme, prüfen'
        links = [u for u in (it.get('_detail') or {}).get('links', []) if not BOIL.search(u)]
        ol = t.get('online_link') or next((u for u in links if ONLRE.search(u)), None)
        reg = next((u for u in links if REGRE.search(u)), None)
        if reg and 'oeticket.com/?affiliate' in reg: reg = None
        info = next((u for u in links if u != reg and u != ol and not re.search(r'youtube\.com/watch', u)), None)
        if ol and modus == 'praesenz': modus = 'hybrid'
        themen = [x for x in (t.get('themen') or []) if x in TOP]
        rt = rtags(it['titel'] + ' ' + it['text'])
        if not themen: themen = rt[:2]; fl['tags'] = 'Themen per Regel ergänzt'
        fmt = chk(t.get('format'), FMT, 'Sonstiges'); w = W8.get(t.get('gewicht'), 'lokal'); rel = chk(t.get('relevanz'), ('hoch', 'mittel', 'niedrig'), 'niedrig')
        zg = [z for z in (t.get('zielgruppe') or []) if z in ZG] or ['allgemein']
        if not gem: fl['ort'] = 'Gemeinde nicht eindeutig'
        EV.append({'id': k, 'd': d, 's': s, 'e': e_, 'd2': None, 'gem': gem, 'bz': (G[gem][2] if gem else code), 'gemHow': how,
                   'venue': t.get('ort') or (it['ort_angaben'][0] if it['ort_angaben'] else ''), 'org': t.get('veranstalter') or '', 'title': it['titel'],
                   'sum': t.get('kurz') or '', 'format': fmt, 'topics': themen, 'zg': zg, 'w': w, 'rel': rel, 'modus': modus, 'online': ol, 'anm': t.get('anmeldung'),
                   'reg': reg, 'reach': reach_est(fmt, w), 'stand': stand(fmt, zg, 'mb'), 'src': [{'n': 'meinbezirk.at', 'u': it['_url']}] + ([{'n': 'Veranstalter-Seite', 'u': info}] if info else []),
                   'fl': fl, 'ruleTopics': rt})
        add('meinbezirk.at', 'aufgenommen')
    # extrahierte Quellen
    for f in sorted(glob.glob(os.path.join(a.work, 'ext_*.json'))):
        key = os.path.basename(f)[4:-5]
        if key not in SOURCES: continue
        name = SOURCES[key][0]
        tf = os.path.join(a.work, 'todo_src', key + '.txt')
        TXT = re.sub(r'\s+', ' ', open(tf).read()) if os.path.exists(tf) else ''
        for x in json.load(open(f)):
            add(name, 'roh')
            d = x.get('datum') or ''
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', d) or not (START <= d <= END): continue
            add(name, 'im_fenster')
            b = re.sub(r'\s+', ' ', x.get('beleg') or '').strip()
            if not b or b not in TXT: LOG['verworfen'].append((x.get('titel', '?'), 'Beleg nicht im Quelltext')); continue
            gem = x.get('gemeinde') if x.get('gemeinde') in G else None
            fl = {}; ven = x.get('ort') or ''
            first = (x.get('titel') or '').split()[0] if x.get('titel') else ''
            if not gem and (NONSTMK.search(ven) or first in OUTKNOWN):
                LOG['verworfen'].append((x['titel'], 'außerhalb der Steiermark (' + (ven or OUTKNOWN.get(first, ''))[:40] + ')')); continue
            if not gem and x.get('titel') in KORR:
                gem = KORR[x['titel']][0]; LOG['korrekturen'].append((x['titel'], gem, KORR[x['titel']][1]))
            if not gem:
                i = TXT.find((x.get('titel') or '')[:30])
                m = re.search(r'\bin ([A-ZÄÖÜ][\wäöüß\-]+(?: [A-ZÄÖÜ][\wäöüß\-]+)?) statt', TXT[i:i + 300]) if i >= 0 else None
                if m:
                    g2, _ = resolve(m.group(1))
                    if g2: gem = g2; LOG['korrekturen'].append((x['titel'], gem, 'Ort aus dem Quelltext: „in ' + m.group(1) + ' statt“'))
            modus = chk(x.get('modus'), ('praesenz', 'hybrid', 'online'), 'praesenz')
            if not gem and modus == 'praesenz': fl['ort'] = 'Ort in der Quelle nicht genannt'
            fmt = chk(x.get('format'), FMT, 'Sonstiges'); w = W8.get(x.get('gewicht'), 'region'); rel = chk(x.get('relevanz'), ('hoch', 'mittel', 'niedrig'), 'niedrig')
            themen = [t for t in (x.get('themen') or []) if t in TOP] or rtags(x['titel'] + ' ' + (x.get('kurz') or ''))[:2]
            zg = [z for z in (x.get('zielgruppe') or []) if z in ZG] or ['allgemein']
            anm = x.get('anmeldung')
            EV.append({'id': 'x' + sid(key, x['titel'], d), 'd': d, 's': x.get('beginn'), 'e': x.get('ende'), 'd2': x.get('bis_datum'), 'gem': gem, 'bz': (G[gem][2] if gem else None),
                       'gemHow': 'ki' if gem else 'none', 'venue': ven, 'org': x.get('veranstalter') or name, 'title': x['titel'], 'sum': x.get('kurz') or '', 'format': fmt,
                       'topics': themen, 'zg': zg, 'w': w, 'rel': rel, 'modus': modus, 'online': x.get('online_link'), 'anm': anm,
                       'reg': anm if (anm or '').startswith('http') else None, 'reach': reach_est(fmt, w), 'stand': stand(fmt, zg, key),
                       'src': [{'n': name, 'u': x.get('url')}], 'fl': fl, 'ruleTopics': rtags(x['titel'] + ' ' + (x.get('kurz') or '')), '_srckey': key})
            add(name, 'aufgenommen')
    # Marktkalender (Jahresausgabe, statisch)
    mk = sorted(json.load(open(os.path.join(HERE, 'markt_2026.json'))), key=lambda m: (m['place'], m['d']))
    grp = []
    for m in mk:
        if grp and grp[-1]['place'] == m['place'] and (date.fromisoformat(m['d']) - date.fromisoformat(grp[-1]['d2'])).days == 1:
            grp[-1]['d2'] = m['d']; grp[-1]['n'] += 1; continue
        grp.append({'d': m['d'], 'd2': m['d'], 'place': m['place'], 'n': 1})
    for m in grp:
        add(MK, 'roh', m['n'])
        if not (START <= m['d2'] and m['d'] <= END): continue
        add(MK, 'im_fenster', m['n'])
        pl = m['place']; gem, how = resolve(pl)
        if not gem:
            gem = MK_ALIAS.get(norm(re.sub(r'\(.*?\)', '', pl)))
            if gem not in G: gem = None
        fl = {'zeit': 'Uhrzeit laut Marktkalender nicht angegeben'}
        if not gem: fl['ort'] = 'Gemeinde nicht eindeutig'
        EV.append({'id': 'm' + sid(pl, m['d']), 'd': max(m['d'], START), 's': None, 'e': None, 'd2': (m['d2'] if m['d2'] != m['d'] else None), 'gem': gem, 'bz': G[gem][2] if gem else None,
                   'gemHow': how, 'venue': pl, 'org': 'laut Steirischem Marktkalender', 'title': ('Markttage in ' if m['n'] > 1 else 'Markttag in ') + pl,
                   'sum': mk_sum(pl, m['n']), 'format': 'Markt', 'topics': ['regionen', 'entlastung'], 'zg': ['allgemein'],
                   'w': 'lokal', 'rel': 'mittel', 'modus': 'praesenz', 'online': None, 'anm': None, 'reg': None, 'reach': (popf(gem) if gem else 300), 'stand': 'anfragen',
                   'src': [{'n': MK, 'u': MK_URL}], 'fl': fl, 'ruleTopics': ['regionen']})
        add(MK, 'aufgenommen', m['n'])
    # Dubletten
    def toks(s): return set(w for w in re.findall(r'[a-zäöüß]{4,}', (s or '').lower()) if w not in ('markt', 'herbst', 'oktober', 'november', 'steiermark', 'graz'))
    keepl, merged = [], 0
    for ev in sorted(EV, key=lambda e: (e['d'], e['gem'] or '', e['title'])):
        dup = None
        for k2 in keepl:
            if k2['id'] == ev['id']: dup = k2; break
            near = False
            if k2['d'] != ev['d'] and (not k2['gem'] or not ev['gem'] or k2['gem'] == ev['gem']):
                near = abs((date.fromisoformat(k2['d']) - date.fromisoformat(ev['d'])).days) <= 1 and len([w for w in (toks(k2['title']) & toks(ev['title'])) if len(w) >= 6]) >= 3
            if (k2['d'] == ev['d'] or near) and ((k2['gem'] and k2['gem'] == ev['gem']) or (not k2['gem'] or not ev['gem'])):
                A, Bt = toks(k2['title']), toks(ev['title'])
                j = len(A & Bt) / max(1, len(A | Bt)); lt = len([w for w in (A & Bt) if len(w) >= 6])
                if not (k2['gem'] and ev['gem']) and j < 0.5 and lt < 2: continue
                if lt >= 2: j = max(j, 0.5)
                mk2 = (k2['format'] == 'Markt' and ev['format'] == 'Markt' and ('Markttag' in k2['title'] or 'Markttag' in ev['title']))
                if j >= 0.5 or mk2: dup = k2; break
        if dup:
            if dup['id'] == ev['id']: continue
            merged += 1
            have = {(s['n'], s.get('u')) for s in dup['src']}
            dup['src'] += [s for s in ev['src'] if (s['n'], s.get('u')) not in have]
            if dup['d'] != ev['d']: dup['fl']['datum'] = 'Quellen nennen verschiedene Termine: ' + dup['d'][8:10] + '.' + dup['d'][5:7] + '. und ' + ev['d'][8:10] + '.' + ev['d'][5:7] + '.'
            if not dup['gem'] and ev['gem']:
                for f in ('gem', 'bz', 'gemHow', 'venue'): dup[f] = ev[f]
                dup['fl'].pop('ort', None)
            if dup['title'].startswith('Markttag') and not ev['title'].startswith('Markttag'):
                for f in ('title', 'sum', 's', 'e', 'venue', 'org', 'topics'): dup[f] = ev[f] or dup[f]
                dup['fl'].pop('zeit', None)
            continue
        keepl.append(ev)
    # Prüfungen je Termin
    topfix = 0
    for e in keepl:
        tx = (e['title'] + ' ' + (e.get('sum') or '')).lower()
        if 'energie' in e['topics'] and len(e['topics']) > 1 and not re.search(ENERGIE_OK, tx): e['topics'] = [t for t in e['topics'] if t != 'energie']; topfix += 1
        if 'politik' in e['topics'] and not re.search(POLITIK_OK, tx): e['topics'] = [t for t in e['topics'] if t != 'politik'] or [FB.get(e['format'], 'regionen')]; topfix += 1
        if e.get('anm') and not re.search(r'anmeld|regist|ticket|karten|reserv|@|http|bis\s+\d|voranmeld|platz', e['anm'], re.I): e['anm'] = None
        if e['format'] == 'Sonstiges' and re.search(r'buchpräsentation|lesung|liest aus|vortrag', e['title'], re.I): e['format'] = 'Vortrag'
        if not e['topics']: e['topics'] = [FB.get(e['format'], 'regionen')]; e['fl']['tags'] = 'Thema aus dem Format abgeleitet'
        if e['gem'] and e['w'] == 'lokal' and e['src'][0]['n'] != MK and G[e['gem']][5] < 2000 and not e.get('_reachScaled'): e['reach'] = int(e['reach'] * 0.6); e['_reachScaled'] = True
        if e['gem']: e['min'] = G[e['gem']][3]; e['km'] = G[e['gem']][4]
        else: e['min'] = e['km'] = None
    keepl = [e for e in keepl if START <= (e.get('d2') or e['d']) and e['d'] <= END]
    for e in keepl:
        if e['d'] < START: e['d'] = START
    LOG['zusammengefuehrt'] = merged
    Q = {'n': len(keepl), 'themen_min1': sum(1 for e in keepl if e['topics']), 'themen_fallback': sum(1 for e in keepl if e['fl'].get('tags')),
         'format': dict(sorted({f: sum(1 for e in keepl if e['format'] == f) for f in FMT}.items(), key=lambda x: -x[1])),
         'rel': {r: sum(1 for e in keepl if e['rel'] == r) for r in ('hoch', 'mittel', 'niedrig')},
         'modus': {m: sum(1 for e in keepl if e['modus'] == m) for m in ('praesenz', 'hybrid', 'online')},
         'online_link': sum(1 for e in keepl if e.get('online')), 'reg_link': sum(1 for e in keepl if e.get('reg')),
         'anm_text': sum(1 for e in keepl if e.get('anm') and not e.get('reg')),
         'gemHow': {h: sum(1 for e in keepl if e.get('gemHow') == h) for h in ('ki', 'name', 'prefix', 'titel', 'geonames', 'none')},
         'gem_ok': sum(1 for e in keepl if e['gem']), 'online_ohne_ort': sum(1 for e in keepl if not e['gem'] and e['modus'] != 'praesenz'),
         'regel_n': sum(1 for e in keepl if e.get('ruleTopics')), 'regel_overlap': sum(1 for e in keepl if e.get('ruleTopics') and set(e['topics']) & set(e['ruleTopics'])),
         'topfix': topfix, 'chapman': {'n1': 0, 'n2': 0, 'm': 0}}
    LOG['qa'] = Q
    now = datetime.now(timezone.utc)
    run_id = 'r' + now.strftime('%Y%m%d%H%M')
    loc = vienna_now()
    out = a.out; os.makedirs(os.path.join(out, 'parts'), exist_ok=True)
    for f in glob.glob(os.path.join(out, 'parts', '*.json')): os.remove(f)
    clean_ev = [{k: v for k, v in e.items() if k not in ('_reachScaled',)} for e in keepl]
    parts, cur, size = [], [], 0
    for e in clean_ev:
        s = len(json.dumps(e, ensure_ascii=False))
        if cur and size + s > 150000: parts.append(cur); cur, size = [], 0
        cur.append(e); size += s
    if cur: parts.append(cur)
    for i, p in enumerate(parts, 1):
        json.dump({'runId': run_id, 'i': i, 'events': p}, open(os.path.join(out, 'parts', f'p{i}.json'), 'w'), ensure_ascii=False)
    meta = {'runId': run_id, 'ts': now.isoformat(), 'label': f"{loc.day}.{loc.month}.{loc.year}, {loc.hour}:{loc.minute:02d} Uhr", 'n': len(clean_ev),
            'parts': len(parts), 'hashes': S['hashes'], 'log': LOG, 'window': [START, END], 'prevRun': S.get('prevRun')}
    json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'), ensure_ascii=False)
    print(json.dumps({'runId': run_id, 'termine': len(clean_ev), 'teile': len(parts), 'zusammengefuehrt': merged, 'verworfen': len(LOG['verworfen']),
                      'ohne_gemeinde': Q['n'] - Q['gem_ok'], 'fehler': LOG['fehler']}, ensure_ascii=False, indent=1))

WT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
def cut(t, n): return t if len(t) <= n else t[:n].rsplit(' ', 1)[0].rstrip(' –-,:') + '…'
def fd(d): x = date.fromisoformat(d); return f'{WT[x.weekday()]} {x.day}.{x.month}.'
def cmd_notify(a):
    """Eine Zeile (unter 200 Zeichen) für die Handy-Mitteilung der Besitzerin oder des Besitzers. Vereinfachte Auswahl: Thema, Fahrzeit, Relevanz."""
    try: pj = json.load(open(a.push)); pr = pj.get('data', pj)
    except Exception: print(''); return
    if not pr.get('on') or pr.get('mode') != 'live': print(''); return
    what = pr.get('what') or {}
    _, prev = load_prev(a.prev); _, cur = load_prev(a.out)
    old = {e['id'] for e in prev}; byid = {e['id']: e for e in cur}
    today = vienna_today(); tom = (today + timedelta(days=1)).isoformat(); t2 = (today + timedelta(days=2)).isoformat()
    top = set(pr.get('top') or []); mx = pr.get('maxMin') or 90; kind = pr.get('kind') or 'labg'; org = pr.get('originGem')
    no = set(pr.get('no') or []); lo = pr.get('learnedOff') if isinstance(pr.get('learnedOff'), dict) else {}
    off = {k[4:] for k in lo if k.startswith('fmt:')}; toff = {k[4:] for k in lo if k.startswith('top:')}
    if isinstance(lo.get('weit'), (int, float)): mx = min(mx, lo['weit'])
    def fits(e):
        if e['id'] in no or not e.get('gem') or e['format'] in ('Kurs', 'Sonstiges') or e['rel'] == 'niedrig' or e['format'] in off: return False
        if (e.get('fl') or {}).get('cancelled'): return False
        if kind == 'gv': return e['gem'] == org or (e['rel'] == 'hoch' and org in G and G[e['gem']][2] == G[org][2])
        if e.get('min') is None or e['min'] > mx: return False
        if set(e['topics']) and set(e['topics']) <= toff: return False
        return (not top) or bool(top & set(e['topics']))
    neu = sorted([e for e in cur if e['id'] not in old and fits(e)], key=lambda e: (e['rel'] != 'hoch', e['d'])) if what.get('neu', True) else []
    mine = [byid[i] for i in set((pr.get('going') or []) + (pr.get('saved') or []) + (pr.get('reg') or [])) if i in byid]
    vortag = [e for e in mine if e['d'] == tom] if what.get('vortag', True) else []
    frist = []
    if what.get('frist', True):
        for e in mine:
            m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})?', e.get('anm') or '')
            if m:
                try: fdx = date(int(m.group(3) or today.year), int(m.group(2)), int(m.group(1))).isoformat()
                except ValueError: continue
                if today.isoformat() <= fdx <= t2: frist.append(e)
    bits = []
    if vortag: bits.append('Morgen: ' + cut(vortag[0]['title'], 60))
    if frist: bits.append('Anmeldefrist bald: ' + cut(frist[0]['title'], 50))
    if neu:
        e = neu[0]; bits.append(f"{len(neu)} neue passende Termine, z. B. {cut(e['title'], 60)} ({fd(e['d'])}, {e['gem']})")
    msg = 'Scanner: ' + ' · '.join(bits) if bits else ''
    print(msg[:199])

def cmd_due(a):
    """Ist heute ein Suchlauf fällig? Ausgabe: 'ja' oder 'nein' plus Grund. Standard: einmal pro Woche, Montag."""
    def rd(f):
        try: j = json.load(open(f)); return j.get('data', j) if isinstance(j, dict) else {}
        except Exception: return {}
    c = rd(a.cfg) if a.cfg else {}; m = rd(a.latest) if a.latest else {}
    rh = c.get('rhythm') if c.get('rhythm') in ('tag', 'zwei', 'woche', 'zwoche') else 'woche'
    day = int(c.get('day') or 1) if str(c.get('day') or '1').isdigit() else 1
    now = vienna_now(); wd = now.isoweekday()
    last = None
    try: last = datetime.fromisoformat(str(m.get('ts')).replace('Z', '+00:00')).astimezone(timezone.utc)
    except Exception: pass
    age = (datetime.now(timezone.utc) - last).total_seconds() / 86400 if last else 999
    soll = {'tag': 1, 'zwei': 3.5, 'woche': 7, 'zwoche': 14}[rh]
    if age >= soll + 1.5: print(f'ja: letzter Lauf vor {age:.1f} Tagen, Rhythmus {rh}'); return
    if age < 0.5: print(f'nein: letzter Lauf erst vor {age*24:.0f} Stunden'); return
    if rh == 'tag': print('ja: täglicher Rhythmus'); return
    if rh == 'zwei': print('ja: Montag oder Donnerstag' if wd in (1, 4) else 'nein: zweimal pro Woche, heute nicht'); return
    if wd != day: print(f'nein: Suchtag ist {WT[day-1]}, heute {WT[wd-1]}'); return
    if rh == 'zwoche' and age < 12: print(f'nein: alle zwei Wochen, letzter Lauf vor {age:.1f} Tagen'); return
    print(f'ja: Suchtag {WT[day-1]}')

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd')
    f = sp.add_parser('fetch'); f.add_argument('--prev', default=''); f.add_argument('--work', required=True)
    m = sp.add_parser('merge'); m.add_argument('--work', required=True); m.add_argument('--out', required=True)
    n = sp.add_parser('notify'); n.add_argument('--push', required=True); n.add_argument('--prev', default=''); n.add_argument('--out', required=True)
    d = sp.add_parser('due'); d.add_argument('--cfg', default=''); d.add_argument('--latest', default='')
    a = ap.parse_args()
    {'fetch': cmd_fetch, 'merge': cmd_merge, 'notify': cmd_notify, 'due': cmd_due}[a.cmd](a)
