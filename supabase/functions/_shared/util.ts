// Gemeinsame Hilfen für die Edge Functions
import { createClient, SupabaseClient } from "npm:@supabase/supabase-js@2";

export const URL_ = Deno.env.get("SUPABASE_URL")!;
// Neue Schlüssel (sb_publishable_/sb_secret_) bevorzugen, alte als Rückfall (Supabase stellt die alten 2027 ab)
function keyFrom(json: string | undefined, legacy: string): string {
  try { const o = JSON.parse(json || "{}"); if (o && typeof o.default === "string" && o.default) return o.default; } catch (_) { /* weiter */ }
  return Deno.env.get(legacy) || "";
}
const ANON = keyFrom(Deno.env.get("SUPABASE_PUBLISHABLE_KEYS"), "SUPABASE_ANON_KEY");
const SERVICE = keyFrom(Deno.env.get("SUPABASE_SECRET_KEYS"), "SUPABASE_SERVICE_ROLE_KEY");
const ORIGIN = Deno.env.get("APP_ORIGIN") || "*";   // z. B. https://dein-name.github.io

export const cors = {
  "Access-Control-Allow-Origin": ORIGIN,
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-vs-cron",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};
export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json; charset=utf-8" } });
}
export function admin(): SupabaseClient {
  return createClient(URL_, SERVICE, { auth: { persistSession: false } });
}
export type Caller = { uid: string; email: string; member: boolean; admin: boolean; cron: boolean };

/** Prüft, wer aufruft: angemeldetes Mitglied (Bearer-Token) oder der Suchlauf (x-vs-cron). */
export async function caller(req: Request): Promise<Caller | null> {
  const cronSecret = Deno.env.get("CRON_SECRET");
  if (cronSecret && req.headers.get("x-vs-cron") === cronSecret) return { uid: "", email: "", member: true, admin: true, cron: true };
  const auth = req.headers.get("Authorization") || "";
  const token = auth.replace(/^Bearer\s+/i, "");
  if (!token) return null;
  const sb = createClient(URL_, ANON, { global: { headers: { Authorization: "Bearer " + token } }, auth: { persistSession: false } });
  const { data, error } = await sb.auth.getUser(token);
  if (error || !data.user) return null;
  const m = await sb.rpc("is_member"); const a = await sb.rpc("is_admin");
  return { uid: data.user.id, email: data.user.email || "", member: !!m.data, admin: !!a.data, cron: false };
}

/** Tageslimit je Person und Art. true = erlaubt. */
export async function allow(uid: string, kind: string, perDay: number): Promise<boolean> {
  if (!uid) return true;
  const db = admin();
  const since = new Date(Date.now() - 86400000).toISOString();
  const { count } = await db.from("ask_log").select("id", { count: "exact", head: true }).eq("uid", uid).eq("kind", kind).gte("at", since);
  if ((count || 0) >= perDay) return false;
  await db.from("ask_log").insert({ uid, kind });
  return true;
}

/** Ein Aufruf der Anthropic-API. Gibt den Text der Antwort zurück. */
export async function claude(system: string, user: string, tier: string, maxTokens = 2000): Promise<{ text: string; truncated: boolean }> {
  const key = Deno.env.get("ANTHROPIC_API_KEY");
  if (!key) throw new Error("ANTHROPIC_API_KEY fehlt");
  const model = tier === "quick" ? (Deno.env.get("MODEL_QUICK") || "claude-haiku-4-5-20251001") : (Deno.env.get("MODEL_MAIN") || "claude-sonnet-5-5");
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model, max_tokens: maxTokens, system, messages: [{ role: "user", content: user }] }),
  });
  if (!r.ok) throw new Error("Anthropic " + r.status + ": " + (await r.text()).slice(0, 300));
  const j = await r.json();
  const text = (j.content || []).filter((c: { type: string }) => c.type === "text").map((c: { text: string }) => c.text).join("");
  return { text, truncated: j.stop_reason === "max_tokens" };
}

/** Erstes JSON-Objekt oder -Array aus einem Text. */
export function firstJson(t: string): unknown {
  const s = t.replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/, "").trim();
  try { return JSON.parse(s); } catch (_) { /* weiter */ }
  const i = s.search(/[\[{]/); if (i < 0) throw new Error("kein JSON");
  const open = s[i], close = open === "{" ? "}" : "]";
  let depth = 0, inStr = false, esc = false;
  for (let k = i; k < s.length; k++) {
    const c = s[k];
    if (inStr) { if (esc) esc = false; else if (c === "\\") esc = true; else if (c === '"') inStr = false; continue; }
    if (c === '"') inStr = true; else if (c === open) depth++; else if (c === close) { depth--; if (depth === 0) return JSON.parse(s.slice(i, k + 1)); }
  }
  throw new Error("JSON unvollständig");
}
