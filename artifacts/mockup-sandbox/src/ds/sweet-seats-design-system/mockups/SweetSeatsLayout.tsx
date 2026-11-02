import { useMemo, useState } from "react";
import { Button } from "@workspace/sweet-seats-design-system/components/ui/button";
import { Field, FieldControl, FieldHelp, FieldLabel } from "@workspace/sweet-seats-design-system/components/ui/field";
import { Link } from "@workspace/sweet-seats-design-system/components/ui/link";
import { StatusMessage } from "@workspace/sweet-seats-design-system/components/ui/status";
import sweetSeatsMusicFanLogo from "@workspace/sweet-seats-design-system/assets/sweet-seats-music-fan-logo.png";
import "./SweetSeatsLayout.css";

const nights = [
  { id: "violet-static", day: "18", month: "MAY", title: "Violet Static", artist: "Violet Static · with June Bloom", venue: "Baby's All Right", area: "Williamsburg", time: "8:00 PM · Brooklyn", records: 2 },
  { id: "soft-focus", day: "21", month: "MAY", title: "Soft Focus", artist: "Soft Focus · Mira Sol", venue: "Elsewhere — Zone One", area: "Bushwick", time: "7:30 PM · Brooklyn", records: 1 },
  { id: "paper-moons", day: "24", month: "MAY", title: "Paper Moons", artist: "Paper Moons · The Gables", venue: "Bowery Ballroom", area: "Lower East Side", time: "Doors 7:00 PM · Manhattan", records: 3 },
];

export function SweetSeatsLayout() {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return nights.filter((night) =>
      `${night.title} ${night.artist} ${night.venue} ${night.area}`.toLowerCase().includes(term),
    );
  }, [query]);

  return <main className="ss-layout" id="page-top">
    <header className="ss-top">
      <Link className="ss-wordmark" variant="plain" href="#page-top" aria-label="Sweet Seats preview home">
        <img className="ss-logo" src={sweetSeatsMusicFanLogo} alt="" />
      </Link>
      <nav className="ss-top-right" aria-label="Preview navigation">
        <span className="ss-demo">LOCAL DISCOVERY DEMO</span>
        <Link href="#source-notes">About this preview</Link>
      </nav>
    </header>

    <section className="ss-board" aria-labelledby="page-title">
      <div className="ss-board-head">
        <div>
          <p className="ss-overline">NEW YORK · LIVE MUSIC</p>
          <h1 id="page-title">Your next night<br />starts here.</h1>
        </div>
        <div className="ss-date-stamp"><strong>THE CITY, ON YOUR RADAR</strong><span>THREE SAMPLE NIGHTS</span></div>
      </div>

      <div className="ss-board-grid">
        <aside className="ss-rail" aria-label="Search and demo limits">
          <div>
            <span className="ss-rail-kicker">A LITTLE CLOSER TO THE MUSIC</span>
            <h2 className="ss-rail-title">Find the<br />good rooms.</h2>
            <p className="ss-rail-copy">Small rooms. Big nights. Find your next show, with a clear trail back to where every detail came from.</p>
          </div>
          <Field>
            <FieldLabel htmlFor="sample-search">Search these loaded examples</FieldLabel>
            <FieldControl id="sample-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Artist, venue, area" aria-describedby="sample-search-help" />
            <FieldHelp id="sample-search-help">Filters only these sample cards. It does not call the app API.</FieldHelp>
          </Field>
          <nav className="ss-rail-nav" aria-label="Preview sections">
            <Link variant="plain" href="#sample-events">All sample nights <span>{visible.length.toString().padStart(2, "0")}</span></Link>
            <Link variant="plain" href="#source-notes">Source notes <span>03</span></Link>
          </nav>
          <StatusMessage tone="warning">Synthetic demo only. No working sign-in, saved events, artist follows, alert management, ticket purchases, or live ticket links.</StatusMessage>
        </aside>

        <section className="ss-feed" id="sample-events" aria-labelledby="feed-title">
          <header className="ss-feed-head">
            <h2 id="feed-title">Coming up <span className="ss-results">{visible.length} sample {visible.length === 1 ? "night" : "nights"}</span></h2>
            <div className="ss-refresh">
              <Button variant="quiet" disabled aria-describedby="refresh-note">Refresh feed</Button>
              <p id="refresh-note">Refresh reloads stored observations only. It does not collect live events or update observation freshness.</p>
            </div>
          </header>
          <div className="ss-cards">
            {visible.length ? visible.map((night) => <article className="ss-event" key={night.id}>
              <time className="ss-date" dateTime={`2026-${night.month === "MAY" ? "05" : "01"}-${night.day}`}>
                <span>{night.month}</span><strong>{night.day}</strong>
              </time>
              <div className="ss-event-copy">
                <div className="ss-event-kicker"><b>DEMO FIXTURE</b><span>Example observation · not live</span></div>
                <h3>{night.title}</h3>
                <p className="ss-event-artist">{night.artist}</p>
                <p className="ss-event-venue">{night.venue} · {night.area}</p>
              </div>
              <div className="ss-event-side">
                <span className="ss-time">{night.time}</span>
                <span>{night.records} synthetic source {night.records === 1 ? "record" : "records"}</span>
                <Link href="#source-notes">View source notes</Link>
              </div>
            </article>) : <p className="ss-no-results">No sample nights match. Try another artist, venue, or area.</p>}
          </div>
        </section>

        <aside className="ss-aside" id="source-notes" aria-labelledby="source-title">
          <p className="ss-aside-label">BUILT ON RECEIPTS</p>
          <h2 id="source-title">Every detail<br />has a source.</h2>
          <p>This visual preview uses invented sample records. The live discovery screen reads the local API and preserves source timestamps.</p>
          <dl className="ss-source-stats">
            <div><dt>Collection status</dt><dd>DEMO FIXTURES</dd></div>
            <div><dt>Feed refresh</dt><dd>STORED SNAPSHOT</dd></div>
            <div><dt>Live source access</dt><dd>OFF</dd></div>
          </dl>
          <StatusMessage tone="warning">Ticket actions are disabled here. No live ticket links or ticket purchases are available.</StatusMessage>
        </aside>
      </div>
    </section>

    <footer className="ss-foot">
      <span>Sweet Seats · Find your next favorite night.</span>
      <span>Visual preview · Synthetic examples only</span>
    </footer>
  </main>;
}
