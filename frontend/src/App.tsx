import React, { useContext, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, BarChart3, ChevronLeft, ChevronRight, LoaderCircle, Mail, RefreshCw, Search, Ticket as TicketIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import NavBar from './components/NavBar';
import { AuthContext } from './context/AuthContext';
import { apiJson, getCsrfToken } from './api';
import { Ticket } from './types';
import { CategoryBadge, PriorityBadge, StatusBadge } from './components/ui/Badge';
import { EmptyState } from './components/ui/EmptyState';
import { PageHeader } from './components/ui/PageHeader';
import { Button } from './components/ui/button';

const TICKETS_PER_PAGE = 30;

interface PaginatedTickets {
  count: number;
  next: string | null;
  previous: string | null;
  results: Ticket[];
  stats: {
    total: number;
    open: number;
    high_urgent: number;
    resolved: number;
  };
}

const App: React.FC = () => {
  const auth = useContext(AuthContext);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [filterPriority, setFilterPriority] = useState<'all' | 'high-urgent'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [page, setPage] = useState(1);
  const [isSyncingEmail, setIsSyncingEmail] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const ticketsQuery = useQuery({
    queryKey: ['tickets', page, filterStatus, filterCategory, filterPriority, searchQuery, sortOrder],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        ordering: sortOrder === 'desc' ? '-created_at' : 'created_at',
      });
      if (filterStatus !== 'all') params.set('status', filterStatus);
      if (filterCategory !== 'all') params.set('category', filterCategory);
      if (filterPriority === 'high-urgent') params.set('priority__in', 'high,urgent');
      if (searchQuery.trim()) params.set('search', searchQuery.trim());
      return apiJson<PaginatedTickets>(`/api/tickets/?${params.toString()}`);
    },
    enabled: Boolean(auth?.user),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
  });

  const tickets = ticketsQuery.data?.results ?? [];
  const totalTickets = ticketsQuery.data?.count ?? 0;
  const firstTicketOnPage = totalTickets === 0 ? 0 : (page - 1) * TICKETS_PER_PAGE + 1;
  const lastTicketOnPage = Math.min(page * TICKETS_PER_PAGE, totalTickets);
  const setStatus = (status: string) => {
    setFilterStatus(status);
    setPage(1);
  };
  const toggleSort = () => {
    setSortOrder((previous) => (previous === 'desc' ? 'asc' : 'desc'));
    setPage(1);
  };

  const refreshTickets = async () => {
    setIsSyncingEmail(true);
    setRefreshMessage(null);
    try {
      const csrfToken = await getCsrfToken();
      const result = await apiJson<{ matched: number; created: number; skipped: number; errors: number }>(
        '/api/email-ingestion/sync/',
        { method: 'POST', headers: { 'X-CSRFToken': csrfToken } },
      );
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ['tickets'] });
      setRefreshMessage(
        `Mailbox checked: ${result.matched} matched, ${result.created} created, ${result.skipped} duplicate${result.skipped === 1 ? '' : 's'} skipped, ${result.errors} error${result.errors === 1 ? '' : 's'}.`,
      );
    } catch (refreshError) {
      setRefreshMessage(
        refreshError instanceof Error
          ? refreshError.message
          : 'Unable to refresh tickets from the support mailbox.',
      );
      await ticketsQuery.refetch();
    } finally {
      setIsSyncingEmail(false);
    }
  };

  const statCards = [
    { label: 'Total tickets', value: ticketsQuery.data?.stats.total, icon: TicketIcon, color: 'text-slate-500' },
    { label: 'Open tickets', value: ticketsQuery.data?.stats.open, icon: LoaderCircle, color: 'text-blue-600' },
    { label: 'High / urgent', value: ticketsQuery.data?.stats.high_urgent, icon: BarChart3, color: 'text-orange-600' },
    { label: 'Resolved', value: ticketsQuery.data?.stats.resolved, icon: TicketIcon, color: 'text-emerald-600' },
  ];

  return (
    <>
      <NavBar />
      <main className="app-main">
        <div className="mx-auto max-w-[1440px]">
          <PageHeader
            title="Tickets"
            description={`${totalTickets} total · ${ticketsQuery.data?.stats.open ?? 0} open · ${ticketsQuery.data?.stats.resolved ?? 0} resolved`}
            actions={
              <>
                <Link
                  to="/dashboard"
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  <BarChart3 className="size-4" aria-hidden="true" />
                  Analytics
                </Link>
                <Button
                  type="button"
                  variant="outline"
                  disabled={ticketsQuery.isFetching || isSyncingEmail}
                  onClick={() => void refreshTickets()}
                  aria-label={isSyncingEmail ? 'Checking mailbox and refreshing tickets' : 'Refresh tickets'}
                >
                  <RefreshCw className={`size-4 ${isSyncingEmail || ticketsQuery.isFetching ? 'animate-spin' : ''}`} aria-hidden="true" />
                  {isSyncingEmail ? 'Checking mail…' : 'Refresh'}
                </Button>
              </>
            }
          />

          {refreshMessage && (
            <p className="mb-4 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800" role="status" aria-live="polite">
              {refreshMessage}
            </p>
          )}

          <section aria-label="Ticket overview" className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
            {statCards.map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-slate-500">{label}</p>
                  <Icon className={`size-4 ${color}`} aria-hidden="true" />
                </div>
                <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
                  {value ?? (ticketsQuery.isLoading ? '—' : 0)}
                </p>
              </div>
            ))}
          </section>

          <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <div className="space-y-4 border-b border-slate-200 p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <label className="relative block w-full lg:max-w-md">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                  <input
                    type="search"
                    value={searchQuery}
                    onChange={(event) => {
                      setSearchQuery(event.target.value);
                      setPage(1);
                    }}
                    placeholder="Search ticket, subject, or customer…"
                    aria-label="Search tickets"
                    className="h-9 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </label>
                <button
                  type="button"
                  onClick={toggleSort}
                  className="inline-flex h-9 w-fit items-center gap-2 rounded-md border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                  title="Toggle ticket creation date sort order"
                >
                  {sortOrder === 'desc' ? <ArrowDown className="size-4" aria-hidden="true" /> : <ArrowUp className="size-4" aria-hidden="true" />}
                  {sortOrder === 'desc' ? 'Newest first' : 'Oldest first'}
                </button>
              </div>

              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-1 overflow-x-auto" aria-label="Filter tickets by status">
                  {(['all', 'open', 'resolved', 'closed'] as const).map((status) => (
                    <button
                      type="button"
                      key={status}
                      onClick={() => setStatus(status)}
                      aria-pressed={filterStatus === status}
                      className={`shrink-0 rounded-md px-3 py-1.5 text-sm font-medium capitalize transition ${
                        filterStatus === status ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      {status === 'all' ? 'All statuses' : status}
                    </button>
                  ))}
                </div>
                <div className="flex flex-col gap-3 border-t border-slate-100 pt-3 sm:flex-row sm:flex-wrap sm:items-center">
                  <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
                    Category
                    <select
                      value={filterCategory}
                      onChange={(event) => {
                        setFilterCategory(event.target.value);
                        setPage(1);
                      }}
                      className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm font-normal text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                    >
                      <option value="all">All categories</option>
                      <option value="general">General</option>
                      <option value="technical">Technical</option>
                      <option value="refund">Refund</option>
                    </select>
                  </label>
                  <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
                    Priority
                    <select
                      value={filterPriority}
                      onChange={(event) => {
                        setFilterPriority(event.target.value as 'all' | 'high-urgent');
                        setPage(1);
                      }}
                      className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm font-normal text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                    >
                      <option value="all">All priorities</option>
                      <option value="high-urgent">High / urgent</option>
                    </select>
                  </label>
                  {(filterCategory !== 'all' || filterPriority !== 'all' || filterStatus !== 'all' || searchQuery) && (
                    <button
                      type="button"
                      onClick={() => {
                        setStatus('all');
                        setFilterCategory('all');
                        setFilterPriority('all');
                        setSearchQuery('');
                        setPage(1);
                      }}
                      className="w-fit text-xs font-medium text-blue-700 hover:text-blue-800 hover:underline"
                    >
                      Clear filters
                    </button>
                  )}
                </div>
              </div>
            </div>

            {ticketsQuery.isError ? (
              <div className="flex flex-col items-center justify-center gap-2 px-5 py-12 text-center">
                <p className="text-sm font-medium text-slate-800">Unable to load tickets</p>
                <p className="text-sm text-red-700">
                  {ticketsQuery.error instanceof Error ? ticketsQuery.error.message : 'Please try again.'}
                </p>
                <Button variant="outline" size="sm" onClick={() => void ticketsQuery.refetch()}>
                  Try again
                </Button>
              </div>
            ) : ticketsQuery.isLoading ? (
              <div className="space-y-3 p-4" aria-label="Loading tickets">
                {Array.from({ length: 6 }, (_, index) => (
                  <div key={index} className="grid grid-cols-4 gap-4 py-3">
                    <span className="h-4 animate-pulse rounded bg-slate-100" />
                    <span className="col-span-2 h-4 animate-pulse rounded bg-slate-100" />
                    <span className="h-4 animate-pulse rounded bg-slate-100" />
                  </div>
                ))}
              </div>
            ) : tickets.length === 0 ? (
              <EmptyState
                title="No tickets found"
                description={
                  searchQuery || filterStatus !== 'all' || filterCategory !== 'all' || filterPriority !== 'all'
                    ? 'Try adjusting your search or filters.'
                    : 'New customer support tickets will appear here.'
                }
                action={
                  searchQuery || filterStatus !== 'all' || filterCategory !== 'all' || filterPriority !== 'all' ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setStatus('all');
                        setFilterCategory('all');
                        setFilterPriority('all');
                        setSearchQuery('');
                        setPage(1);
                      }}
                    >
                      Clear filters
                    </Button>
                  ) : undefined
                }
              />
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
                        <th scope="col" className="whitespace-nowrap px-4 py-3">
                          <button type="button" onClick={toggleSort} className="inline-flex items-center gap-1 transition hover:text-slate-900">
                            Created
                            {sortOrder === 'desc' ? <ArrowDown className="size-3" aria-hidden="true" /> : <ArrowUp className="size-3" aria-hidden="true" />}
                          </button>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {tickets.map((ticket) => (
                        <tr key={ticket.id} className="transition-colors hover:bg-slate-50/80">
                          <td className="overflow-hidden px-4 py-3.5 align-middle">
                            <Link to={`/tickets/${ticket.id}`} title={ticket.ticket_number} className="block max-w-full truncate whitespace-nowrap text-sm font-semibold text-blue-700 hover:text-blue-800 hover:underline">
                              {ticket.ticket_number}
                            </Link>
                          </td>
                          <td className="min-w-0 overflow-hidden px-4 py-3.5 align-middle">
                            <Link to={`/tickets/${ticket.id}`} title={ticket.subject} className="block max-w-full truncate text-sm font-medium text-slate-800 hover:text-blue-700">
                              {ticket.subject}
                            </Link>
                            {ticket.requester_email && (
                              <p className="mt-0.5 max-w-full truncate text-xs text-slate-500" title={ticket.requester_email}>{ticket.requester_email}</p>
                            )}
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
                  {tickets.map((ticket) => (
                    <Link
                      key={ticket.id}
                      to={`/tickets/${ticket.id}`}
                      className="block px-4 py-4 transition-colors hover:bg-slate-50 focus-visible:bg-blue-50"
                    >
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
                        <span className="text-xs text-slate-500">
                          {new Date(ticket.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              </>
            )}

            {ticketsQuery.data && totalTickets > 0 && (
              <div className="flex flex-col gap-3 border-t border-slate-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-slate-500" aria-live="polite">
                  Showing {firstTicketOnPage}–{lastTicketOnPage} of {totalTickets} tickets
                </p>
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    disabled={!ticketsQuery.data.previous || ticketsQuery.isFetching}
                  >
                    <ChevronLeft className="size-4" aria-hidden="true" /> Previous
                  </Button>
                  <span className="text-xs text-slate-500">
                    Page {page} of {Math.ceil(totalTickets / TICKETS_PER_PAGE)}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((current) => current + 1)}
                    disabled={!ticketsQuery.data.next || ticketsQuery.isFetching}
                  >
                    Next <ChevronRight className="size-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>
    </>
  );
};

export default App;
