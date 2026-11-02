import { lazy, type ComponentType } from 'react';
import {
  BrandPage,
  ColorsPage,
  FontsPage,
  LayoutPage,
  OverviewPage,
} from './foundations';

function lazyPage(load: () => Promise<ComponentType>) {
  return lazy(async () => ({ default: await load() }));
}

const ButtonDemo = lazyPage(() =>
  import('./demos/button').then(({ ButtonDemo }) => ButtonDemo),
);
const LinkDemo = lazyPage(() =>
  import('./demos/link').then(({ LinkDemo }) => LinkDemo),
);
const FieldDemo = lazyPage(() =>
  import('./demos/field').then(({ FieldDemo }) => FieldDemo),
);
const StatusDemo = lazyPage(() =>
  import('./demos/status').then(({ StatusDemo }) => StatusDemo),
);

export type PreviewEntry = {
  id: string;
  name: string;
  description: string;
  Page: ComponentType;
};

export type NavGroup = {
  name: string;
  entries: PreviewEntry[];
};

export const DESIGN_SYSTEM = {
  title: 'Sweet Seats Design System',
  description:
    'Midnight Session tokens, source-backed interface foundations, and a reviewable derived light theme.',
} as const;

export const OVERVIEW_ENTRY: PreviewEntry = {
  id: 'overview',
  name: 'Overview',
  description: 'The shared brand foundations and source-backed UI families.',
  Page: OverviewPage,
};

export const NAV_GROUPS: NavGroup[] = [
  {
    name: 'Brand',
    entries: [
      {
        id: 'brand-identity',
        name: 'Identity and guidance',
        description: 'Logo use, brand voice, and the two existing visual contexts.',
        Page: BrandPage,
      },
    ],
  },
  {
    name: 'Colors',
    entries: [
      {
        id: 'color-roles',
        name: 'Color roles',
        description: 'Canonical Midnight Session tokens and derived light values.',
        Page: ColorsPage,
      },
    ],
  },
  {
    name: 'Fonts',
    entries: [
      {
        id: 'type-scale',
        name: 'Type system',
        description: 'System font stacks and live type examples.',
        Page: FontsPage,
      },
    ],
  },
  {
    name: 'Layout',
    entries: [
      {
        id: 'spacing-radius',
        name: 'Spacing and layout',
        description: 'Spacing, radii, content widths, and responsive breakpoints.',
        Page: LayoutPage,
      },
    ],
  },
  {
    name: 'Actions',
    entries: [
      {
        id: 'button',
        name: 'Buttons',
        description: 'Primary and quiet actions, disabled state, and focus.',
        Page: ButtonDemo,
      },
      {
        id: 'link',
        name: 'Links',
        description: 'Destination-first text links with visible keyboard focus.',
        Page: LinkDemo,
      },
    ],
  },
  {
    name: 'Forms & inputs',
    entries: [
      {
        id: 'field',
        name: 'Form field',
        description: 'Native input, associated label, help text, and error state.',
        Page: FieldDemo,
      },
    ],
  },
  {
    name: 'Feedback',
    entries: [
      {
        id: 'status',
        name: 'Status messages',
        description: 'Warning, error, and success tones with appropriate semantics.',
        Page: StatusDemo,
      },
    ],
  },
];

export const ALL_ENTRIES: PreviewEntry[] = [
  OVERVIEW_ENTRY,
  ...NAV_GROUPS.flatMap((group) => group.entries),
];

const duplicateIds = ALL_ENTRIES.map((entry) => entry.id).filter(
  (id, index, ids) => ids.indexOf(id) !== index,
);
if (duplicateIds.length > 0) {
  throw new Error(
    `Duplicate preview page id(s): ${[...new Set(duplicateIds)].join(', ')}`,
  );
}
