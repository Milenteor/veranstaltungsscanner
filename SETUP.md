# Veranstaltungsscanner als echte App: Einrichtung (Weg A)

Ergebnis am Ende: Eine App auf dem iPhone-Home-Bildschirm mit eigener Adresse, Anmeldung per Mail-Code, Mitteilungen aufs Handy, Kalender-Abo für iPhone und Outlook, „Neue Suche starten“, die Links aus „＋ Termin“ werden sofort gelesen. Der Suchlauf läuft von selbst, ohne dass du etwas tun musst.

Zeitbedarf: etwa 60 bis 90 Minuten, einmalig. Programmieren musst du nichts, nur Konten anlegen, Werte kopieren und Knöpfe drücken.

## Was wo läuft

| Teil | Dienst | Kosten |
|---|---|---|
| App-Seite (die Oberfläche) | GitHub Pages | kostenlos |
| Suchlauf (wöchentlich, plus Knopf) | GitHub Actions | kostenlos bei öffentlichem Repository |
| Datenbank, Anmeldung, Kalender-Abo | Supabase, Region Frankfurt | Free-Plan reicht für den Pilot |
| KI (Taggen, Suchfragen, Links lesen) | Anthropic API | nach Verbrauch, Limit selbst festlegen |
| Mails mit Anmeldecode | eigener Mail-Versand (SMTP), z. B. Brevo | Free-Plan reicht |

Ein Repository auf GitHub ist ein Ordner mit den Dateien des Projekts. „Öffentlich“ heißt: Der Programmcode ist sichtbar. Geheimnisse (Schlüssel) liegen getrennt und sind nie sichtbar. Termine und Klicks liegen in Supabase und sind ohne Anmeldung nicht lesbar.

## Schritt 1: GitHub

1. Konto anlegen auf github.com (falls noch keins).
2. Oben rechts **+ › New repository**. Name: `veranstaltungsscanner`. **Public** wählen. „Add a README“ nicht anhaken. **Create repository**.
3. Auf der leeren Seite **uploading an existing file** anklicken. Den Inhalt des entpackten ZIP-Ordners hineinziehen (alle Ordner und Dateien, nicht den Ordner selbst). **Commit changes**.
   - Achtung Mac: Der Ordner `.github` ist im Finder versteckt. Im Finder **Cmd + Shift + .** drücken, dann ist er sichtbar und kann mitgezogen werden. Ohne diesen Ordner läuft nichts automatisch.
   - Prüfen: Im Repository muss ein Ordner `.github/workflows` mit drei Dateien stehen.
4. **Settings › Pages › Build and deployment › Source: GitHub Actions** wählen.
5. Deine App-Adresse lautet dann `https://DEIN-GITHUB-NAME.github.io/veranstaltungsscanner/`. Notieren.

## Schritt 2: Supabase (Datenbank und Anmeldung)

1. Konto auf supabase.com, **New project**. Name `veranstaltungsscanner`, Region **Central EU (Frankfurt)**, ein sicheres Datenbank-Passwort (wird nicht weiter gebraucht, aber aufheben).
2. Links **SQL Editor › New query**. Den ganzen Inhalt von `supabase/schema.sql` hineinkopieren, **Run**. Es muss „Success“ erscheinen.
3. Im selben Editor deine eigene Adresse als Verwalter:in eintragen und **Run**:
   ```sql
   insert into public.members (email, admin) values ('deine@adresse.at', true);
   ```
4. **Authentication › Sign In / Providers › Email**: „Enable Email provider“ an. „Confirm email“ an lassen.
5. **Authentication › Emails › Templates › Magic Link**: Den Text ersetzen durch
   ```html
   <h2>Dein Anmeldecode</h2><p>Gib diesen Code in der App ein: <b>{{ .Token }}</b></p><p>Er gilt eine Stunde.</p>
   ```
   Betreff zum Beispiel „Dein Code für den Veranstaltungsscanner“. Speichern.
6. **Authentication › URL Configuration › Site URL**: deine App-Adresse aus Schritt 1.5.
7. **Mail-Versand einrichten (wichtig):** Der eingebaute Versand von Supabase schickt nur an Mitglieder deines Supabase-Teams und nur 2 Mails pro Stunde. Für Kolleginnen und Kollegen brauchst du einen eigenen Versand:
   - Zum Beispiel bei brevo.com ein kostenloses Konto anlegen, dort unter **SMTP & API** die SMTP-Zugangsdaten holen und die Absender-Adresse bestätigen.
   - In Supabase **Authentication › Emails › SMTP Settings**: „Enable Custom SMTP“ an, Host, Port, Benutzer, Passwort und Absender eintragen. Speichern.
   - Alternativ geht der SMTP-Zugang eines eigenen Postfachs, wenn die IT ihn freigibt.
8. **Project Settings › API Keys** (oder **API**): Notiere
   - die **Project URL** (`https://xxxx.supabase.co`), der Teil `xxxx` ist die **Project Ref**,
   - den **anon** oder **publishable** Schlüssel (öffentlich, kommt in die App),
   - den **service_role** oder **secret** Schlüssel (geheim, nur für GitHub).
9. **Account (oben rechts) › Access Tokens › Generate new token**, Name „github“. Notieren (geheim).

## Schritt 3: Schlüssel für Mitteilungen

Die Datei `tools/schluessel.html` aus dem ZIP doppelklicken. Sie öffnet sich im Browser und schickt nichts ins Netz. **Schlüssel erzeugen** drücken und die drei Werte notieren:
- VAPID öffentlich → kommt in die App (Schritt 6),
- VAPID privat → GitHub-Geheimnis,
- Zufallswert → GitHub-Geheimnis `CRON_SECRET`.

## Schritt 4: Anthropic (KI)

1. console.anthropic.com, Konto anlegen, Zahlungsmittel hinterlegen.
2. **Settings › Limits**: ein Monatslimit setzen, zum Beispiel 20 €. Mehr kann dann nicht anfallen.
3. **API Keys › Create Key**, Name „veranstaltungsscanner“. Notieren (geheim).

## Schritt 5: GitHub-Schlüssel für den Knopf „Neue Suche starten“

1. github.com › dein Profilbild › **Settings › Developer settings › Personal access tokens › Fine-grained tokens › Generate new token**.
2. Name „scan-knopf“, Ablauf 1 Jahr, **Only select repositories › veranstaltungsscanner**.
3. **Repository permissions › Actions: Read and write**. Sonst nichts.
4. **Generate token**, notieren (geheim). In einem Jahr erneuern (GitHub erinnert per Mail).

## Schritt 6: Werte eintragen

**a) In der App:** Im Repository die Datei `web/config.js` öffnen, oben rechts auf den Stift. Eintragen:
- `supabaseUrl`: Project URL,
- `supabaseAnonKey`: anon- oder publishable-Schlüssel,
- `vapidPublicKey`: VAPID öffentlich.

**Commit changes**. Danach baut GitHub die App-Seite selbst (unter **Actions** sichtbar, dauert etwa eine Minute).

**b) Geheimnisse:** Im Repository **Settings › Secrets and variables › Actions › New repository secret**, je Zeile eines:

| Name | Wert |
|---|---|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SERVICE_KEY` | service_role- oder secret-Schlüssel |
| `SUPABASE_PROJECT_REF` | der Teil `xxxx` aus der Project URL |
| `SUPABASE_ACCESS_TOKEN` | Access Token aus Schritt 2.9 |
| `ANTHROPIC_API_KEY` | aus Schritt 4 |
| `VAPID_PRIVATE_KEY` | VAPID privat |
| `VAPID_SUBJECT` | `mailto:deine@adresse.at` |
| `CRON_SECRET` | Zufallswert aus Schritt 3 |
| `GH_DISPATCH_TOKEN` | Token aus Schritt 5 |

**c) Variablen:** Gleiche Seite, Reiter **Variables › New repository variable**:

| Name | Wert |
|---|---|
| `APP_URL` | deine App-Adresse |
| `APP_ORIGIN` | `https://DEIN-GITHUB-NAME.github.io` (ohne Pfad) |

## Schritt 7: Starten

Im Repository auf **Actions**. Falls GitHub fragt, ob Workflows laufen dürfen: bestätigen.

Rote Läufe aus der Zeit vor Schritt 6 sind normal (da fehlten die Schlüssel noch) und können ignoriert werden.

1. Links **Edge Functions einrichten › Run workflow › Run workflow**. Warten, bis ein grüner Haken erscheint (etwa 2 Minuten).
2. Links **Suchlauf › Run workflow**, bei „mode“ `seed` eintippen, **Run workflow**. Lädt den letzten Datenstand aus dem Prototyp hoch.
3. Noch einmal **Suchlauf › Run workflow**, mode `check`. Alle drei Prüfungen müssen „ok“ bzw. „vorhanden“ zeigen (Ergebnis in der Zusammenfassung des Laufs).
4. Noch einmal mit mode `scan`. Der erste echte Lauf dauert 15 bis 30 Minuten. Danach stehen frische Termine in der App.

Ab jetzt läuft alles von selbst: jeden Tag um 9:20 Uhr Wiener Zeit prüft der Suchlauf, ob nach dem eingestellten Rhythmus gesucht werden soll (Standard: montags). Mitteilungen kommen danach, gegen 9:30 Uhr, und nie zwischen 21 und 8 Uhr.

## Schritt 8: Auf dem iPhone

1. Die App-Adresse in **Safari** öffnen (nicht in Chrome und nicht in der Claude-App).
2. Unten auf **Teilen** (Viereck mit Pfeil), dann **„Zum Home-Bildschirm“**, **Hinzufügen**.
3. Die App ab jetzt über das neue Symbol öffnen.
4. Mail-Adresse eingeben, Code aus der Mail eintippen.
5. **Einstellungen › Aufs Handy** einschalten, Rückfrage mit **Erlauben** beantworten. Mit **Test-Mitteilung schicken** prüfen (kommt nach etwa einer Minute).
6. **Einstellungen › Kalender-Abo › iPhone-Kalender abonnieren** antippen, bestätigen. Ab dann erscheinen alle Zusagen von selbst im Kalender.
7. Für Outlook am Computer: **Outlook abonnieren** in der App am Computer anklicken.

Mitteilungen auf dem iPhone gehen nur über das Home-Bildschirm-Symbol und ab iOS 16.4. Das ist eine Vorgabe von Apple.

## Kolleginnen und Kollegen freischalten

Supabase › SQL Editor:
```sql
insert into public.members (email) values ('kollegin@beispiel.at'), ('kollege@beispiel.at');
```
Für weitere Verwalter:innen `admin` auf `true` setzen. Verwalter:innen dürfen den Suchrhythmus ändern. Danach die App-Adresse und diese Anleitung ab Schritt 8 weitergeben.

Jemand soll keinen Zugang mehr haben:
```sql
delete from public.members where email = 'adresse@beispiel.at';
```

## Wenn etwas nicht geht

| Beobachtung | Ursache und Lösung |
|---|---|
| Kein Code kommt an | SMTP aus Schritt 2.7 fehlt oder Absender nicht bestätigt. Supabase › Authentication › Logs zeigt den Fehler. |
| „Noch kein Zugang“ | Adresse fehlt in `members` oder ist anders geschrieben. |
| „Neue Suche starten“ meldet einen Fehler | `GH_DISPATCH_TOKEN` fehlt oder ist abgelaufen; danach **Edge Functions einrichten** neu starten. |
| Keine Mitteilung | Nur über das Home-Bildschirm-Symbol; in iPhone-Einstellungen › Mitteilungen › Termine prüfen. |
| Suchlauf rot | Unter **Actions** den Lauf öffnen, die Zusammenfassung zeigt den Grund. Bei weniger als 200 Terminen lädt er absichtlich nichts hoch und die App behält den letzten guten Stand. |
| Zeitplan läuft nicht mehr | GitHub schaltet Zeitpläne in öffentlichen Repositories nach 60 Tagen ohne Aktivität ab. Der Suchlauf versucht das zu verhindern. Falls es doch passiert: **Actions › Suchlauf › Enable workflow**. |

## Später: Umzug nach Microsoft 365 (Weg B)

Alles hier ist so gebaut, dass es sich übertragen lässt:

| Heute (Weg A) | In Microsoft 365 (Weg B) |
|---|---|
| Supabase-Tabelle `docs` (Pfad, Daten) | SharePoint-Listen oder Dataverse-Tabellen mit denselben Feldern |
| GitHub-Suchlauf `pipeline/run.py` | Power-Automate-Ablauf mit Zeitplan (Recurrence); `update.py` als Azure Function oder gleich in Power Automate nachgebaut |
| KI-Tagging über Anthropic-API | gleiche Prompts, aufgerufen aus Power Automate (HTTP-Aktion oder freigegebener KI-Connector) |
| Kalender-Abo | „Ich gehe hin“ schreibt direkt in den Dienstkalender (Outlook-Connector „Create event (V4)“) |
| Web Push | Power-Apps-Mitteilung oder Teams-Nachricht |
| Anmeldung per Mail-Code | Microsoft-Konto der Organisation (Entra ID) |

Die Termindaten (Format in `seed/runs`) und der Tag-Katalog (`pipeline/KATALOG.md`) bleiben gleich.
