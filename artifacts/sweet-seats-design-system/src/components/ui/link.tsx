import type { AnchorHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export type LinkVariant = 'text' | 'plain' | 'heading' | 'primary' | 'quiet';

export interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  variant?: LinkVariant;
}

const variants: Record<LinkVariant, string> = {
  text: 'text-accent underline-offset-4 hover:underline',
  plain: 'text-foreground no-underline hover:text-accent',
  heading: 'text-lg font-bold text-foreground no-underline hover:text-accent',
  primary:
    'rounded-lg border border-transparent bg-primary px-4 text-primary-foreground no-underline hover:brightness-110',
  quiet:
    'rounded-lg border border-input bg-secondary px-4 text-secondary-foreground no-underline hover:brightness-105',
};

export function Link({ variant = 'text', className, ...props }: LinkProps) {
  return (
    <a
      className={cn(
        'inline-flex min-h-11 items-center text-sm font-semibold transition-[background-color,color,filter] duration-[180ms] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
