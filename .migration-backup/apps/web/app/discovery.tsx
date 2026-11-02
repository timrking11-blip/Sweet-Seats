"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export type DiscoveryEvent = {
  event_id: string;
  title: string;
  venue: { venue_id: string; name: string; neighborhood: string; timezone: string };
  performers: { artist_id: string; name: string; role: string; billing_order: number }[];
  starts_at: string | null;
  local_date: string;
  timezone: string;
  time_tba: boolean;
  status: "scheduled" | "rescheduled" | "postponed" | "cancelled" | "unknown";
  observed_at: string;
  available_at: string;
  fresh_until: string;
  stale: boolean;
  sources: { source_id: string; source_record_id: string; source_url: string; name: string; observed_at: string; available_at: string }[];
  ticket_url: null;
  ticket_notice: string;
};

export type Feed = {
  mode: "synthetic";
  status: "ready" | "empty" | "partial" | "unavailable" | "blocked" | "review_required";
  review_count: number;
  unresolved: { source_record_id: string; title: string; reason: string }[];
  pagination: { limit: number; offset: number; total: number; next_offset: number | null };
  events: DiscoveryEvent[];
  collections: { name: string; status: string; finished_at: string; item_count: number }[];
};

// "missing" (404) means absent or withheld from display; it is not a provider failure.
export type Remote<T> = { state: "loading" } | { state: "error" } | { state: "missing" } | { state: "ready"; data: T };

function useDiscovery<T>(path: string) {
  const [result, setResult] = useState<Remote<T>>({ state: "loading" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setResult({ state: "loading" });
    const timeout = setTimeout(() => controller.abort(), 8000);
    fetch(`/api/discovery/${path}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (response.status === 404) {
          if (active) setResult({ state: "missing" });
          return;
        }
        if (!response.ok) throw new Error("unavailable");
        const data = await response.json();
        if (data.mode !== "synthetic") throw new Error("unexpected_mode");
        if (active) setResult({ state: "ready", data });
      })
      .catch(() => { if (active) setResult({ state: "error" }); })
      .finally(() => clearTimeout(timeout));
    return () => { active = false; controller.abort(); clearTimeout(timeout); };
  }, [path, revision]);
  return { result, retry: () => setRevision((value) => value + 1) };
}

export function observedTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    timeZone: "America/New_York", timeZoneName: "short",
  }).format(new Date(value));
}

export function eventTime(event: DiscoveryEvent) {
  return event.starts_at ? new Intl.DateTimeFormat("en-US", {
    hour: "numeric", minute: "2-digit", timeZone: event.timezone, timeZoneName: "short",
  }).format(new Date(event.starts_at)) : "Time to be announced";
}

function DateBlock({ event }: { event: DiscoveryEvent }) {
  const day = new Date(`${event.local_date}T12:00:00Z`);
  return <time className="date-block" dateTime={event.local_date}>
    <span>{day.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" }).toUpperCase()}</span>
    <strong>{event.local_date.slice(-2)}</strong>
  </time>;
}

export function DiscoveryFeed() {
  const [offset, setOffset] = useState(0);
  const { result, retry } = useDiscovery<Feed>(`events?limit=100&offset=${offset}`);
  return <DiscoveryFeedView result={result} retry={retry} offset={offset} setOffset={setOffset} />;
}

export function DiscoveryFeedView({ result, retry, offset = 0, setOffset = () => {} }: {
  result: Remote<Feed>; retry: () => void; offset?: number; setOffset?: (offset: number) => void;
}) {
  const [query, setQuery] = useState("");
  if (result.state === "loading") return <div className="feed-state" role="status" aria-busy="true">Loading the local event feed…</div>;
  if (result.state !== "ready") return <Failure retry={retry} />;
  const { data } = result;
  const matches = data.events.filter((event) =>
    [event.title, event.venue.name, event.venue.neighborhood, ...event.performers.map((p) => p.name)]
      .join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  return <>
    <div className="feed-tools">
      <label htmlFor="event-search">Find an artist, venue, or neighborhood on this page
        <input id="event-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Try Violet Static or Brooklyn" />
      </label>
      <button className="secondary" onClick={retry}>Refresh feed</button>
    </div>
    {data.status === "partial" && <p className="data-warning" role="status">A source failed. Previously observed events remain available; their timestamps have not been refreshed.</p>}
    {data.status === "unavailable" && <p className="data-warning" role="alert">Source unavailable. This is a collection failure, not evidence of no events or sold-out tickets.</p>}
    {data.status === "blocked" && <p className="data-warning" role="alert">Events are withheld because source permissions do not allow display or retention.</p>}
    {data.review_count > 0 && <p className="data-warning" role="status">{data.review_count} source record(s) or event(s) withheld for unresolved identities or conflicting facts. Matching needs review.</p>}
    {data.unresolved.length > 0 && <details className="collection-details"><summary>Unresolved identities</summary>
      <ul>{data.unresolved.map((record) => <li key={record.source_record_id}>{record.title}: identity crosswalk needs review; no match was guessed.</li>)}</ul>
    </details>}
    <p className="result-count" role="status">{matches.length} demo {matches.length === 1 ? "night" : "nights"} · NYC area</p>
    {matches.length === 0 && !["unavailable", "blocked", "review_required"].includes(data.status) && <div className="feed-state">
      <h3>{query ? "Nothing matches this search." : "No events returned."}</h3>
      <p>{query ? "Try another artist, venue, or neighborhood." : "Collection succeeded without events. That does not mean tickets are sold out."}</p>
    </div>}
    <div className="event-grid">
      {matches.map((event, index) => <article className={`event-card ${["violet", "coral", "gold"][index % 3]}`} key={event.event_id}>
        <div className="event-glow" aria-hidden="true" />
        <header><span className="event-status">{event.status}</span><span className={`freshness ${event.stale ? "stale" : ""}`}>{event.stale ? "Stale observation" : "Recent observation"}</span></header>
        <div className="event-main">
          <DateBlock event={event} />
          <div><h3><Link href={`/events/${event.event_id}`}>{event.title}</Link></h3>
            <p>{event.performers.map((artist) => artist.name).join(" · ")}</p>
            <p>{event.venue.name}</p><p className="muted">{event.venue.neighborhood} · {eventTime(event)}</p></div>
        </div>
        <div className="event-evidence"><span>{event.sources.length} synthetic source {event.sources.length === 1 ? "record" : "records"}</span>
          <time dateTime={event.observed_at}>Observed {observedTime(event.observed_at)}</time>
          <Link href={`/events/${event.event_id}`}>Explore this night <span aria-hidden="true">↗</span></Link></div>
      </article>)}
    </div>
    <nav aria-label="Event pages" className="feed-tools">
      <button className="secondary" disabled={offset === 0} onClick={() => { setQuery(""); setOffset(Math.max(0, offset - 100)); }}>Previous page</button>
      <span>{data.pagination.total} total demo events</span>
      <button className="secondary" disabled={data.pagination.next_offset === null} onClick={() => { setQuery(""); setOffset(data.pagination.next_offset ?? 0); }}>Next page</button>
    </nav>
    <details className="collection-details"><summary>Source collection results</summary>
      <ul>{data.collections.map((collection, i) => <li key={i}>{collection.name}: {collection.status} · {collection.item_count} records · {observedTime(collection.finished_at)}</li>)}</ul>
    </details>
  </>;
}

function Failure({ retry }: { retry: () => void }) {
  return <div className="feed-state" role="alert"><h3>Discovery is unavailable.</h3>
    <p>The local API or fixture store could not be read. We cannot infer event availability from this failure.</p>
    <button className="secondary" onClick={retry}>Try again</button></div>;
}

export function EventDetail({ eventId }: { eventId: string }) {
  const { result, retry } = useDiscovery<{ mode: "synthetic"; event: DiscoveryEvent }>(`events/${encodeURIComponent(eventId)}`);
  if (result.state === "loading") return <div className="feed-state" role="status">Loading event details…</div>;
  if (result.state === "missing") return <div className="feed-state" role="status"><h1>This event isn&apos;t available.</h1>
    <p>It doesn&apos;t exist, or its sources don&apos;t currently permit display. This says nothing about ticket availability.</p>
    <Link className="secondary button-link" href="/#discover-title">Back to all events</Link></div>;
  if (result.state === "error") return <Failure retry={retry} />;
  const event = result.data.event;
  return <article className="event-detail">
    <p className="eyebrow">SYNTHETIC EVENT · {event.status.toUpperCase()}</p>
    <h1>{event.title}</h1>
    <p className="detail-location">{event.venue.name} · {event.venue.neighborhood}</p>
    <p><time dateTime={event.local_date}>{event.local_date}</time> · {eventTime(event)}</p>
    <p className={`data-warning ${event.stale ? "" : "recent"}`}>{event.stale ? "Stale observation. Recheck an official source before making plans." : "Recent observation under the demo’s 24-hour freshness rule."}</p>
    <section aria-labelledby="lineup-title"><h2 id="lineup-title">The lineup</h2>
      <ul className="lineup">{event.performers.map((artist) => <li key={`${artist.artist_id}:${artist.role}`}><strong>{artist.name}</strong><span>{artist.role}</span></li>)}</ul>
    </section>
    <section aria-labelledby="sources-title"><h2 id="sources-title">The source trail</h2>
      <p>Invented calendars and artists for local testing. These URLs are reserved placeholders, not live announcements.</p>
      {event.sources.map((source) => <div className="source-record" key={source.source_record_id}>
        <h3>{source.name}</h3><p className="source-url">{source.source_url}</p>
        <p>Observed <time dateTime={source.observed_at}>{observedTime(source.observed_at)}</time></p>
        <p>Available to Sweet Seats <time dateTime={source.available_at}>{observedTime(source.available_at)}</time></p>
      </div>)}
    </section>
    <section><h2>Tickets</h2><p>{event.ticket_notice} Official ticket links arrive with a permitted live source.</p>
      <button className="secondary" disabled>No ticket link in this demo</button></section>
  </article>;
}

