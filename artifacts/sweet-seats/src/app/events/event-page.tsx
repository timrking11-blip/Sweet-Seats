
import { useParams } from "wouter";
import { EventDetail } from "../discovery";
import DemoNotice from "../demo-notice";

export default function EventPage() {
  const { eventId } = useParams<{ eventId: string }>();
  return <main className="detail-shell">
    <nav className="topbar" aria-label="Event navigation"><a className="brand" href="/">sweet seats</a><div className="nav-actions"><a className="text-button" href="/#discover-title">← All events</a><a className="text-button" href="/coming-soon/">About Sweet Seats</a></div></nav>
    <DemoNotice />
    <EventDetail eventId={eventId} />
    <footer>Local demo · No live ticket listings or notifications</footer>
  </main>;
}
