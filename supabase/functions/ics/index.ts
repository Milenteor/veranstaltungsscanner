// Persönliches Kalender-Abo: alle Zusagen einer Person als iCalendar (webcal)
import { admin } from "../_shared/util.ts";

const VTZ = [
  "BEGIN:VTIMEZONE", "TZID:Europe/Vienna",
  "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST", "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
  "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET", "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
  "END:VTIMEZONE",
];
const esc = (s: string) => String(s || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/[,;]/g, (c) => "\\" + c);
function fold(l: string) {
  const out: string[] = []; const enc = new TextEncoder(); let cur = ""; let n = 0;
  for (const ch of l) { const b = enc.encode(ch).length; if (n + b > 73) { out.push(cur); cur = " "; n = 1; } cur += ch; n += b; }
  out.push(cur); return out.join("\r\n");
}
const ymd = (d: string) => d.replace(/-/g, "");
function nextDay(d: string) { const x = new Date(d + "T12:00:00Z"); x.setUTCDate(x.getUTCDate() + 1); return x.toISOString().slice(0, 10); }
function addH(t: string, h: number) { const [a, b] = t.split(":").map(Number); return String(Math.min(23, a + h)).padStart(2, "0") + ":" + String(b).padStart(2, "0"); }

type Ev = { id: string; d: string; d2?: string | null; s?: string | null; e?: string | null; title: string; venue?: string; gem?: string; org?: string; sum?: string; url?: string; online?: string | null };

Deno.serve(async (req) => {
  const t = new URL(req.url).searchParams.get("t") || "";
  if (!/^[0-9a-f]{40}$/.test(t)) return new Response("Nicht gefunden", { status: 404 });
  const db = admin();
  const tok = await db.from("docs").select("path").like("path", "data/users/%/icstok").eq("data->>token", t).limit(1).maybeSingle();
  if (tok.error || !tok.data) return new Response("Nicht gefunden", { status: 404 });
  const uid = tok.data.path.split("/")[2];
  const feed = await db.from("docs").select("data").eq("path", `data/users/${uid}/calfeed`).maybeSingle();
  const evs: Ev[] = (feed.data?.data?.events || []) as Ev[];
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  const L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Veranstaltungsscanner Steiermark//DE", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    "X-WR-CALNAME:NEOS Termine (Zusagen)", "X-WR-TIMEZONE:Europe/Vienna", "REFRESH-INTERVAL;VALUE=DURATION:PT4H", "X-PUBLISHED-TTL:PT4H", ...VTZ];
  for (const e of evs) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(e.d)) continue;
    L.push("BEGIN:VEVENT", `UID:${e.id}@veranstaltungsscanner`, `DTSTAMP:${stamp}`);
    if (e.s && /^\d{2}:\d{2}$/.test(e.s)) {
      const end = e.e && e.e > e.s ? e.e : addH(e.s, 2);
      L.push(`DTSTART;TZID=Europe/Vienna:${ymd(e.d)}T${e.s.replace(":", "")}00`, `DTEND;TZID=Europe/Vienna:${ymd(e.d2 && e.d2 > e.d ? e.d2 : e.d)}T${end.replace(":", "")}00`);
    } else {
      L.push(`DTSTART;VALUE=DATE:${ymd(e.d)}`, `DTEND;VALUE=DATE:${ymd(nextDay(e.d2 && e.d2 > e.d ? e.d2 : e.d))}`);
    }
    L.push(fold("SUMMARY:" + esc(e.title)));
    const loc = [e.venue, e.gem].filter(Boolean).join(", ");
    if (loc) L.push(fold("LOCATION:" + esc(loc)));
    const desc = [e.sum, e.org ? "Veranstalter: " + e.org : "", e.online ? "Online: " + e.online : "", e.url ? "Quelle: " + e.url : ""].filter(Boolean).join("\n");
    if (desc) L.push(fold("DESCRIPTION:" + esc(desc)));
    if (e.url && /^https?:\/\//.test(e.url)) L.push(fold("URL:" + e.url));
    L.push("TRANSP:OPAQUE", "END:VEVENT");
  }
  L.push("END:VCALENDAR");
  return new Response(L.join("\r\n") + "\r\n", {
    headers: { "Content-Type": "text/calendar; charset=utf-8", "Content-Disposition": 'inline; filename="neos-termine.ics"', "Cache-Control": "private, max-age=900" },
  });
});
