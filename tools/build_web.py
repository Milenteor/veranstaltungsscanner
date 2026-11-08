#!/usr/bin/env python3
"""Baut web/index.html aus src/app.html (der Artefakt-Fassung der App).
Jede Änderung muss genau einmal passen, sonst bricht das Skript ab. So fällt sofort auf,
wenn sich die App-Fassung geändert hat und ein Eingriff angepasst werden muss.
Aufruf: python3 tools/build_web.py"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'src', 'app.html'), encoding='utf-8').read()

def once(s, old, new, label):
    n = s.count(old)
    if n != 1: sys.exit(f'Eingriff "{label}" passt {n}-mal statt einmal')
    return s.replace(old, new)

HEAD = ('<meta name="theme-color" content="#CB1967"><link rel="manifest" href="manifest.webmanifest">'
        '<link rel="apple-touch-icon" href="apple-touch-icon.png"><meta name="apple-mobile-web-app-capable" content="yes">'
        '<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="default">'
        '<meta name="apple-mobile-web-app-title" content="Termine">'
        '<script src="config.js"></script><script src="vendor/supabase.js"></script><script src="backend.js"></script>')
s = once(src, '</style></head><body>', '</style>' + HEAD + '</head><body>', 'Kopf')
s = once(s, 'const APP_URL="https://claude.ai/artifact/SUzPecCXhCQJot8oUbgr5y";',
         'const APP_URL=(window.VS_CONFIG&&VS_CONFIG.appUrl)||(location.origin+location.pathname);', 'App-Adresse')
s = once(s, "function inArtifact(){return typeof window!=='undefined'&&!!window.claude;}",
         "function inArtifact(){return typeof window!=='undefined'&&!!window.claude&&!window.VS_SELF;}", 'inArtifact')
s = once(s, "S.mode=Store.flag('mode')||'demo';", "S.mode=Store.flag('mode')||(window.VS_SELF?'live':'demo');", 'Startmodus')
# Uhrzeit des Suchlaufs aus config.js statt 5:45
n = s.count('5:45 Uhr')
s = s.replace('5:45 Uhr', "'+(window.VS_TIME||'5:45 Uhr')+'")
print('Uhrzeit ersetzt:', n)
s = once(s, 'Kommt morgens gegen \'+(window.VS_TIME||\'5:45 Uhr\')+\' über die Claude-App, wenn es etwas Neues gibt oder morgen ein Termin ansteht. Im Prototyp nur für die Person, der die App gehört, und ohne Gewähr, dass jede Mitteilung ankommt.',
         "'+(window.VS_SELF?'Kommt nach dem Suchlauf um '+VS_TIME+', wenn es etwas Neues gibt, eine Frist abläuft oder morgen ein Termin ansteht. Einrichten auf diesem Gerät: weiter unten bei „Mitteilungen auf diesem Gerät“.':'Kommt morgens gegen 5:45 Uhr über die Claude-App, wenn es etwas Neues gibt oder morgen ein Termin ansteht. Im Prototyp nur für die Person, der die App gehört, und ohne Gewähr, dass jede Mitteilung ankommt.')+'",
         'Text Mitteilungen')
s = once(s, "note='Gesucht wird um '+(window.VS_TIME||'5:45 Uhr')+', '+rhyLabel()+'. Die Seite selbst darf keine fremden Webseiten öffnen, darum holt dieser Knopf den neuesten fertigen Lauf.';",
         "note=window.VS_SELF?VS.scanNote():'Gesucht wird um 5:45 Uhr, '+rhyLabel()+'. Die Seite selbst darf keine fremden Webseiten öffnen, darum holt dieser Knopf den neuesten fertigen Lauf.';", 'Text Suche')
s = once(s, "'<p class=\"xs muted\">'+esc(note)+'</p><div class=\"acts\"><button class=\"btn pri\" data-act=\"close\" data-goto=\"fuerdich\">Zum Briefing</button>",
         "'<p class=\"xs muted\">'+esc(note)+'</p>'+(window.VS_SELF&&live?VS.scanBtnHtml():'')+'<div class=\"acts\"><button class=\"btn pri\" data-act=\"close\" data-goto=\"fuerdich\">Zum Briefing</button>", 'Knopf neue Suche')
s = once(s, "h+='<h3>Deine Daten</h3>", "if(window.VS_SELF)h+=VS.einstHtml();h+='<h3>Deine Daten</h3>", 'Einstellungen')
s = once(s, "const item=(q,a,open)=>'<details'+(open?' open':'')+'><summary>'+q+'</summary><div class=\"ans\">'+a+'</div></details>';",
         "const item=(q,a,open)=>{if(window.VS_SELF&&window.VS&&VS.faq&&Object.prototype.hasOwnProperty.call(VS.faq,q))a=VS.faq[q];return a===null?'':'<details'+(open?' open':'')+'><summary>'+q+'</summary><div class=\"ans\">'+a+'</div></details>';};", 'FAQ')
out = os.path.join(ROOT, 'web', 'index.html')
open(out, 'w', encoding='utf-8').write(s)
print('geschrieben:', out, len(s), 'Zeichen')
