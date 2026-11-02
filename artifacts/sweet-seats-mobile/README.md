# Sweet Seats Mobile

Expo companion to the Sweet Seats web app. Discovery and detail requests use the
shared generated API client, `/api/discovery`, and the original Python service.
There is no mobile fixture copy or live provider.

## Run

Start the existing `artifacts/api-server: API Server` and
`artifacts/sweet-seats-mobile: expo` workflows. The mobile workflow injects
`EXPO_PUBLIC_DOMAIN` for absolute API requests from phones. Open this artifact's
phone preview to use Expo Go. Both services must remain reachable.

The discovery screen searches artist, venue, neighborhood and event title on the
current page (up to 100 events). Previous/next navigation clears the search.
Pull down or use the refresh button to re-read permission-checked data.

## Data boundaries

- Invented events, artists and venues are prominently labeled synthetic.
- Source URLs are selectable placeholder text, not live outbound links.
- A missing/withheld event (404) is distinct from network/service failure.
- Partial, unavailable, blocked and review-required feeds preserve their meaning;
  none implies sold-out tickets.
- Failed refreshes hide old results. Queries are revalidated on screen focus and
  app foreground, have an eight-second deadline, and are not persisted.
- No authentication, notifications, live providers, purchases, or ticket advice
  are added.

## Checks

`pnpm --filter @workspace/sweet-seats-mobile run typecheck`

From this directory: `CI=1 pnpm exec expo install --check` and
`pnpm dlx expo-doctor@latest`.

The browser preview validates rendering but does not substitute for physical
iOS/Android checks of safe areas, keyboard, gestures and system font fallbacks.
