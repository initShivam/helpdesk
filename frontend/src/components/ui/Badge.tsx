import type { ReactNode } from 'react';
import { cn } from 'cn';

type BadgeProps = {
  children: ReactNode;
  className?: string;
};

function Badge({ children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium leading-5',
        className,
      )}
    >
      {children}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    open: 'border-blue-200 bg-blue-50 text-blue-700',
    pending: 'border-amber-200 bg-amber-50 text-amber-800',
    resolved: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    closed: 'border-slate-200 bg-slate-100 text-slate-600',
    failed: 'border-red-200 bg-red-50 text-red-700',
    sent: 'border-blue-200 bg-blue-50 text-blue-700',
    delivered: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    read: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    queued: 'border-amber-200 bg-amber-50 text-amber-800',
  };
  return (
    <Badge className={styles[status.toLowerCase()] ?? 'border-slate-200 bg-slate-50 text-slate-600'}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
      <span className="capitalize">{status.replaceAll('_', ' ')}</span>
    </Badge>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const styles: Record<string, string> = {
    low: 'border-slate-200 bg-slate-50 text-slate-600',
    medium: 'border-amber-200 bg-amber-50 text-amber-800',
    high: 'border-orange-200 bg-orange-50 text-orange-800',
    urgent: 'border-red-200 bg-red-50 text-red-700',
  };
  return (
    <Badge className={styles[priority.toLowerCase()] ?? 'border-slate-200 bg-slate-50 text-slate-600'}>
      <span className="capitalize">{priority}</span>
    </Badge>
  );
}

function CategoryBadge({ category }: { category: string }) {
  const styles: Record<string, string> = {
    general: 'border-slate-200 bg-slate-50 text-slate-600',
    technical: 'border-blue-200 bg-blue-50 text-blue-700',
    refund: 'border-teal-200 bg-teal-50 text-teal-800',
  };
  return (
    <Badge className={styles[category.toLowerCase()] ?? 'border-slate-200 bg-slate-50 text-slate-600'}>
      <span className="capitalize">{category}</span>
    </Badge>
  );
}

export { Badge, CategoryBadge, PriorityBadge, StatusBadge };
