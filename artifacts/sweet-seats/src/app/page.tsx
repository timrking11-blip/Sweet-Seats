import { DiscoveryFeed } from "./discovery";
import { Link } from "@workspace/sweet-seats-design-system/components/ui/link";
import { SiteHeader } from "./site-header";

export default function Home() {
  return <main className="ss-app ss-home" id="main-content">
    <Link className="ss-skip" variant="plain" href="#discover-title">Skip to nights</Link>
    <SiteHeader secondaryHref="#source-notes" secondaryLabel="About this preview" />
    <section className="ss-board" id="top" aria-labelledby="home-title">
      <div className="ss-board-head">
        <div>
          <p className="ss-overline">NEW YORK · LIVE MUSIC</p>
          <h1 id="home-title">Your next night starts here.</h1>
          <p className="ss-board-intro">Small rooms. Big nights. Find your next show, with a clear trail back to where every detail came from.</p>
        </div>
        <div className="ss-date-stamp"><strong>THE CITY, ON YOUR RADAR</strong><span>LOCAL DISCOVERY DEMO</span></div>
      </div>
      <DiscoveryFeed />
    </section>
    <footer className="ss-foot"><span>Sweet Seats · Find your next favorite night.</span><Link variant="plain" href="/coming-soon/">About Sweet Seats</Link><span>Synthetic demo only · Discovery first</span></footer>
  </main>;
}
