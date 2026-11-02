
import { useParams } from "wouter";
import { EventDetail } from "../discovery";

export default function EventPage() {
  const { eventId } = useParams<{ eventId: string }>();
  return <main className="detail-shell">
    <nav className="topbar" aria-label="Event navigation"><a className="brand" href="/">sweet seats</a><a className="text-button" href="/#discover-title">← All events</a></nav>
    <EventDetail eventId={eventId} />
    <footer>Local demo · No live ticket listings or notifications</footer>
  </main>;
}
