import { tokens } from '../generated/tokens';
import { Button } from '../components/ui/button';
import {
  Field,
  FieldControl,
  FieldHelp,
  FieldLabel,
} from '../components/ui/field';
import { Link } from '../components/ui/link';
import { StatusMessage } from '../components/ui/status';
import { Guidelines, Row } from './parts';

const logoUrl = `${import.meta.env.BASE_URL}sweet-seats-logo.png`;
const spacingScale = [4, 8, 12, 16, 24, 32, 48, 64, 96] as const;
const colorRoles = Object.keys(tokens.color.dark) as Array<
  keyof typeof tokens.color.dark
>;

type ColorScope = keyof typeof tokens.color;

function Surface({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-border bg-card p-5 text-card-foreground sm:p-6 ${className}`}
    >
      {children}
    </section>
  );
}

function Palette({ scope }: { scope: ColorScope }) {
  const palette = tokens.color[scope];
  const isCanonical = scope === 'dark';

  return (
    <section
      aria-label={`${scope} color palette`}
      className="rounded-2xl border p-5 sm:p-6"
      style={{
        backgroundColor: palette.background,
        color: palette.foreground,
        borderColor: palette.border,
      }}
    >
      <div className="mb-5">
        <h2 className="text-xl font-semibold">
          {isCanonical ? 'Midnight Session · canonical' : 'Warm cream · derived'}
        </h2>
        <p className="mt-1 text-sm opacity-80">
          {isCanonical
            ? 'Owner-supplied dark palette from the shared foundation.'
            : 'Companion values derived for review; not approved for product screens.'}
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {colorRoles.map((role) => {
          const color = palette[role];
          return (
            <div
              key={`${scope}-${role}`}
              className="flex min-w-0 items-center gap-3 rounded-lg border p-2"
              style={{
                backgroundColor: scope === 'dark' ? '#0D2038' : '#FFF8EE',
                borderColor: palette.border,
              }}
            >
              <span
                aria-hidden="true"
                className="h-9 w-9 shrink-0 rounded-md border"
                style={{ backgroundColor: color, borderColor: palette.border }}
              />
              <span className="min-w-0">
                <span className="block break-words text-xs font-medium leading-4">{role}</span>
                <code className="block text-xs opacity-75">{color}</code>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function OverviewPage() {
  return (
    <div className="space-y-6">
      <section className="grid gap-6 rounded-2xl border border-border bg-card p-5 text-card-foreground sm:grid-cols-[minmax(0,1fr)_220px] sm:items-center sm:p-8">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
            Midnight Session
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">
            Be there for the good stuff.
          </h2>
          <p className="mt-3 text-base leading-7 text-muted-foreground">
            Live music discovery for NYC and nearby.
          </p>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-muted-foreground">
            One token source and four reusable interface families extracted
            from the active Sweet Seats foundation. This is a standalone
            reference; no product screens have been changed.
          </p>
        </div>
        <div className="rounded-xl border border-border p-2">
          <img
            src={logoUrl}
            alt="Sweet Seats logo with headphones, a coral seat, music note, and teal bars"
            className="mx-auto aspect-square w-full max-w-[210px] rounded-lg object-cover"
          />
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        <Surface>
          <h2 className="font-semibold">Source-backed foundations</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Midnight navy, warm cream, coral, and teal; a system sans stack;
            4px spacing; 12px controls; visible 3px focus.
          </p>
        </Surface>
        <Surface>
          <h2 className="font-semibold">Review status</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Dark mode is canonical. The light companion is clearly marked
            derived and should be reviewed before any screen adopts it.
          </p>
        </Surface>
      </div>

      <Surface className="space-y-5">
        <div>
          <h2 className="font-semibold">Active shared UI families</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            These examples are for visual review only; they do not trigger
            product actions.
          </p>
        </div>
        <Row label="Actions">
          <Button variant="primary" type="button">Explore shows</Button>
          <Button variant="quiet" type="button">Learn more</Button>
          <Link href="#page=button">Button patterns</Link>
        </Row>
        <Field>
          <FieldLabel htmlFor="overview-search">Find a show</FieldLabel>
          <FieldControl
            id="overview-search"
            type="search"
            placeholder="Artist, venue, or neighborhood"
          />
          <FieldHelp>This is a visual example, not a connected search.</FieldHelp>
        </Field>
        <StatusMessage tone="warning">
          Example source warning. Existing observation times are not changed by
          refreshing stored data.
        </StatusMessage>
      </Surface>
    </div>
  );
}

export function BrandPage() {
  return (
    <div className="space-y-6">
      <Surface className="grid gap-6 sm:grid-cols-[220px_minmax(0,1fr)] sm:items-center">
        <img
          src={logoUrl}
          alt="Sweet Seats logo with headphones, a coral seat, music note, and teal equalizer bars"
          className="mx-auto aspect-square w-full max-w-[220px] rounded-xl object-cover"
        />
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
            Sweet Seats
          </p>
          <h2 className="mt-2 text-2xl font-bold">Music, made easier to find.</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
            The supplied mark pairs a headphone arch and seat cushion with a
            music note and teal sound bars. Its raster file is a visual
            reference—not an editable vector master or approved production
            export.
          </p>
        </div>
      </Surface>

      <Surface className="space-y-4">
        <h2 className="font-semibold">Brand and content guidance</h2>
        <Guidelines
          items={[
            { kind: 'do', text: 'Keep the supplied artwork on a solid, quiet background and preserve its proportions.' },
            { kind: 'dont', text: 'Shrink the detailed stacked mark into a favicon or describe the raster as a vector master.' },
            { kind: 'do', text: 'Use familiar words such as show, artist, venue, source, and checked.' },
            { kind: 'dont', text: 'Promise comprehensive coverage, guaranteed savings, artificial urgency, or unvalidated predictions.' },
          ]}
        />
      </Surface>

      <Surface>
        <h2 className="font-semibold">Two existing visual contexts</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-border bg-background p-4">
            <h3 className="font-semibold">Discovery demo</h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Data-forward, source-aware, and anchored to the canonical
              Midnight Session palette.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-background p-4">
            <h3 className="font-semibold">Coming-soon brand page</h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              A separately imported marketing composition. Its layout is not
              copied into this component library.
            </p>
          </div>
        </div>
      </Surface>
    </div>
  );
}

export function ColorsPage() {
  return (
    <div className="space-y-6">
      <Surface>
        <h2 className="font-semibold">Semantic color roles</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          Dark values are copied from the shared Sweet Seats foundation. Light
          values are derived companions. Inspect text and control contrast in
          the rendered product before approving a different theme.
        </p>
      </Surface>
      <div className="grid gap-5 xl:grid-cols-2">
        <Palette scope="dark" />
        <Palette scope="light" />
      </div>
      <Surface>
        <h2 className="font-semibold">Solid-color contrast references</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          The supplied dark checks pass normal text at 4.5:1 and meaningful
          boundaries/focus at 3:1. Selected calculated light pairs also meet
          those ratios. These are solid-pair calculations, not a complete
          rendered accessibility audit.
        </p>
        <ul className="mt-4 grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
          <li>Dark text on navy: 16.98:1</li>
          <li>Dark coral action on navy: 6.39:1</li>
          <li>Dark teal accent on navy: 8.44:1</li>
          <li>Light text on warm cream: 16.98:1</li>
          <li>Light teal accent on cream: 5.86:1</li>
          <li>Light control border on cream: 3.44:1</li>
        </ul>
      </Surface>
    </div>
  );
}

export function FontsPage() {
  const sans = tokens.fontFamily.sans.join(', ');
  const mono = tokens.fontFamily.mono.join(', ');

  return (
    <div className="space-y-6">
      <Surface>
        <h2 className="font-semibold">System type</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          The existing product uses system fonts to avoid extra downloads. The
          interface does not use a serif display face.
        </p>
        <div className="mt-6 space-y-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Display and headings
            </p>
            <p className="mt-2 text-4xl font-bold tracking-tight" style={{ fontFamily: sans }}>
              Be there for the good stuff.
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Body
            </p>
            <p className="mt-2 max-w-2xl text-base leading-7" style={{ fontFamily: sans }}>
              Find live music around New York with clear event details and
              honest source context.
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Token values
            </p>
            <p className="mt-2 break-words rounded-lg border border-border bg-muted p-3 text-xs">
              sans: {sans}
            </p>
            <p className="mt-2 break-words rounded-lg border border-border bg-muted p-3 text-xs" style={{ fontFamily: mono }}>
              mono: {mono}
            </p>
          </div>
        </div>
      </Surface>
    </div>
  );
}

export function LayoutPage() {
  return (
    <div className="space-y-6">
      <Surface>
        <h2 className="font-semibold">Four-pixel spacing rhythm</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Use spacing to group related information; avoid nesting cards around
          every paragraph.
        </p>
        <div className="mt-5 space-y-3">
          {spacingScale.map((value) => (
            <div key={value} className="flex items-center gap-3">
              <span className="w-10 text-right font-mono text-xs text-muted-foreground">
                {value}px
              </span>
              <span
                aria-hidden="true"
                className="h-3 rounded-full bg-primary"
                style={{ width: value }}
              />
            </div>
          ))}
        </div>
      </Surface>

      <div className="grid gap-4 sm:grid-cols-2">
        <Surface>
          <h2 className="font-semibold">Corners and touch targets</h2>
          <div className="mt-4 flex flex-wrap items-end gap-4">
            <div className="rounded-lg border border-border bg-muted p-3 text-sm">
              12px control
            </div>
            <div className="rounded-xl border border-border bg-muted p-3 text-sm">
              16px card
            </div>
            <div className="rounded-full border border-border bg-muted px-4 py-2 text-sm">
              Pill when useful
            </div>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            Interactive targets are at least 44 × 44 px.
          </p>
        </Surface>
        <Surface>
          <h2 className="font-semibold">Responsive content</h2>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
            <li>Small: below 640px; 16px page gutters.</li>
            <li>Medium: 640–1023px; 24px gutters.</li>
            <li>Large: 1024px and above; 32px gutters.</li>
            <li>Marketing width: 1200–1250px; discovery: about 1120px.</li>
          </ul>
        </Surface>
      </div>
    </div>
  );
}
