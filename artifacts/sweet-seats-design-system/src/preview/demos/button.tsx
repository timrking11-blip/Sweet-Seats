import { Button } from '../../components/ui/button';
import { Guidelines, Row } from '../parts';

export function ButtonDemo() {
  return (
    <div className="space-y-8">
      <section className="space-y-4 rounded-xl border bg-card p-6 text-card-foreground">
        <div>
          <h2 className="font-semibold">Variants and states</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Native buttons retain keyboard behavior and a 44px minimum target.
          </p>
        </div>
        <Row label="Actions">
          <Button variant="primary" type="button">Explore shows</Button>
          <Button variant="quiet" type="button">Learn more</Button>
          <Button variant="quiet" type="button" disabled>Unavailable</Button>
        </Row>
        <p className="text-sm text-muted-foreground">
          These are visual examples only; they do not save, submit, or purchase.
        </p>
      </section>
      <section className="space-y-4 rounded-xl border bg-card p-6 text-card-foreground">
        <h2 className="font-semibold">Use</h2>
        <Guidelines
          items={[
            { kind: 'do', text: 'Use a clear, specific verb for an available action.' },
            { kind: 'dont', text: 'Show an enabled control when the product action is not implemented.' },
          ]}
        />
      </section>
    </div>
  );
}
