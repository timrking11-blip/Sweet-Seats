import { useMemo, useState } from "react";
import "./SweetSeatsLayout.css";
import sweetSeatsMusicFanLogo from "../../../../../../attached_assets/0_Sweet_Seats_Music_Fan_Logo_1793606109380.png";

const nights = [
  { id: "violet-static", day: "18", month: "MAY", status: "Just announced", title: "Violet Static", artist: "Violet Static · with June Bloom", venue: "Baby's All Right", area: "Williamsburg", time: "8:00 PM · Brooklyn", records: 2, freshness: "Observed 2h ago" },
  { id: "soft-focus", day: "21", month: "MAY", status: "On sale", title: "Soft Focus", artist: "Soft Focus · Mira Sol", venue: "Elsewhere — Zone One", area: "Bushwick", time: "7:30 PM · Brooklyn", records: 1, freshness: "Observed 4h ago" },
  { id: "paper-moons", day: "24", month: "MAY", status: "Following", title: "Paper Moons", artist: "Paper Moons · The Gables", venue: "Bowery Ballroom", area: "Lower East Side", time: "Doors 7:00 PM · Manhattan", records: 3, freshness: "Observed 5h ago" },
];

export function SweetSeatsLayout() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All nights");
  const [followed, setFollowed] = useState<string[]>(["paper-moons"]);
  const [refresh, setRefresh] = useState("Updated just now");
  const visible = useMemo(() => nights.filter((night) => {
    const textMatch = `${night.title} ${night.artist} ${night.venue} ${night.area}`.toLowerCase().includes(query.toLowerCase());
    const filterMatch = filter === "All nights" || (filter === "Following" && followed.includes(night.id)) || (filter === "Brooklyn" && night.area !== "Lower East Side");
    return textMatch && filterMatch;
  }), [filter, followed, query]);

  return <main className="ss-layout" data-ss-brand="midnight-session">
    <header className="ss-top">
      <div className="ss-wordmark"><img className="ss-logo" src={sweetSeatsMusicFanLogo} alt="Sweet Seats Music Fan" /></div>
      <div className="ss-top-right"><span className="ss-demo">LOCAL DISCOVERY DEMO</span><a className="ss-about" href="#source-notes">About this preview</a></div>
    </header>
    <section className="ss-board">
      <div className="ss-board-head">
        <div><div className="ss-overline">New York · Live music</div><h1>Your next night<br />starts here.</h1></div>
        <div className="ss-date-stamp"><strong>THE CITY, ON YOUR RADAR</strong>THREE NIGHTS TO EXPLORE</div>
      </div>
      <div className="ss-board-grid">
        <aside className="ss-rail">
          <span className="ss-rail-kicker">A LITTLE CLOSER TO THE MUSIC</span>
          <h2 className="ss-rail-title">Find the<br />good rooms.</h2>
          <p className="ss-rail-copy">Small rooms. Big nights. Find your next show, with a clear trail back to where every detail came from.</p>
          <label className="ss-search"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Artist, venue, area" aria-label="Search events" /></label>
          <p className="ss-filter-label">Browse the feed</p>
          <div className="ss-filter-list" role="group" aria-label="Filter events">
            {["All nights", "Following", "Brooklyn"].map((item) => <button key={item} className={`ss-filter ${filter === item ? "active" : ""}`} onClick={() => setFilter(item)}>{item}<span className="ss-filter-count">{item === "All nights" ? "03" : item === "Following" ? "01" : "02"}</span></button>)}
          </div>
          <div className="ss-rail-bottom"><div className="ss-permission"><div className="ss-permission-title"><span className="ss-live-dot" /> Demo data only</div><p>Invented events and venues. No live sources or notifications are active.</p></div></div>
        </aside>

        <section className="ss-feed" aria-label="Upcoming events">
          <div className="ss-feed-head"><h2>Coming up <span className="ss-results">{visible.length} nights</span></h2><button className="ss-refresh" onClick={() => setRefresh("Updated moments ago")}>↻ &nbsp;Refresh feed</button></div>
          <div className="ss-cards">
            {visible.length ? visible.map((night) => {
              const isFollowing = followed.includes(night.id);
              return <article className="ss-event" key={night.id}>
                <time className="ss-date"><span>{night.month}</span><strong>{night.day}</strong></time>
                <div className="ss-event-copy"><div className="ss-event-kicker"><b>{night.status}</b><span>{night.freshness}</span></div><h3>{night.title}</h3><p className="ss-event-artist">{night.artist}</p><p className="ss-event-venue">{night.venue} · {night.area}</p></div>
                <div className="ss-event-side"><span className="ss-time">{night.time}</span><button className={`ss-follow ${isFollowing ? "following" : ""}`} onClick={() => setFollowed((current) => isFollowing ? current.filter((id) => id !== night.id) : [...current, night.id])}>{isFollowing ? "Following ✓" : "Follow night"}</button><a className="ss-evidence-link" href="#source-notes">{night.records} source {night.records === 1 ? "record" : "records"} ↗</a></div>
              </article>;
            }) : <div className="ss-no-results">No nights match that search. Try another artist or neighborhood.</div>}
          </div>
        </section>

        <aside className="ss-aside" id="source-notes">
          <p className="ss-aside-label">Built on receipts</p>
          <h3>Every detail<br />has a source.</h3>
          <p>This preview follows synthetic source records through permission checks, event matching, and the discovery feed.</p>
          <div className="ss-aside-rule" />
          <div className="ss-source-stat"><span>Collection status</span><strong>DEMO FIXTURES</strong></div>
          <div className="ss-source-stat"><span>Feed refresh</span><strong>{refresh.toUpperCase()}</strong></div>
          <div className="ss-source-stat"><span>Live source access</span><strong>OFF</strong></div>
          <div className="ss-aside-note">Ticket pricing and buy/wait advice need separately licensed data. No ticket links in this demo.</div>
        </aside>
      </div>
    </section>
    <footer className="ss-foot"><span>Sweet Seats · Find your next favorite night.</span><span>Discovery first&nbsp; · &nbsp;Synthetic data only</span></footer>
  </main>;
}
