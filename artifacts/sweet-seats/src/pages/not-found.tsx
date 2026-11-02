import { Link } from "@workspace/sweet-seats-design-system/components/ui/link";
import { SiteHeader } from "../app/site-header";

export default function NotFound() {
  return <main className="ss-app ss-not-found-page" aria-labelledby="not-found-title">
    <SiteHeader secondaryHref="/" secondaryLabel="Discovery demo" />
    <section className="ss-not-found">
      <p className="ss-overline">404 · PAGE NOT FOUND</p>
      <h1 id="not-found-title">That page isn’t here.</h1>
      <p>This address does not match a Sweet Seats discovery page.</p>
      <Link variant="primary" href="/">Return to discovery home</Link>
    </section>
  </main>;
}
