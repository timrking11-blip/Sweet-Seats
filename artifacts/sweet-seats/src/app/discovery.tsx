
import { useEffect, useState } from "react";
import { Button } from "@workspace/sweet-seats-design-system/components/ui/button";
import { Field, FieldControl, FieldHelp, FieldLabel } from "@workspace/sweet-seats-design-system/components/ui/field";
import { Link } from "@workspace/sweet-seats-design-system/components/ui/link";
import { StatusMessage } from "@workspace/sweet-seats-design-system/components/ui/status";
import DemoNotice from "./demo-notice";

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
  return <time className="ss-date-block" dateTime={event.local_date}>
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
  const data = result.state === "ready" ? result.data : undefined;
  const matches = (data?.events ?? []).filter((event) =>
    [event.title, event.venue.name, event.venue.neighborhood, ...event.performers.map((p) => p.name)]
      .join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  const pageEventCount = data?.events.length ?? 0;
  const sourceCount = data?.events.reduce((total, event) => total + event.sources.length, 0) ?? 0;
  const loading = result.state === "loading";

  return <>
    <div className="ss-disclosure-band"><DemoNotice /></div>
    <div className="ss-board-grid">
    <aside className="ss-rail" aria-label="Browse discovery">
      <div>
        <span className="ss-rail-kicker">A LITTLE CLOSER TO THE MUSIC</span>
        <h2 className="ss-rail-title">Find the<br />good rooms.</h2>
        <p className="ss-rail-copy">Small rooms. Big nights. Find your next show, with a clear trail back to where every detail came from.</p>
      </div>
      <Field>
        <FieldLabel htmlFor="event-search">Find an artist, venue, or neighborhood on this page</FieldLabel>
        <FieldControl id="event-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try an artist or place" disabled={!data || loading} aria-describedby="event-search-help" />
        <FieldHelp id="event-search-help">Searches only the events on this loaded page.</FieldHelp>
      </Field>
      <nav className="ss-browse" aria-label="Discovery sections">
        <span className="ss-filter-label">Browse the feed</span>
        <Link className="ss-browse-link" variant="plain" href="#discover-title"><span>All loaded nights</span><span>{pageEventCount.toString().padStart(2, "0")}</span></Link>
        <Link className="ss-browse-link" variant="plain" href="#source-notes"><span>Source records</span><span>{sourceCount.toString().padStart(2, "0")}</span></Link>
      </nav>
    </aside>

    <section className="ss-feed" aria-labelledby="discover-title">
      <header className="ss-feed-head">
        <div>
          <p className="ss-overline">THE CITY, ON YOUR RADAR</p>
          <h2 id="discover-title" tabIndex={-1}>Coming up <span className="ss-feed-count">{data ? `${matches.length} on this page` : "Local event feed"}</span></h2>
        </div>
        <div className="ss-refresh-control">
          <Button variant="quiet" aria-describedby="refresh-note" onClick={retry} disabled={loading}>Refresh feed</Button>
          <p id="refresh-note">Reloads stored observations only. Does not collect live events or update observation freshness.</p>
        </div>
      </header>

      <div className="ss-feed-content">
        {loading && <div className="ss-feed-state" role="status" aria-busy="true">Loading the local event feed…</div>}
        {result.state === "missing" && <StatusMessage tone="warning">The stored demo feed is not available for display. This is not evidence that no events exist.</StatusMessage>}
        {result.state === "error" && <Failure retry={retry} />}
        {data?.status === "partial" && <StatusMessage tone="warning">A source failed. Previously observed events remain available; their timestamps have not been refreshed.</StatusMessage>}
        {data?.status === "unavailable" && <StatusMessage tone="error">Source unavailable. This is a collection failure, not evidence of no events or sold-out tickets.</StatusMessage>}
        {data?.status === "blocked" && <StatusMessage tone="error">Events are withheld because source permissions do not allow display or retention.</StatusMessage>}
        {data && data.review_count > 0 && <StatusMessage tone="warning">{data.review_count} source record(s) or event(s) withheld for unresolved identities or conflicting facts. Matching needs review.</StatusMessage>}
        {data && data.unresolved.length > 0 && <details className="ss-collection-details"><summary>Unresolved identities</summary>
          <ul>{data.unresolved.map((record) => <li key={record.source_record_id}>{record.title}: identity crosswalk needs review; no match was guessed.</li>)}</ul>
        </details>}
        {data && matches.length === 0 && !["unavailable", "blocked", "review_required"].includes(data.status) && <div className="ss-feed-state">
          <h3>{query ? "Nothing matches this search." : "No events returned."}</h3>
          <p>{query ? "Try another artist, venue, or neighborhood on this page." : "Collection succeeded without events. That does not mean tickets are sold out."}</p>
        </div>}
        {data && matches.map((event) => <article className="ss-event" key={event.event_id}>
          <DateBlock event={event} />
          <div className="ss-event-copy">
            <div className="ss-event-kicker">
              <span className="ss-event-status">{event.status.replaceAll("_", " ")}</span>
              <span className={event.stale ? "ss-stale" : "ss-fresh"}>{event.stale ? "Stale observation" : "Recent observation"}</span>
            </div>
            <h3><Link variant="heading" href={`/events/${encodeURIComponent(event.event_id)}`}>{event.title}</Link></h3>
            <p className="ss-event-artists">{event.performers.map((artist) => artist.name).join(" · ")}</p>
            <p className="ss-event-place">{event.venue.name} · {event.venue.neighborhood}</p>
            <p className="ss-event-time">{eventTime(event)}</p>
          </div>
          <div className="ss-event-side">
            <time dateTime={event.observed_at}>Observed {observedTime(event.observed_at)}</time>
            <span>{event.sources.length} synthetic source {event.sources.length === 1 ? "record" : "records"}</span>
            <Link href={`/events/${encodeURIComponent(event.event_id)}`}>Explore this night <span aria-hidden="true">↗</span></Link>
          </div>
        </article>)}
        {data && <nav aria-label="Event pages" className="ss-pagination">
          <Button variant="quiet" disabled={offset === 0} onClick={() => { setQuery(""); setOffset(Math.max(0, offset - 100)); }}>Previous page</Button>
          <span>{pageEventCount} loaded · {data.pagination.total} total demo events</span>
          <Button variant="quiet" disabled={data.pagination.next_offset === null} onClick={() => { setQuery(""); setOffset(data.pagination.next_offset ?? 0); }}>Next page</Button>
        </nav>}
        {data && <details className="ss-collection-details"><summary>Source collection results</summary>
          <ul>{data.collections.map((collection, index) => <li key={`${collection.name}:${index}`}>{collection.name}: {collection.status} · {collection.item_count} records · {observedTime(collection.finished_at)}</li>)}</ul>
        </details>}
      </div>
    </section>

    <aside className="ss-aside" id="source-notes" aria-labelledby="source-title">
      <p className="ss-aside-label">BUILT ON RECEIPTS</p>
      <h2 id="source-title">Every detail has a source.</h2>
      <p>This local preview follows synthetic source records through permission checks, event matching, storage, and the discovery feed.</p>
      <dl className="ss-source-stats">
        <div><dt>Collection status</dt><dd>{data?.status.toUpperCase() ?? (loading ? "LOADING" : "UNAVAILABLE")}</dd></div>
        <div><dt>Events on this page</dt><dd>{pageEventCount.toString().padStart(2, "0")}</dd></div>
        <div><dt>Live source access</dt><dd>OFF</dd></div>
      </dl>
      <StatusMessage tone="warning">Ticket actions are disabled in this demo. No live ticket links are active.</StatusMessage>
    </aside>
    </div>
  </>;
}

function Failure({ retry }: { retry: () => void }) {
  return <div className="ss-feed-state">
    <StatusMessage tone="error">Discovery is unavailable. The local API or fixture store could not be read. We cannot infer event availability from this failure.</StatusMessage>
    <Button variant="quiet" onClick={retry}>Try again</Button>
  </div>;
}

export function EventDetail({ eventId }: { eventId: string }) {
  const { result, retry } = useDiscovery<{ mode: "synthetic"; event: DiscoveryEvent }>(`events/${encodeURIComponent(eventId)}`);
  if (result.state === "loading") return <div className="ss-feed-state" role="status" aria-busy="true">Loading event details…</div>;
  if (result.state === "missing") return <article className="ss-event-detail">
    <StatusMessage tone="warning">This event is not available for display. It may not exist, or its sources may not currently permit display. This says nothing about ticket availability.</StatusMessage>
    <Link variant="quiet" href="/#discover-title">Back to all events</Link>
  </article>;
  if (result.state === "error") return <Failure retry={retry} />;
  const event = result.data.event;
  return <article className="ss-event-detail">
    <p className="ss-overline">SYNTHETIC EVENT · {event.status.toUpperCase()}</p>
    <h1>{event.title}</h1>
    <p className="ss-detail-location">{event.venue.name} · {event.venue.neighborhood}</p>
    <p><time dateTime={event.local_date}>{event.local_date}</time> · {eventTime(event)}</p>
    <StatusMessage tone={event.stale ? "warning" : "success"}>{event.stale ? "Stale observation. Recheck an official source before making plans." : "Recent observation under the demo’s 24-hour freshness rule."}</StatusMessage>
    <section aria-labelledby="lineup-title"><h2 id="lineup-title">The lineup</h2>
      <ul className="ss-lineup">{event.performers.map((artist) => <li key={`${artist.artist_id}:${artist.role}`}><strong>{artist.name}</strong><span>{artist.role}</span></li>)}</ul>
    </section>
    <section aria-labelledby="sources-title"><h2 id="sources-title">The source trail</h2>
      <p>Invented calendars and artists for local testing. These URLs are reserved placeholders, not live announcements.</p>
      {event.sources.map((source) => <div className="ss-source-record" key={source.source_record_id}>
        <h3>{source.name}</h3><p className="source-url">{source.source_url}</p>
        <p>Observed <time dateTime={source.observed_at}>{observedTime(source.observed_at)}</time></p>
        <p>Available to Sweet Seats <time dateTime={source.available_at}>{observedTime(source.available_at)}</time></p>
      </div>)}
    </section>
    <section><h2>Tickets</h2><p>{event.ticket_notice} No live ticket links or ticket purchases are available in this demo.</p>
      <Button variant="quiet" disabled>No ticket link in this demo</Button>
    </section>
  </article>;
}

