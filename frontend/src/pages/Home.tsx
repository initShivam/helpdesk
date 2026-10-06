import React, { useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, ArrowRight, Inbox, Ticket as TicketIcon, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { AuthContext } from '../context/AuthContext';
import { apiJson } from '../api';
import { Ticket } from '../types';
import { CategoryBadge, PriorityBadge, StatusBadge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/button';

interface HomeTicketsResponse {
  count: number;
  results: Ticket[];
  stats: {
    total: number;
    open: number;
    high_urgent: number;
    resolved: number;
  };
}

const Home: React.FC = () => {
  const auth = useContext(AuthContext);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['tickets', 'home'],
    queryFn: () => apiJson<HomeTicketsResponse>('/api/tickets/?page=1&ordering=-created_at'),
    enabled: Boolean(auth?.user),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  const firstName = auth?.user?.username?.trim().split(/\s+/)[0] || 'there';
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const role = auth?.user?.role === 'ADMIN' ? 'admin' : 'agent';
  const stats = data?.stats;
  const metrics = [
    { label: 'Total tickets', value: stats?.total, icon: TicketIcon, iconStyle: 'bg-blue-50 text-blue-700' },
    { label: 'Open tickets', value: stats?.open, icon: Inbox, iconStyle: 'bg-amber-50 text-amber-700' },
    { label: 'High / urgent', value: stats?.high_urgent, icon: TriangleAlert, iconStyle: 'bg-orange-50 text-orange-700' },
    { label: 'Resolved', value: stats?.resolved, icon: Activity, iconStyle: 'bg-emerald-50 text-emerald-700' },
  ];

  return (
    <>
      <NavBar />
      <main className="app-main">
        <div className="mx-auto max-w-[1440px]">
          <PageHeader
            eyebrow="Support workspace"
            title={`${greeting}, ${firstName}`}
            description={`Welcome back to your ${role} workspace. Here's the latest support activity.`}
            actions={
              <Button asChild>
                <Link to="/tickets">View all tickets <ArrowRight className="size-4" aria-hidden="true" /></Link>
              </Button>
            }
          />

          {error && (
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
              <span>{error instanceof Error ? error.message : 'Unable to load your support overview.'}</span>
              <Button type="button" size="sm" variant="outline" onClick={() => void refetch()}>Try again</Button>
            </div>
          )}

          <section aria-label="Ticket overview" className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
            {metrics.map(({ label, value, icon: Icon, iconStyle }) => (
              <div key={label} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-slate-600">{label}</p>
                  <span className={`flex size-8 shrink-0 items-center justify-center rounded-md ${iconStyle}`}>
                    <Icon className="size-4" aria-hidden="true" />
                  </span>
                </div>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
                  {value ?? (isLoading ? '—' : 0)}
                </p>
              </div>
            ))}
          </section>

          <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-4 sm:px-5">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Recent tickets</h2>
                <p className="mt-0.5 text-sm text-slate-500">The latest requests from your customers.</p>
              </div>
              <Link to="/tickets" className="inline-flex items-center gap-1 text-sm font-medium text-blue-700 hover:text-blue-800">
                Browse tickets <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </div>

            {isLoading ? (
              <div className="space-y-3 p-4" aria-label="Loading recent tickets">
                {Array.from({ length: 4 }, (_, index) => (
                  <div key={index} className="grid grid-cols-4 gap-4 py-3">
                    <span className="h-4 animate-pulse rounded bg-slate-100" />
                    <span className="col-span-2 h-4 animate-pulse rounded bg-slate-100" />
                    <span className="h-4 animate-pulse rounded bg-slate-100" />
                  </div>
                ))}
              </div>
            ) : error ? (
              <EmptyState title="Recent tickets unavailable" description="Try refreshing the overview to load ticket activity." />
            ) : !data?.results.length ? (
              <EmptyState title="No tickets yet" description="New customer requests will show up here." />
            ) : (
              <>
                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full min-w-[1050px] table-fixed">
                    <colgroup>
                      <col className="w-[22%]" />
                      <col className="w-[35%]" />
                      <col className="w-[12%]" />
                      <col className="w-[12%]" />
                      <col className="w-[9%]" />
                      <col className="w-[10%]" />
                    </colgroup>
                    <thead className="bg-slate-50">
                      <tr className="border-b border-slate-200 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        <th scope="col" className="whitespace-nowrap px-4 py-3">Ticket</th>
                        <th scope="col" className="px-4 py-3">Subject / customer</th>
                        <th scope="col" className="whitespace-nowrap px-4 py-3">Category</th>
                        <th scope="col" className="whitespace-nowrap px-4 py-3">Status</th>
                        <th scope="col" className="whitespace-nowrap px-4 py-3">Priority</th>
                        <th scope="col" className="whitespace-nowrap px-4 py-3">Created</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.results.slice(0, 6).map((ticket) => (
                        <tr key={ticket.id} className="transition-colors hover:bg-slate-50/80">
                          <td className="overflow-hidden px-4 py-3.5 align-middle">
                            <Link to={`/tickets/${ticket.id}`} title={ticket.ticket_number} className="block max-w-full truncate whitespace-nowrap text-sm font-semibold text-blue-700 hover:underline">{ticket.ticket_number}</Link>
                          </td>
                          <td className="min-w-0 overflow-hidden px-4 py-3.5 align-middle">
                            <Link to={`/tickets/${ticket.id}`} title={ticket.subject} className="block max-w-full truncate text-sm font-medium text-slate-800 hover:text-blue-700">{ticket.subject}</Link>
                            {ticket.requester_email && <p className="mt-0.5 max-w-full truncate text-xs text-slate-500" title={ticket.requester_email}>{ticket.requester_email}</p>}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3.5 align-middle"><CategoryBadge category={ticket.category || ticket.classification || 'general'} /></td>
                          <td className="whitespace-nowrap px-4 py-3.5 align-middle"><StatusBadge status={ticket.status} /></td>
                          <td className="whitespace-nowrap px-4 py-3.5 align-middle"><PriorityBadge priority={ticket.priority} /></td>
                          <td className="whitespace-nowrap px-4 py-3.5 align-middle text-xs text-slate-500">
                            {new Date(ticket.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="divide-y divide-slate-100 md:hidden">
                  {data.results.slice(0, 5).map((ticket) => (
                    <Link key={ticket.id} to={`/tickets/${ticket.id}`} className="block px-4 py-4 hover:bg-slate-50">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-blue-700">{ticket.ticket_number}</p>
                          <p className="mt-1 truncate text-sm font-semibold text-slate-900">{ticket.subject}</p>
                          <p className="mt-0.5 truncate text-xs text-slate-500">{ticket.requester_email}</p>
                        </div>
                        <StatusBadge status={ticket.status} />
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <CategoryBadge category={ticket.category || ticket.classification || 'general'} />
                        <PriorityBadge priority={ticket.priority} />
                      </div>
                    </Link>
                  ))}
                </div>
                <div className="border-t border-slate-200 px-4 py-3 text-right">
                  <Link to="/tickets" className="text-sm font-medium text-blue-700 hover:underline">Open ticket inbox</Link>
                </div>
              </>
            )}
          </section>
        </div>
      </main>
    </>
  );
};

export default Home;
