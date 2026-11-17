import { useEffect, useId, useState, type FormEvent } from "react";

const ENDPOINT = "/api/v1/waitlist";
const MAX_ARTISTS = 10;

type Consent = { version: string; copy: string };
type Phase = "loading" | "ready" | "closed" | "sending" | "done";

/** First-touch attribution from ?src= (or utm_source); the server normalises it. */
export function sourceFromSearch(search: string): string {
  const params = new URLSearchParams(search);
  return (params.get("src") ?? params.get("utm_source") ?? "").trim().toLowerCase().slice(0, 64);
}

export function parseArtists(value: string): string[] {
  const seen: string[] = [];
  for (const raw of value.split(/[,\n]/)) {
    const name = raw.replace(/\s+/g, " ").trim().slice(0, 100);
    if (name && !seen.includes(name)) seen.push(name);
  }
  return seen.slice(0, MAX_ARTISTS);
}

const MESSAGES: Record<number, string> = {
  409: "The sign-up text has changed. We've loaded the new version; please read it and try again.",
  422: "Check the email address and tick the box to join.",
  429: "Too many sign-ups from this connection. Please try again in a few minutes.",
};

export default function WaitlistForm() {
  const id = useId();
  const [consent, setConsent] = useState<Consent | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [artists, setArtists] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [website, setWebsite] = useState("");

  async function loadConsent(signal?: AbortSignal) {
    try {
      const response = await fetch(`${ENDPOINT}/consent`, { cache: "no-store", signal });
      if (!response.ok) throw new Error(String(response.status));
      setConsent((await response.json()) as Consent);
      setAgreed(false);
      setPhase("ready");
    } catch {
      if (!signal?.aborted) setPhase("closed");
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void loadConsent(controller.signal);
    return () => controller.abort();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!consent || phase === "sending") return;
    setError("");
    setPhase("sending");
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          consent: agreed,
          consent_version: consent.version,
          source: sourceFromSearch(window.location.search) || null,
          artists: parseArtists(artists),
          website,
        }),
      });
      if (response.status === 202) {
        setPhase("done");
        return;
      }
      if (response.status === 409) await loadConsent();
      else if (response.status === 503) {
        setPhase("closed");
        return;
      } else setPhase("ready");
      setError(MESSAGES[response.status] ?? "Something went wrong. Please try again.");
    } catch {
      setPhase("ready");
      setError("We couldn't reach Sweet Seats. Check your connection and try again.");
    }
  }

  if (phase === "done") {
    return (
      <p role="status" className="rounded-xl border border-rule bg-charcoal p-5 text-sm leading-relaxed">
        <span className="font-semibold">Thanks, you're on the list.</span>{" "}
        <span className="text-soft">We'll email you when the pilot opens. You can unsubscribe at any time.</span>
      </p>
    );
  }

  if (phase === "closed") {
    return <p role="status" className="text-sm text-soft">The waitlist isn't open yet. Please check back soon.</p>;
  }

  return (
    <form onSubmit={submit} className="flex max-w-md flex-col gap-4" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="text-lg font-bold tracking-tight">Join the waitlist</h2>
      <label className="flex flex-col gap-1.5 text-sm font-semibold">
        Email
        <input
          type="email"
          name="email"
          required
          maxLength={254}
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="min-h-11 rounded-lg border border-rule bg-background px-3 font-normal text-foreground"
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm font-semibold">
        <span>
          Artists you'd follow <span className="font-normal text-soft">(optional, comma separated, up to {MAX_ARTISTS})</span>
        </span>
        <input
          type="text"
          name="artists"
          maxLength={1000}
          autoComplete="off"
          value={artists}
          onChange={(e) => setArtists(e.target.value)}
          className="min-h-11 rounded-lg border border-rule bg-background px-3 font-normal text-foreground"
        />
      </label>
      {/* Honeypot: hidden from people and assistive technology; bots fill it in. */}
      <div aria-hidden="true" className="absolute -left-[10000px] h-px w-px overflow-hidden">
        <label>
          Website
          <input type="text" name="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
        </label>
      </div>
      <label className="flex gap-3 text-sm leading-relaxed text-soft">
        <input
          type="checkbox"
          name="consent"
          required
          checked={agreed}
          disabled={!consent}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1 h-4 w-4 shrink-0 accent-coral"
        />
        <span>{consent ? consent.copy : "Loading the sign-up terms…"}</span>
      </label>
      {error && <p role="alert" className="text-sm text-coral">{error}</p>}
      <button
        type="submit"
        disabled={!consent || !agreed || phase === "sending"}
        className="ss-button ss-button--primary w-fit disabled:opacity-60"
      >
        {phase === "sending" ? "Joining…" : "Join the waitlist"}
      </button>
    </form>
  );
}
