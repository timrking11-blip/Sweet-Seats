import { brandNavigation } from "../../../../lib/sweet-seats-brand/foundation";
import { useEffect, useState } from "react";
import WaitlistForm from "../components/waitlist-form";

const GH = "https://github.com/timrking11-blip";
const BASE = import.meta.env.BASE_URL;
const VIDEO_SOURCE = "/api/storage/public-objects/sweet-seats-final-cut-v3.mp4";

const wrap = "mx-auto w-full max-w-[1250px] px-5 sm:px-8";
const eyebrow = "text-xs font-semibold tracking-[0.18em] text-coral";

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden="true">
      <path d="M4 9h24v5a2 2 0 0 0 0 4v5H4v-5a2 2 0 0 0 0-4z" className="fill-coral" />
      <path d="M16 11.5l1.2 2.5 2.7.3-2 1.9.5 2.7-2.4-1.3-2.4 1.3.5-2.7-2-1.9 2.7-.3z" className="fill-ink" />
    </svg>
  );
}

function Trailer() {
  const [availability, setAvailability] = useState<
    "checking" | "available" | "unavailable"
  >("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch(VIDEO_SOURCE, { method: "HEAD", cache: "no-store", signal: controller.signal })
      .then((response) =>
        setAvailability(response.ok ? "available" : "unavailable"),
      )
      .catch(() => setAvailability("unavailable"));

    return () => controller.abort();
  }, []);

  return (
    <figure className="mx-auto w-full max-w-[560px]">
      <div className="overflow-hidden rounded-2xl border border-rule bg-charcoal p-2">
        {availability !== "available" ? (
          <div className="relative aspect-video overflow-hidden rounded-xl bg-charcoal">
            <img
              src={`${BASE}sweet-seats-final-cut-v3-poster.jpg`}
              alt=""
              aria-hidden="true"
              className="h-full w-full object-cover"
            />
            <p
              role="status"
              className="absolute inset-x-0 bottom-0 bg-background/90 px-4 py-3 text-sm text-soft"
            >
              {availability === "checking"
                ? "Checking the film preview…"
                : "The film preview isn’t available right now. Please check back soon."}
            </p>
          </div>
        ) : (
          <video
            className="aspect-video w-full rounded-xl bg-background object-contain"
            controls
            playsInline
            preload="none"
            poster={`${BASE}sweet-seats-final-cut-v3-poster.jpg`}
            aria-label="Sweet Seats short film about live music in New York and nearby"
            aria-describedby="trailer-caption"
            onError={() => setAvailability("unavailable")}
          >
            <source
              src={VIDEO_SOURCE}
              type="video/mp4"
            />
            Your browser does not support the video player.
          </video>
        )}
      </div>
      <figcaption id="trailer-caption" className="px-2 pt-3 text-sm leading-relaxed text-soft">
        A 27-second film about the kind of live-music nights Sweet Seats is being built for.
      </figcaption>
    </figure>
  );
}

const ideas = [
  ["01", "Keep your favorites close.", "Planned artist follows to help you keep up with the musicians you love, without checking every channel."],
  ["02", "Find a show that fits your night.", "Discovery focused on New York City and nearby communities, with useful artist, venue, and event details."],
  ["03", "Stay in the know.", "Planned alerts for official concert announcements, ticket on-sales, and event changes. Clear sources. Useful updates."],
];

export default function Index() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className={`${wrap} flex items-center justify-between py-6`}>
        <a href={brandNavigation.publicSite.href} className="flex min-h-11 items-center" aria-label="Sweet Seats home">
          <img src={`${BASE}sweet-seats-logo.svg`} alt="Sweet Seats home" className="h-8 w-auto sm:h-9" width="173" height="32" />
        </a>
        <a href={GH} target="_blank" rel="noopener noreferrer" className="ss-link flex min-h-11 items-center text-sm">
          Meet the founder ↗<span className="sr-only"> (opens in new tab)</span>
        </a>
      </header>

      <main>
        <section className={`${wrap} grid items-center gap-14 py-14 md:grid-cols-2 md:py-24`}>
          <div>
            <p className={eyebrow}>COMING SOON · NYC &amp; NEARBY</p>
            <h1 className="mt-6 text-[clamp(3rem,8vw,6.5rem)] font-black leading-[0.92] tracking-[-0.04em]">
              Be there
              <br />
              for the
              <br />
              <span className="text-coral">good stuff.</span>
            </h1>
            <p className="mt-8 max-w-md text-lg leading-relaxed text-soft">
              Your favorite artists. Your next great night. We’re building a simpler way to find live music around New York.
            </p>
            <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
              <a
                href={brandNavigation.discovery.href}
                className="ss-button ss-button--primary w-fit"
              >
                Explore the discovery demo →
              </a>
              <p className="text-sm text-soft">Synthetic demo available now.</p>
            </div>
            <div className="mt-10">
              <WaitlistForm />
            </div>
          </div>
          <Trailer />
        </section>

        <div className="border-y border-rule">
          <div className={`${wrap} flex flex-col gap-2 py-5 text-sm sm:flex-row sm:justify-between`}>
            <p className="font-semibold">Starting local. Thinking live.</p>
            <p className="text-soft">New York City · Nearby stages · Your kind of music</p>
          </div>
        </div>

        <section id="the-idea" className={`${wrap} grid scroll-mt-6 gap-12 py-20 md:grid-cols-2 md:py-28`} aria-labelledby="idea-h">
          <div>
            <p className={eyebrow}>THE IDEA</p>
            <h2 id="idea-h" className="mt-5 text-4xl font-black leading-[1.02] tracking-[-0.03em] sm:text-5xl">
              Finding a great show should feel easy.
            </h2>
            <p className="mt-6 max-w-md text-lg leading-relaxed text-soft">
              Concert news is everywhere. We’re working to bring the useful parts together, so a night you’d love doesn’t pass you by.
            </p>
          </div>
          <ol className="divide-y divide-rule border-y border-rule">
            {ideas.map(([n, t, d]) => (
              <li key={n} className="flex gap-6 py-7">
                <span className="font-sans text-xl font-bold text-coral">{n}</span>
                <div>
                  <h3 className="text-xl font-bold tracking-tight">{t}</h3>
                  <p className="mt-2 leading-relaxed text-soft">{d}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className={`${wrap} pb-20`}>
          <div className="flex flex-col gap-6 rounded-2xl border border-rule bg-charcoal p-8 sm:p-12 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-black tracking-tight sm:text-3xl">Still backstage. Getting ready for the good stuff.</h2>
              <p className="mt-3 text-soft">Sweet Seats is in development and isn’t available to use yet.</p>
            </div>
            <a href={GH} target="_blank" rel="noopener noreferrer" className="shrink-0 font-semibold text-coral hover:underline">
              Connect with Tim on GitHub ↗<span className="sr-only"> (opens in new tab)</span>
            </a>
          </div>
        </section>
      </main>

      <footer className="border-t border-rule">
        <div className={`${wrap} flex flex-col gap-2 py-8 text-sm text-soft sm:flex-row sm:justify-between`}>
          <p>© 2026 Sweet Seats. Built by Tim King.</p>
          <p>Independent project · NYC-area live music discovery</p>
        </div>
      </footer>
    </div>
  );
}

export { Logo };
