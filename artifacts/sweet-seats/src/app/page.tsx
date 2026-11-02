
import { DiscoveryFeed } from "./discovery";
import DemoNotice from "./demo-notice";

export default function Home() {
  return <main id="main-content">
    <a className="skip-link" href="#discover-title">Skip to events</a>
    <nav className="topbar" aria-label="Primary navigation">
      <a className="brand" href="/" aria-label="Sweet Seats home"><span className="brand-mark">S</span><span>sweet seats</span></a>
      <div className="nav-actions"><span className="demo-label">LOCAL DISCOVERY DEMO</span><a className="text-button" href="/coming-soon/">About Sweet Seats</a></div>
    </nav>
    <section className="hero" id="top">
      <div className="hero-copy"><p className="eyebrow">NEW YORK · LIVE MUSIC</p>
        <h1>Catch the nights<br />you&apos;d hate to miss.</h1>
        <p className="hero-text">Small rooms. Big nights. Find your next show, with a clear trail back to where every detail came from.</p>
        <div className="hero-actions"><a className="primary button-link" href="#discover-title">Explore the demo <span aria-hidden="true">↗</span></a>
          <a className="secondary button-link" href="#about-demo">About this preview</a></div>
      </div>
      <div className="hero-art" aria-hidden="true"><div className="orb orb-one" /><div className="orb orb-two" /><div className="orb orb-three" />
        <div className="ticket-fragment ticket-top">YOUR CITY<br /><strong>LIVE</strong></div>
        <div className="ticket-fragment ticket-bottom">NEXT UP<br /><strong>YOUR NIGHT</strong></div>
        <p className="art-caption">A little closer to the music.</p></div>
    </section>
    <section className="signal-strip" aria-label="Demo data notice"><span className="signal-dot" aria-hidden="true" />
      <span>Invented events, artists, and venues. No live sources or notifications are active.</span></section>
    <section className="discover" aria-labelledby="discover-title"><div className="section-heading"><div>
      <p className="eyebrow">THE CITY, ON YOUR RADAR</p><h2 id="discover-title" tabIndex={-1}>A few nights to explore</h2></div></div>
      <DemoNotice />
      <DiscoveryFeed />
    </section>
    <section className="promise" id="about-demo"><div><p className="eyebrow">BUILT ON RECEIPTS</p><h2>Every detail<br />has a source.</h2></div>
      <div className="promise-copy"><p>This local preview follows synthetic source records through permission checks, event matching, storage, and the event feed.</p>
        <p>Artist follows, saved events, and durable alerts are next. Ticket pricing and buy/wait advice require separately licensed data and validation.</p></div></section>
    <footer><span>Sweet Seats · Find your next favorite night.</span><span>Demo data only · Discovery first</span></footer>
  </main>;
}
