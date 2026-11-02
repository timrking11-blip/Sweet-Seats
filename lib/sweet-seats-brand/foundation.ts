/** Framework-neutral source imports: no new package, dependencies or API runtime. */
export const BRAND_SCOPE = "midnight-session";
export const brandNavigation = {
  discovery: { href: "/", label: "Explore the discovery demo" },
  publicSite: { href: "/coming-soon/", label: "About Sweet Seats" },
} as const;

export function applyBrandFoundation(root: { setAttribute(name: string, value: string): void }) {
  root.setAttribute("data-ss-brand", BRAND_SCOPE);
}
