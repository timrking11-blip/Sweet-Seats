import {
  Field,
  FieldControl,
  FieldHelp,
  FieldLabel,
} from '../../components/ui/field';

export function FieldDemo() {
  return (
    <div className="space-y-8">
      <section className="max-w-xl space-y-5 rounded-xl border bg-card p-6 text-card-foreground">
        <div>
          <h2 className="font-semibold">Label, control, and help</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Use a real label and connect instructions or errors with
            aria-describedby.
          </p>
        </div>
        <Field>
          <FieldLabel htmlFor="sample-email">Email address</FieldLabel>
          <FieldControl
            id="sample-email"
            type="email"
            placeholder="you@example.com"
            aria-describedby="sample-email-help"
          />
          <FieldHelp id="sample-email-help">
            Preview example only; this field has no waitlist or submission.
          </FieldHelp>
        </Field>
        <Field>
          <FieldLabel htmlFor="sample-invalid">Example with an error</FieldLabel>
          <FieldControl
            id="sample-invalid"
            type="text"
            aria-invalid="true"
            aria-describedby="sample-invalid-help"
            defaultValue="Needs correction"
          />
          <FieldHelp id="sample-invalid-help">
            Add a concise correction that explains what the visitor should do.
          </FieldHelp>
        </Field>
      </section>
    </div>
  );
}
