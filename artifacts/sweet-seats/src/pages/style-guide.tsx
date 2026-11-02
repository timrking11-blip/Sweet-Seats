import { useState } from "react";
import { Button } from "@workspace/sweet-seats-design-system/components/ui/button";
import { Field, FieldControl, FieldHelp, FieldLabel } from "@workspace/sweet-seats-design-system/components/ui/field";
import { Link } from "@workspace/sweet-seats-design-system/components/ui/link";
import { StatusMessage } from "@workspace/sweet-seats-design-system/components/ui/status";
import { brandNavigation } from "../../../../lib/sweet-seats-brand/foundation";
import { SiteHeader } from "../app/site-header";
import sweetSeatsLogo from "@workspace/sweet-seats-design-system/assets/sweet-seats-music-fan-logo.png";

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
  return <main className="ss-app style-guide" id="main-content">
    <SiteHeader secondaryHref={brandNavigation.discovery.href} secondaryLabel="Discovery demo" />
    <div className="guide-content">
      <span className="guide-kicker">DEVELOPMENT STYLE GUIDE</span>
    <section className="guide-intro">
      <p className="eyebrow">SWEET SEATS · CANONICAL DARK</p>
      <h1>One shared<br />house style.</h1>
      <p>The discovery app consumes the shared Sweet Seats design-system tokens and components. This page is a development-only component reference.</p>
      <nav className="guide-nav" aria-label="Shared site navigation">
        <Link variant="primary" href={brandNavigation.discovery.href}>{brandNavigation.discovery.label}</Link>
        <Link variant="quiet" href={brandNavigation.publicSite.href}>{brandNavigation.publicSite.label}</Link>
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
      <p className="guide-note">Palette values come from the linked Sweet Seats design system. The coming-soon artifact remains unchanged.</p>
    </section>

    <section className="guide-section guide-type" aria-labelledby="type-title">
      <div className="guide-heading"><p className="eyebrow">02 · TYPE</p><h2 id="type-title">Bold, familiar, readable.</h2></div>
      <div className="type-specimen"><span className="type-label">DISPLAY · SYSTEM SANS</span><p>Make room<br />for the music.</p></div>
      <div className="type-meta"><span>Body / ui-sans-serif system stack</span><span>Headlines / same family, heavier weight</span><span>Minimum body copy / 16px</span></div>
    </section>

    <section className="guide-section guide-marks" aria-labelledby="marks-title">
      <div className="guide-heading"><p className="eyebrow">03 · CURRENT MARKS</p><h2 id="marks-title">Provisional, not final.</h2></div>
      <div className="mark-samples">
        <div className="mark-sample"><img className="guide-existing-logo" src={sweetSeatsLogo} alt="Sweet Seats headphone-and-seat music-fan logo" /><p><strong>Music-fan logo</strong><br />Uploaded brand asset used in the discovery header.</p></div>
      </div>
      <p className="guide-note">The logo asset is retained as supplied. No additional artwork is generated here.</p>
    </section>

    <section className="guide-section" aria-labelledby="controls-title">
      <div className="guide-heading"><p className="eyebrow">04 · CONTROLS &amp; STATES</p><h2 id="controls-title">Room to tap. Focus to find.</h2></div>
      <div className="guide-controls">
        <div className="guide-control-block">
          <h3>Navigation and actions</h3>
          <div className="guide-actions">
            <Link variant="primary" href="#form-examples">Primary link</Link>
            <Button variant="quiet" type="button" onClick={() => setMessage("Example action acknowledged locally. No form was submitted.")}>Secondary action</Button>
            <Button type="button" disabled>Disabled action</Button>
          </div>
          <p className="guide-note" aria-live="polite">{message}</p>
        </div>
        <div className="guide-control-block" id="form-examples">
          <h3>Form-field examples</h3>
          <div className="guide-field"><Field>
            <FieldLabel htmlFor="guide-email">Email address</FieldLabel>
            <FieldControl id="guide-email" type="email" placeholder="you@example.com" aria-describedby="guide-email-help" />
            <FieldHelp id="guide-email-help">An example field only; there is no connected waitlist or submission.</FieldHelp>
          </Field></div>
          <div className="guide-field"><Field>
            <FieldLabel htmlFor="guide-invalid">Example with an error</FieldLabel>
            <FieldControl id="guide-invalid" type="text" aria-invalid="true" aria-describedby="guide-invalid-error" defaultValue="Invalid sample" />
            <FieldHelp id="guide-invalid-error">This example shows the accessible invalid state.</FieldHelp>
          </Field></div>
        </div>
      </div>
      <div className="guide-statuses">
        <StatusMessage tone="warning"><strong>Warning:</strong> Some source observations may be older than expected.</StatusMessage>
        <StatusMessage tone="error"><strong>Error:</strong> Discovery is unavailable. No event availability is inferred.</StatusMessage>
        <StatusMessage tone="success"><strong>Recent:</strong> Observation is inside the demo freshness window.</StatusMessage>
      </div>
    </section>

    <footer className="guide-footer"><span>Sweet Seats · Shared design system</span><Link href={brandNavigation.discovery.href}>Back to discovery</Link></footer>
    </div>
  </main>;
}
