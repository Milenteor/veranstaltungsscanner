// Startet den Suchlauf auf GitHub sofort ("Neue Suche starten") oder schickt eine Test-Mitteilung
import { caller, json, cors, allow } from "../_shared/util.ts";

const GH_TOKEN = Deno.env.get("GH_TOKEN") || "";      // fein abgestimmter Token, nur dieses Repo, Actions: Read and write
const GH_REPO = Deno.env.get("GH_REPO") || "";        // z. B. dein-name/veranstaltungsscanner
const WF = "scan.yml";

async function gh(path: string, init: RequestInit = {}) {
  return await fetch("https://api.github.com/repos/" + GH_REPO + path, {
    ...init,
    headers: { "Authorization": "Bearer " + GH_TOKEN, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "veranstaltungsscanner", ...(init.headers || {}) },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ code: "method" }, 405);
  const who = await caller(req);
  if (!who || !who.member) return json({ code: "not_granted", message: "Nicht angemeldet oder nicht freigeschaltet" }, 401);
  if (!GH_TOKEN || !GH_REPO) return json({ code: "not_configured", message: "GH_TOKEN oder GH_REPO fehlt" }, 500);
  let body: { mode?: string } = {};
  try { body = await req.json(); } catch (_) { /* leer ist ok */ }
  const mode = body.mode === "pushtest" ? "pushtest" : "scan";

  if (mode === "scan") {
    for (const st of ["in_progress", "queued"]) {
      const r = await gh(`/actions/workflows/${WF}/runs?status=${st}&per_page=5`);
      if (r.ok) { const j = await r.json(); if ((j.total_count || 0) > 0) return json({ code: "rate_limited", message: "Es läuft gerade schon eine Suche. Ergebnis kommt in einigen Minuten." }, 429); }
    }
    if (!(await allow(who.uid, "scan", Number(Deno.env.get("SCAN_PER_DAY") || "4")))) return json({ code: "rate_limited", message: "Heute schon mehrere Suchen gestartet. Morgen wieder." }, 429);
  } else if (!(await allow(who.uid, "pushtest", 6))) return json({ code: "rate_limited", message: "Bitte später noch einmal" }, 429);

  const r = await gh(`/actions/workflows/${WF}/dispatches`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: Deno.env.get("GH_REF") || "main", inputs: { mode, uid: who.uid } }),
  });
  if (r.status !== 204) return json({ code: "upstream", message: "GitHub: " + r.status + " " + (await r.text()).slice(0, 200) }, 502);
  return json({ ok: true, message: mode === "scan" ? "Gestartet. Dauert etwa 10 bis 20 Minuten. Danach kommt eine Mitteilung, wenn sie eingeschaltet ist." : "Test-Mitteilung kommt in etwa einer Minute." });
});
