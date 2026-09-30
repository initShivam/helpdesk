import React, { useState, useContext, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import NavBar from './components/NavBar';
import { AuthContext } from './context/AuthContext';
import { Link } from 'react-router-dom';
import { apiJson } from './api';
import { Ticket } from './types';

const App: React.FC = () => {
  const auth = useContext(AuthContext);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');

  const ticketsQuery = useQuery({
    queryKey: ['tickets'],
    queryFn: async () => {
      const data = await apiJson<Ticket[] | { results: Ticket[] }>('/api/tickets/');
      return Array.isArray(data) ? data : data.results;
    },
    enabled: Boolean(auth?.user),
  });

  const tickets = ticketsQuery.data ?? [];
  const loading = ticketsQuery.isLoading;
  const error = ticketsQuery.error instanceof Error ? ticketsQuery.error.message : null;

  const filteredTickets = useMemo(() => {
    return tickets
      .filter((t) => {
        const matchesStatus =
          filterStatus === 'all' || t.status.toLowerCase() === filterStatus.toLowerCase();

        const cat = (t.category || t.classification || '').toLowerCase();
        const matchesCategory =
          filterCategory === 'all' || cat === filterCategory.toLowerCase();

        const matchesSearch =
          searchQuery === '' ||
          t.ticket_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (t.requester_email && t.requester_email.toLowerCase().includes(searchQuery.toLowerCase()));

        return matchesStatus && matchesCategory && matchesSearch;
      })
      .sort((a, b) => {
        const timeA = new Date(a.created_at).getTime();
        const timeB = new Date(b.created_at).getTime();
        return sortOrder === 'desc' ? timeB - timeA : timeA - timeB;
      });
  }, [tickets, filterStatus, filterCategory, searchQuery, sortOrder]);

  const getPriorityBadge = (priority: string) => {
    switch (priority?.toLowerCase()) {
      case 'high':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'medium':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'low':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'open':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'resolved':
      case 'closed':
        return 'bg-slate-100 text-slate-600 border-slate-200';
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }
  };

  const getCategoryBadge = (category?: string) => {
    switch (category?.toLowerCase()) {
      case 'technical':
        return 'bg-purple-50 text-purple-700 border-purple-200';
      case 'refund':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'general':
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const formatCategoryName = (category?: string) => {
    switch (category?.toLowerCase()) {
      case 'technical':
        return 'Technical';
      case 'refund':
        return 'Refund';
      case 'general':
      default:
        return 'General';
    }
  };

  const toggleSort = () => {
    setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'));
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <NavBar />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Welcome and Summary Banner */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 sm:p-8 mb-8 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Welcome back, {auth?.user?.username || 'Agent'} 👋
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Manage, monitor, and resolve customer support tickets across your channels.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 transition shadow-sm"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                View Analytics Dashboard
              </Link>
              <button
                type="button"
                onClick={() => void ticketsQuery.refetch()}
                disabled={ticketsQuery.isFetching}
                className="inline-flex items-center gap-2 px-3.5 py-2 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition cursor-pointer disabled:cursor-wait disabled:opacity-60"
                aria-label={ticketsQuery.isFetching ? 'Refreshing tickets' : 'Refresh tickets'}
              >
                <svg className={`w-4 h-4 text-slate-500 ${ticketsQuery.isFetching ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </button>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-100">
            <div className="bg-slate-50/70 p-3.5 rounded-xl border border-slate-100">
              <span className="text-xs font-medium text-slate-500">Total Tickets</span>
              <p className="text-2xl font-bold text-slate-900 mt-1">{tickets.length}</p>
            </div>
            <div className="bg-blue-50/50 p-3.5 rounded-xl border border-blue-100/50">
              <span className="text-xs font-medium text-blue-600">Open Tickets</span>
              <p className="text-2xl font-bold text-blue-700 mt-1">
                {tickets.filter((t) => t.status?.toLowerCase() === 'open').length}
              </p>
            </div>
            <div className="bg-amber-50/50 p-3.5 rounded-xl border border-amber-100/50">
              <span className="text-xs font-medium text-amber-600">High / Urgent</span>
              <p className="text-2xl font-bold text-amber-700 mt-1">
                {tickets.filter((t) => ['high', 'urgent'].includes(t.priority?.toLowerCase())).length}
              </p>
            </div>
            <div className="bg-emerald-50/50 p-3.5 rounded-xl border border-emerald-100/50">
              <span className="text-xs font-medium text-emerald-600">Resolved</span>
              <p className="text-2xl font-bold text-emerald-700 mt-1">
                {tickets.filter((t) => ['resolved', 'closed'].includes(t.status?.toLowerCase())).length}
              </p>
            </div>
          </div>
        </div>

        {/* Filter, Search, and Sort Bar */}
        <div className="bg-white border border-slate-200/80 rounded-2xl shadow-sm overflow-hidden mb-6">
          <div className="p-4 sm:p-5 border-b border-slate-100 flex flex-col gap-4">
            <div className="flex flex-col sm:flex-row gap-4 sm:items-center sm:justify-between">
              {/* Search */}
              <div className="relative flex-1 max-w-md">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search ticket #, subject, or email..."
                  className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition"
                />
              </div>

              {/* Sort Order Control */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-slate-500">Sort by date:</span>
                <button
                  type="button"
                  onClick={toggleSort}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-700 transition cursor-pointer"
                  title="Click to toggle creation date sort order"
                >
                  <svg className="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    {sortOrder === 'desc' ? (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    ) : (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                    )}
                  </svg>
                  {sortOrder === 'desc' ? 'Newest first' : 'Oldest first'}
                </button>
              </div>
            </div>

            {/* Filter Rows: Status and Category */}
            <div className="flex flex-wrap items-center justify-between gap-4 pt-3 border-t border-slate-100">
              {/* Filter by status */}
              <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
                <span className="text-xs font-medium text-slate-400 mr-1">Status:</span>
                {(['all', 'open', 'resolved', 'closed'] as const).map((st) => (
                  <button
                    key={st}
                    onClick={() => setFilterStatus(st)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer capitalize ${
                      filterStatus === st
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>

              {/* Filter by category */}
              <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
                <span className="text-xs font-medium text-slate-400 mr-1">Category:</span>
                {(
                  [
                    { id: 'all', label: 'All Categories' },
                    { id: 'general', label: 'General' },
                    { id: 'technical', label: 'Technical' },
                    { id: 'refund', label: 'Refund' },
                  ] as const
                ).map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setFilterCategory(cat.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
                      filterCategory === cat.id
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Tickets Table / List */}
          {error ? (
            <div className="p-6 text-center">
              <p className="text-sm text-red-600">{error}</p>
              <button
                onClick={() => void ticketsQuery.refetch()}
                className="mt-2 text-xs font-semibold text-blue-600 hover:underline cursor-pointer"
              >
                Try again
              </button>
            </div>
          ) : loading ? (
            <div className="p-12 text-center text-slate-500 flex flex-col items-center justify-center gap-3">
              <svg className="animate-spin h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
              </svg>
              <span className="text-sm">Loading tickets...</span>
            </div>
          ) : filteredTickets.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <svg className="w-12 h-12 text-slate-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-base font-medium text-slate-700">No tickets found</p>
              <p className="text-xs text-slate-400 mt-1">
                {searchQuery || filterStatus !== 'all' || filterCategory !== 'all'
                  ? 'Try adjusting your search query, status, or category filter.'
                  : 'New customer support tickets will appear here.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50/70">
                  <tr>
                    <th scope="col" className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Ticket
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Subject
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Category
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Priority
                    </th>
                    <th
                      scope="col"
                      onClick={toggleSort}
                      className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-800 select-none"
                    >
                      <div className="inline-flex items-center gap-1">
                        <span>Created</span>
                        <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          {sortOrder === 'desc' ? (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          ) : (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                          )}
                        </svg>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-slate-100">
                  {filteredTickets.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50/80 transition">
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-blue-600">
                        <Link to={`/tickets/${t.id}`} className="hover:underline">
                          {t.ticket_number}
                        </Link>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-900">
                        <div className="font-medium text-slate-900">{t.subject}</div>
                        {t.requester_email && (
                          <div className="text-xs text-slate-400 mt-0.5">{t.requester_email}</div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getCategoryBadge(t.category || t.classification)}`}>
                          {formatCategoryName(t.category || t.classification)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border capitalize ${getStatusBadge(t.status)}`}>
                          {t.status.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border capitalize ${getPriorityBadge(t.priority)}`}>
                          {t.priority}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-xs text-slate-500">
                        {new Date(t.created_at).toLocaleDateString(undefined, {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default App;
