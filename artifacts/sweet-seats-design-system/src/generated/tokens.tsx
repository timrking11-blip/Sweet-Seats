/* GENERATED FROM tokens.json -- DO NOT EDIT. Run scripts/build-tokens.mjs. */
// Portable design tokens (colors as hex). Web consumes the theme via
// src/index.css; mobile (Expo) and any other platform import this object so the
// whole product shares one source of truth.
export const tokens = {
  "color": {
    "light": {
      "background": "#FFF1DD",
      "foreground": "#031126",
      "border": "#72849A",
      "card": "#FFF8EE",
      "cardForeground": "#031126",
      "popover": "#FFF8EE",
      "popoverForeground": "#031126",
      "primary": "#FF624D",
      "primaryForeground": "#031126",
      "secondary": "#E6ECE9",
      "secondaryForeground": "#031126",
      "muted": "#F2E9DC",
      "mutedForeground": "#31445A",
      "accent": "#17695F",
      "accentForeground": "#FFF1DD",
      "destructive": "#A9433A",
      "destructiveForeground": "#FFF1DD",
      "input": "#72849A",
      "ring": "#13685F",
      "chart1": "#C94C3F",
      "chart2": "#17695F",
      "chart3": "#8A5B00",
      "chart4": "#28734F",
      "chart5": "#A9433A",
      "sidebar": "#FFF8EE",
      "sidebarForeground": "#031126",
      "sidebarBorder": "#72849A",
      "sidebarPrimary": "#FF624D",
      "sidebarPrimaryForeground": "#031126",
      "sidebarAccent": "#E6ECE9",
      "sidebarAccentForeground": "#031126",
      "sidebarRing": "#13685F"
    },
    "dark": {
      "background": "#031126",
      "foreground": "#FFF1DD",
      "border": "#2A3E56",
      "card": "#0D2038",
      "cardForeground": "#FFF1DD",
      "popover": "#162D47",
      "popoverForeground": "#FFF1DD",
      "primary": "#FF624D",
      "primaryForeground": "#031126",
      "secondary": "#162D47",
      "secondaryForeground": "#FFF1DD",
      "muted": "#0D2038",
      "mutedForeground": "#B7C3D1",
      "accent": "#67BCAF",
      "accentForeground": "#031126",
      "destructive": "#FFB1A8",
      "destructiveForeground": "#031126",
      "input": "#72849A",
      "ring": "#67BCAF",
      "chart1": "#FF624D",
      "chart2": "#67BCAF",
      "chart3": "#F1CC77",
      "chart4": "#91D4AA",
      "chart5": "#FFB1A8",
      "sidebar": "#031126",
      "sidebarForeground": "#FFF1DD",
      "sidebarBorder": "#2A3E56",
      "sidebarPrimary": "#FF624D",
      "sidebarPrimaryForeground": "#031126",
      "sidebarAccent": "#162D47",
      "sidebarAccentForeground": "#FFF1DD",
      "sidebarRing": "#67BCAF"
    }
  },
  "fontFamily": {
    "sans": [
      "ui-sans-serif",
      "system-ui",
      "-apple-system",
      "Segoe UI",
      "Helvetica",
      "Arial",
      "sans-serif"
    ],
    "serif": [
      "ui-sans-serif",
      "system-ui",
      "-apple-system",
      "Segoe UI",
      "Helvetica",
      "Arial",
      "sans-serif"
    ],
    "mono": [
      "ui-monospace",
      "SFMono-Regular",
      "Consolas",
      "monospace"
    ]
  },
  "radius": "12px",
  "spacing": "4px"
} as const;

export type Tokens = typeof tokens;
export default tokens;
