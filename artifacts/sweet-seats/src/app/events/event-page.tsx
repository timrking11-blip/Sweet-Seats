
import { useParams } from "wouter";
import { EventDetail } from "../discovery";
import DemoNotice from "../demo-notice";
import { SiteHeader } from "../site-header";

export default function EventPage() {
  const { eventId } = useParams<{ eventId: string }>();
  return <main className="ss-app ss-event-route">
    <SiteHeader secondaryHref="/#discover-title" secondaryLabel="← All events" />
    <section className="ss-event-page-shell" aria-label="Event details">
      <DemoNotice />
      <EventDetail eventId={eventId} />
    </section>
    <footer className="ss-foot"><span>Sweet Seats · Local synthetic demo</span><span>No live ticket listings or notifications</span></footer>
  </main>;
}
