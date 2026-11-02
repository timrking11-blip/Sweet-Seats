import { StatusMessage } from '../../components/ui/status';
import { Guidelines, Stack } from '../parts';

export function StatusDemo() {
  return (
    <div className="space-y-8">
      <section className="space-y-4 rounded-xl border bg-card p-6 text-card-foreground">
        <h2 className="font-semibold">Message tones</h2>
        <Stack>
          <StatusMessage tone="warning">
            A source failed. Previously observed events remain available with
            their original observation times.
          </StatusMessage>
          <StatusMessage tone="error">
            Source unavailable. This does not mean there are no events or that
            tickets are sold out.
          </StatusMessage>
          <StatusMessage tone="success">
            Example status only. It is not a live source-health signal.
          </StatusMessage>
        </Stack>
        <p className="text-sm text-muted-foreground">
          Static examples; no live events or source checks are running here.
        </p>
      </section>
      <section className="space-y-4 rounded-xl border bg-card p-6 text-card-foreground">
        <h2 className="font-semibold">Use</h2>
        <Guidelines
          items={[
            { kind: 'do', text: 'Keep source health separate from event status, such as canceled or sold out.' },
            { kind: 'do', text: 'Preserve the original observation time when refreshing stored data.' },
            { kind: 'dont', text: 'Infer availability from a collection failure or a stale observation.' },
          ]}
        />
      </section>
    </div>
  );
}
