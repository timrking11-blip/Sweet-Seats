import { Link } from '../../components/ui/link';
import { Guidelines, Row } from '../parts';

export function LinkDemo() {
  return (
    <div className="space-y-8">
      <section className="space-y-4 rounded-xl border bg-card p-6 text-card-foreground">
        <h2 className="font-semibold">Text and action links</h2>
        <p className="max-w-xl text-sm leading-6 text-muted-foreground">
          Links keep a visible underline on hover and a high-contrast keyboard
          focus ring. Each example navigates within this style guide.
        </p>
        <Row label="Examples">
          <Link href="#page=overview">Back to overview</Link>
          <Link href="#page=color-roles">View color roles</Link>
          <Link variant="plain" href="#page=overview">Header link</Link>
          <Link variant="heading" href="#page=overview">Event title link</Link>
          <Link variant="primary" href="#page=button">Primary action</Link>
          <Link variant="quiet" href="#page=field">Quiet action</Link>
        </Row>
      </section>
      <section className="space-y-4 rounded-xl border bg-card p-6 text-card-foreground">
        <h2 className="font-semibold">Use</h2>
        <Guidelines
          items={[
            { kind: 'do', text: 'Name the destination or action; keep link text visible without color alone.' },
            { kind: 'dont', text: 'Use a brand accent color as a source-health indicator.' },
          ]}
        />
      </section>
    </div>
  );
}
