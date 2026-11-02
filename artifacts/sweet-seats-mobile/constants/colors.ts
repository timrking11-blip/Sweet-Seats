/**
 * Semantic design tokens for the mobile app.
 *
 * These tokens mirror the naming conventions used in web artifacts (index.css)
 * so that multi-artifact projects share a cohesive visual identity.
 *
 * Replace the placeholder values below with values that match the project's
 * brand. If a sibling web artifact exists, read its index.css and convert the
 * HSL values to hex so both artifacts use the same palette.
 *
 * To add dark mode, add a `dark` key with the same token names.
 * The useColors() hook will automatically pick it up.
 */

const colors = {
  light: {
    // Legacy aliases (kept for backward compatibility)
    text: '#f6f1eb',
    tint: '#f7ca70',

    // Core surfaces
    background: '#100c19',
    foreground: '#f6f1eb',

    // Cards / elevated surfaces
    card: '#21172e',
    cardForeground: '#f6f1eb',

    // Primary action color (buttons, links, active states)
    primary: '#f7ca70',
    primaryForeground: '#201527',

    // Secondary / less-emphasis interactive surfaces
    secondary: '#191124',
    secondaryForeground: '#f6f1eb',

    // Muted / subdued elements (dividers, timestamps, placeholders)
    muted: '#2b2231',
    mutedForeground: '#aaa0ad',

    // Accent highlights (badges, selected items, focus rings)
    accent: '#a97cff',
    accentForeground: '#f6f1eb',
    coral: '#ff8568',
    success: '#c4eed8',

    // Destructive actions (delete, error states)
    destructive: '#ff8568',
    destructiveForeground: '#ffffff',

    // Borders and input outlines
    border: 'rgba(246,241,235,0.16)',
    input: '#65526f',
  },

  // Border radius (in px). Sync from the sibling web artifact's --radius
  // CSS variable. This value applies to cards, buttons, inputs, and modals.
  radius: 8,
};

export default colors;
