import { useState } from "react";
import { brandNavigation } from "../../../../lib/sweet-seats-brand/foundation";

const palette = [
  ["Stage navy", "--ss-bg", "Page foundation"],
  ["House cream", "--ss-text", "Primary reading"],
  ["Coral cue", "--ss-primary", "Action / on-navy label"],
  ["Sea-glass", "--ss-accent", "Links / focus"],
  ["Deep house", "--ss-surface", "Raised surfaces"],
  ["Quiet text", "--ss-muted", "Secondary reading"],
];

export default function StyleGuide() {
  const [message, setMessage] = useState("Examples are local only. Nothing is submitted.");
  return <main className="style-guide" id="main-content">
    <header className="guide-header">
      <a className="brand" href="/" aria-label="Sweet Seats discovery home"><span className="brand-mark" aria-hidden="true">S</span><span>sweet seats</span></a>
      <span className="guide-kicker">DEVELOPMENT STYLE GUIDE</span>
    </header>
    <section className="guide-intro">
      <p className="eyebrow">MIDNIGHT SESSION · FOUNDATION A</p>
      <h1>One shared<br />house style.</h1>
      <p>Common tokens, native controls, and accessible states for the discovery demo and the public landing page.</p>
      <nav className="guide-nav" aria-label="Shared site navigation">
        <a className="ss-button ss-button--primary" href={brandNavigation.discovery.href}>{brandNavigation.discovery.label}</a>
        <a className="ss-button ss-button--quiet" href={brandNavigation.publicSite.href}>{brandNavigation.publicSite.label}</a>
      </nav>
    </section>

    <section className="guide-section" aria-labelledby="palette-title">
      <div className="guide-heading"><p className="eyebrow">01 · COLOR</p><h2 id="palette-title">House lights, clearly called.</h2></div>
      <div className="guide-swatches">
        {palette.map(([name, token, use]) => <article className="guide-swatch" key={token} style={{ backgroundColor: `var(${token})` }}>
          <span className="swatch-chip">{name}</span>
          <span className="swatch-detail">{token}<br />{use}</span>
        </article>)}
      </div>
      <p className="guide-note">Palette values are sourced directly from the shared brand tokens; both sites consume this same source.</p>
    </section>

    <section className="guide-section guide-type" aria-labelledby="type-title">
      <div className="guide-heading"><p className="eyebrow">02 · TYPE</p><h2 id="type-title">Bold, familiar, readable.</h2></div>
      <div className="type-specimen"><span className="type-label">DISPLAY · SYSTEM SANS</span><p>Make room<br />for the music.</p></div>
      <div className="type-meta"><span>Body / ui-sans-serif system stack</span><span>Headlines / same family, heavier weight</span><span>Minimum body copy / 16px</span></div>
    </section>

    <section className="guide-section guide-marks" aria-labelledby="marks-title">
      <div className="guide-heading"><p className="eyebrow">03 · CURRENT MARKS</p><h2 id="marks-title">Provisional, not final.</h2></div>
      <div className="mark-samples">
        <div className="mark-sample"><span className="brand-mark" aria-hidden="true">S</span><p><strong>Discovery letter mark</strong><br />Existing demo mark, provisional.</p></div>
        <div className="mark-sample"><img className="guide-existing-logo" src={`${brandNavigation.publicSite.href}sweet-seats-logo.svg`} alt="Existing landing-page ticket-star logo, provisional" /><p><strong>Landing-page mark</strong><br />Existing asset retained as-is; provisional.</p></div>
      </div>
      <p className="guide-note">The approved headphone-seat logo has not been supplied. Existing landing-page artwork is retained as-is; no replacement logo or new media is being introduced.</p>
    </section>

    <section className="guide-section" aria-labelledby="controls-title">
      <div className="guide-heading"><p className="eyebrow">04 · CONTROLS &amp; STATES</p><h2 id="controls-title">Room to tap. Focus to find.</h2></div>
      <div className="guide-controls">
        <div className="guide-control-block">
          <h3>Navigation and actions</h3>
          <div className="guide-actions">
            <a className="ss-button ss-button--primary" href="#form-examples">Primary link</a>
            <button className="ss-button ss-button--quiet" type="button" onClick={() => setMessage("Example action acknowledged locally. No form was submitted.")}>Secondary action</button>
            <button className="ss-button" type="button" disabled>Disabled action</button>
          </div>
          <p className="guide-note" aria-live="polite">{message}</p>
        </div>
        <div className="guide-control-block" id="form-examples">
          <h3>Form-field examples</h3>
          <div className="guide-field">
            <label className="ss-label" htmlFor="guide-email">Email address</label>
            <input className="ss-control" id="guide-email" type="email" placeholder="you@example.com" aria-describedby="guide-email-help" />
            <p className="ss-help" id="guide-email-help">An example field only; there is no connected waitlist or submission.</p>
          </div>
          <div className="guide-field">
            <label className="ss-label" htmlFor="guide-invalid">Example with an error</label>
            <input className="ss-control" id="guide-invalid" type="text" aria-invalid="true" aria-describedby="guide-invalid-error" defaultValue="Not an email address" />
            <p className="guide-error" id="guide-invalid-error">Enter a valid email address.</p>
          </div>
        </div>
      </div>
      <div className="guide-statuses">
        <p className="ss-status" data-tone="warning" role="status"><strong>Warning:</strong> Some source observations may be older than expected.</p>
        <p className="ss-status" data-tone="error" role="alert"><strong>Error:</strong> Discovery is unavailable. No event availability is inferred.</p>
        <p className="ss-status" data-tone="success" role="status"><strong>Recent:</strong> Observation is inside the demo freshness window.</p>
      </div>
    </section>

    <footer className="guide-footer"><span>Sweet Seats · Shared web foundation</span><a className="ss-link" href={brandNavigation.discovery.href}>Back to discovery</a></footer>
  </main>;
}
