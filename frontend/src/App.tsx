import React, { useEffect, useState, useContext } from 'react';
import NavBar from './components/NavBar';
import { AuthContext } from './context/AuthContext';

interface Ticket {
  id: number;
  ticket_number: string;
  subject: string;
  requester_email?: string;
  status: string;
  priority: string;
  category?: string;
  created_at: string;
  updated_at?: string;
}

const App: React.FC = () => {
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
  const auth = useContext(AuthContext);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchTickets = () => {
    setLoading(true);
    setError(null);
    fetch(`${API_BASE_URL}/api/tickets/`, {
      credentials: 'include',
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load tickets (HTTP ${res.status})`);
        }
        return res.json();
      })
      .then((data) => {
        // DRF may return an array or paginated object { results: [...] }
        if (Array.isArray(data)) {
          setTickets(data);
        } else if (data && Array.isArray(data.results)) {
          setTickets(data.results);
        } else {
          setTickets([]);
        }
      })
      .catch((err) => {
        console.error('Failed to fetch tickets:', err);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (auth?.user) {
      fetchTickets();
    }
  }, [auth?.user]);

  const filteredTickets = tickets.filter((t) => {
    const matchesStatus = filterStatus === 'all' || t.status.toLowerCase() === filterStatus.toLowerCase();
    const matchesSearch =
      searchQuery === '' ||
      t.ticket_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (t.requester_email && t.requester_email.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesStatus && matchesSearch;
  });

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
              <button
                onClick={fetchTickets}
                className="inline-flex items-center gap-2 px-3.5 py-2 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition cursor-pointer"
              >
                <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

        {/* Filter and Search Bar */}
        <div className="bg-white border border-slate-200/80 rounded-2xl shadow-sm overflow-hidden mb-6">
          <div className="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row gap-4 sm:items-center sm:justify-between">
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

            {/* Filter by status */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
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
          </div>

          {/* Tickets Table / List */}
          {error ? (
            <div className="p-6 text-center">
              <p className="text-sm text-red-600">{error}</p>
              <button
                onClick={fetchTickets}
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
                {searchQuery || filterStatus !== 'all'
                  ? 'Try adjusting your search query or status filter.'
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
                      Status
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Priority
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Created
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-slate-100">
                  {filteredTickets.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50/80 transition">
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-blue-600">
                        {t.ticket_number}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-900">
                        <div className="font-medium text-slate-900">{t.subject}</div>
                        {t.requester_email && (
                          <div className="text-xs text-slate-400 mt-0.5">{t.requester_email}</div>
                        )}
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
