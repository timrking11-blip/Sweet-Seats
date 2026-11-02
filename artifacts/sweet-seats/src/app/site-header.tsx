import { Link } from "@workspace/sweet-seats-design-system/components/ui/link";
import { brandNavigation } from "../../../../lib/sweet-seats-brand/foundation";
import sweetSeatsLogo from "@workspace/sweet-seats-design-system/assets/sweet-seats-music-fan-logo.png";

type SiteHeaderProps = {
  secondaryHref?: string;
  secondaryLabel?: string;
};

export function SiteHeader({ secondaryHref, secondaryLabel }: SiteHeaderProps) {
  return (
    <header className="ss-top">
      <Link className="ss-brand-link" variant="plain" href="/" aria-label="Sweet Seats discovery home">
        <img className="ss-logo" src={sweetSeatsLogo} alt="" />
      </Link>
      <nav className="ss-top-right" aria-label="Sweet Seats navigation">
        <span className="ss-demo">LOCAL DISCOVERY DEMO</span>
        {secondaryHref && secondaryLabel && <Link variant="plain" href={secondaryHref}>{secondaryLabel}</Link>}
        <Link variant="text" href={brandNavigation.publicSite.href}>{brandNavigation.publicSite.label}</Link>
      </nav>
    </header>
  );
}
