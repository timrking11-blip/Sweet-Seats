import type { HTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export type StatusTone = 'warning' | 'error' | 'success';

export interface StatusMessageProps
  extends HTMLAttributes<HTMLParagraphElement> {
  tone: StatusTone;
}

const toneBorders: Record<StatusTone, string> = {
  warning: 'border-l-chart-3',
  error: 'border-l-destructive',
  success: 'border-l-chart-4',
};

export function StatusMessage({
  tone,
  className,
  role,
  ...props
}: StatusMessageProps) {
  return (
    <p
      role={role ?? (tone === 'error' ? 'alert' : 'status')}
      data-tone={tone}
      className={cn(
        'rounded-lg border border-border border-l-4 bg-card p-4 text-sm leading-6 text-card-foreground',
        toneBorders[tone],
        className,
      )}
      {...props}
    />
  );
}
