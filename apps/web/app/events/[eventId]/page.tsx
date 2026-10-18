"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { EventDetail } from "../../discovery";

export default function EventPage() {
  const { eventId } = useParams<{ eventId: string }>();
  return <main className="detail-shell">
    <nav className="topbar" aria-label="Event navigation"><Link className="brand" href="/">sweet seats</Link><Link className="text-button" href="/#discover-title">← All events</Link></nav>
    <EventDetail eventId={eventId} />
    <footer>Local demo · No live ticket listings or notifications</footer>
  </main>;
}
