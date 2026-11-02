import type { AnchorHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {}

export function Link({ className, ...props }: LinkProps) {
  return (
    <a
      className={cn(
        'inline-flex min-h-11 items-center text-sm font-semibold text-accent underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        className,
      )}
      {...props}
    />
  );
}
