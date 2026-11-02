import { useMemo, useState } from "react";
import "./SweetSeatsItinerary.css";

const nights = [
  { id: "violet-static", day: "18", month: "MAY", status: "Just announced", title: "Violet Static", artist: "Violet Static · with June Bloom", venue: "Baby's All Right", area: "Williamsburg", time: "8:00 PM · Brooklyn", records: 2, freshness: "Observed 2h ago" },
  { id: "soft-focus", day: "21", month: "MAY", status: "On sale", title: "Soft Focus", artist: "Soft Focus · Mira Sol", venue: "Elsewhere — Zone One", area: "Bushwick", time: "7:30 PM · Brooklyn", records: 1, freshness: "Observed 4h ago" },
  { id: "paper-moons", day: "24", month: "MAY", status: "Following", title: "Paper Moons", artist: "Paper Moons · The Gables", venue: "Bowery Ballroom", area: "Lower East Side", time: "Doors 7:00 PM · Manhattan", records: 3, freshness: "Observed 5h ago" },
];

export function SweetSeatsItinerary() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All nights");
  const [followed, setFollowed] = useState<string[]>(["paper-moons"]);
  const [refresh, setRefresh] = useState("Updated just now");
  const visible = useMemo(() => nights.filter((night) => {
    const textMatch = `${night.title} ${night.artist} ${night.venue} ${night.area}`.toLowerCase().includes(query.toLowerCase());
    const filterMatch = filter === "All nights" || (filter === "Following" && followed.includes(night.id)) || (filter === "Brooklyn" && night.area !== "Lower East Side");
    return textMatch && filterMatch;
  }), [filter, followed, query]);

  return <main className="si-shell">
    <header className="si-nav">
      <div className="si-brand"><span className="si-brand-mark">S</span><span>sweet seats</span></div>
      <div className="si-nav-meta"><span className="si-demo-label"><i /> LOCAL DISCOVERY DEMO</span><a href="#si-sources">About this preview <span aria-hidden="true">↗</span></a></div>
    </header>

    <div className="si-page">
      <section className="si-intro">
        <div className="si-intro-copy">
          <p className="si-eyebrow">NEW YORK <span>·</span> LIVE MUSIC</p>
          <h1>Good nights,<br /><em>lined up.</em></h1>
          <p className="si-deck">A little city plan for the shows worth getting out for.</p>
        </div>
        <div className="si-intro-note"><span className="si-note-index">01 — 03</span><span>THREE NIGHTS<br />ON YOUR RADAR</span></div>
      </section>

      <section className="si-itinerary" aria-label="Upcoming events">
        <div className="si-itinerary-head">
          <div><p className="si-eyebrow">THE ITINERARY</p><h2>Coming up <span>{visible.length} nights</span></h2></div>
          <button className="si-refresh" onClick={() => setRefresh("Updated moments ago")} aria-label="Refresh feed"><span aria-hidden="true">↻</span> Refresh feed</button>
        </div>
        <div className="si-controls">
          <label className="si-search">
            <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.8" cy="8.8" r="5.8" /><path d="m13.2 13.2 4 4" /></svg>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Artist, venue, area" aria-label="Search events" />
          </label>
          <div className="si-filters" role="group" aria-label="Filter events">
            {["All nights", "Following", "Brooklyn"].map((item) => <button key={item} className={filter === item ? "selected" : ""} onClick={() => setFilter(item)}>{item}</button>)}
          </div>
        </div>

        <div className="si-list">
          <div className="si-spine" aria-hidden="true" />
          {visible.length ? visible.map((night, index) => {
            const isFollowing = followed.includes(night.id);
            return <article className={`si-event si-event-${index + 1}`} key={night.id}>
              <time className="si-date"><span>{night.month}</span><strong>{night.day}</strong></time>
              <div className="si-node" aria-hidden="true" />
              <div className="si-event-card">
                <div className="si-event-main">
                  <div className="si-event-meta"><span className="si-status">{night.status}</span><span>{night.freshness}</span></div>
                  <h3>{night.title}</h3>
                  <p className="si-artist">{night.artist}</p>
                  <p className="si-venue"><span aria-hidden="true">⌖</span> {night.venue} <i>·</i> {night.area}</p>
                </div>
                <div className="si-event-actions">
                  <span className="si-time">{night.time}</span>
                  <button className={`si-follow ${isFollowing ? "is-following" : ""}`} onClick={() => setFollowed((current) => isFollowing ? current.filter((id) => id !== night.id) : [...current, night.id])}>{isFollowing ? "Following ✓" : "Follow night"}</button>
                  <a href="#si-sources">{night.records} source {night.records === 1 ? "record" : "records"} <span aria-hidden="true">↗</span></a>
                </div>
              </div>
            </article>;
          }) : <div className="si-empty"><span className="si-empty-mark">⌕</span><strong>No nights on this route.</strong><p>Try another artist or neighborhood.</p></div>}
        </div>
        <div className="si-itinerary-foot"><span>Dates are the destination.</span><span>Scroll for source notes <b>↓</b></span></div>
      </section>

      <section className="si-source-panel" id="si-sources">
        <div className="si-source-heading"><p className="si-eyebrow">BUILT ON RECEIPTS</p><h2>Every detail<br />has a source.</h2><p>This preview follows synthetic source records through permission checks, event matching, and the discovery feed.</p></div>
        <div className="si-source-facts">
          <div><span>Collection status</span><strong>DEMO FIXTURES</strong></div>
          <div><span>Feed refresh</span><strong>{refresh.toUpperCase()}</strong></div>
          <div><span>Live source access</span><strong><i /> OFF</strong></div>
        </div>
        <aside className="si-source-note"><span className="si-note-dash">NOTE</span><p>Ticket pricing and buy/wait advice need separately licensed data. No ticket links in this demo.</p></aside>
      </section>
      <footer className="si-footer"><span>Sweet Seats <i>·</i> Find your next favorite night.</span><span>Discovery first <i>·</i> Synthetic data only</span></footer>
    </div>
  </main>;
}
