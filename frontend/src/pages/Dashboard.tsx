import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  PieChart,
  Pie,
  Legend,
} from 'recharts';
import NavBar from '../components/NavBar';
import { apiJson } from '../api';
import { AnalyticsOverview } from '../types';

const CATEGORY_COLORS: Record<string, string> = {
  general: '#64748b',   // slate
  technical: '#8b5cf6', // purple
  refund: '#10b981',    // emerald
};

const AI_COLORS = ['#3b82f6', '#cbd5e1']; // blue (accepted), slate (pending)

const Dashboard: React.FC = () => {
  const [days, setDays] = useState<number>(14);

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['analytics-overview', days],
    queryFn: () => apiJson<AnalyticsOverview>(`/api/analytics/overview?days=${days}`),
  });

  const formattedTrendData = React.useMemo(() => {
    if (!data?.tickets_per_day) return [];
    return data.tickets_per_day.map((item) => {
      const d = new Date(item.date);
      const label = isNaN(d.getTime())
        ? item.date
        : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      return {
        ...item,
        displayDate: label,
      };
    });
  }, [data?.tickets_per_day]);

  const aiPieData = React.useMemo(() => {
    if (!data?.ai_suggestions) return [];
    const { accepted, pending } = data.ai_suggestions;
    return [
      { name: 'Accepted', value: accepted },
      { name: 'Pending / Not Accepted', value: pending },
    ];
  }, [data?.ai_suggestions]);

  return (
    <div className="min-h-screen bg-slate-50">
      <NavBar />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header & Controls */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 sm:p-8 mb-8 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-semibold mb-2">
                Operational Intelligence
              </div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Support & AI Analytics Dashboard
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Real-time visibility into ticket volumes, agent responsiveness, and AI suggestion impact.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center bg-slate-100 p-1 rounded-xl">
                {([7, 14, 30] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDays(d)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                      days === d
                        ? 'bg-white text-blue-700 shadow-sm'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Last {d}d
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => void refetch()}
                disabled={isFetching}
                className="inline-flex items-center gap-2 px-3.5 py-2 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition cursor-pointer disabled:opacity-50"
              >
                <svg
                  className={`w-4 h-4 text-slate-500 ${isFetching ? 'animate-spin' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                {isFetching ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>
        </div>

        {error ? (
          <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center text-red-700">
            <p className="font-semibold text-base">Failed to load analytics data</p>
            <p className="text-sm text-red-600 mt-1">
              {error instanceof Error ? error.message : 'Unknown error occurred.'}
            </p>
            <button
              onClick={() => void refetch()}
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700 cursor-pointer"
            >
              Retry
            </button>
          </div>
        ) : isLoading ? (
          <div className="p-16 text-center text-slate-500 flex flex-col items-center justify-center gap-3 bg-white rounded-2xl border border-slate-200/80">
            <svg className="animate-spin h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
            <span className="text-sm font-medium">Aggregating workspace analytics...</span>
          </div>
        ) : data ? (
          <>
            {/* KPI Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
              {/* Total Tickets */}
              <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Total Volume
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                    </svg>
                  </div>
                </div>
                <p className="text-3xl font-extrabold text-slate-900 mt-2">{data.total_tickets}</p>
                <div className="mt-2 text-xs text-slate-500 flex items-center gap-2">
                  <span className="text-blue-600 font-medium">{data.open_tickets} open</span>
                  <span>•</span>
                  <span className="text-emerald-600 font-medium">{data.resolved_tickets} resolved</span>
                </div>
              </div>

              {/* Average First-Reply Time */}
              <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Avg First-Reply Time
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
                <p className="text-3xl font-extrabold text-slate-900 mt-2">
                  {data.average_first_reply_time_formatted}
                </p>
                <div className="mt-2 text-xs text-slate-500">
                  {data.average_first_reply_time_minutes > 0
                    ? `~${data.average_first_reply_time_minutes} minutes on average`
                    : 'Awaiting initial agent responses'}
                </div>
              </div>

              {/* AI Suggestion Acceptance Rate */}
              <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    AI Suggestion Acceptance
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                </div>
                <p className="text-3xl font-extrabold text-slate-900 mt-2">
                  {data.ai_suggestions.acceptance_rate}%
                </p>
                <div className="mt-2 text-xs text-slate-500">
                  <span className="font-medium text-slate-700">
                    {data.ai_suggestions.accepted}
                  </span>{' '}
                  accepted of {data.ai_suggestions.total} suggestions
                </div>
              </div>

              {/* Resolution Rate */}
              <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Resolution Status
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
                <p className="text-3xl font-extrabold text-slate-900 mt-2">
                  {data.total_tickets > 0
                    ? `${Math.round((data.resolved_tickets / data.total_tickets) * 100)}%`
                    : '0%'}
                </p>
                <div className="mt-2 text-xs text-slate-500">
                  {data.resolved_tickets} tickets resolved / closed
                </div>
              </div>
            </div>

            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              {/* Daily Ticket Trend (Area Chart) */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm lg:col-span-2">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-base font-bold text-slate-900">Tickets per Day</h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Daily volume of newly created customer tickets
                    </p>
                  </div>
                </div>

                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={formattedTrendData}
                      margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient id="ticketTrendGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis
                        dataKey="displayDate"
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#ffffff',
                          borderRadius: '0.75rem',
                          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                          borderColor: '#e2e8f0',
                          fontSize: '0.75rem',
                        }}
                        formatter={(val: number) => [`${val} tickets`, 'Volume']}
                        labelFormatter={(_, payload) => {
                          const item = payload?.[0]?.payload as { date?: string } | undefined;
                          return item?.date ? `Date: ${item.date}` : '';
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="count"
                        stroke="#2563eb"
                        strokeWidth={2.5}
                        fillOpacity={1}
                        fill="url(#ticketTrendGradient)"
                        activeDot={{ r: 6, fill: '#1d4ed8' }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* AI Suggestion Acceptance Breakdown */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex flex-col">
                <h2 className="text-base font-bold text-slate-900">AI Suggestion Adoption</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Proportion of drafted replies accepted by agents
                </p>

                <div className="flex-1 min-h-[220px] flex items-center justify-center">
                  {data.ai_suggestions.total === 0 ? (
                    <div className="text-center text-slate-400 text-xs py-8">
                      No AI suggested replies generated yet.
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={220}>
                      <PieChart>
                        <Pie
                          data={aiPieData}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
                          paddingAngle={3}
                        >
                          {aiPieData.map((_, index) => (
                            <Cell key={`cell-${index}`} fill={AI_COLORS[index % AI_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#ffffff',
                            borderRadius: '0.5rem',
                            borderColor: '#e2e8f0',
                            fontSize: '0.75rem',
                          }}
                        />
                        <Legend
                          verticalAlign="bottom"
                          iconType="circle"
                          wrapperStyle={{ fontSize: '0.75rem', paddingTop: '10px' }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </div>

                <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 gap-2 text-center">
                  <div className="bg-blue-50/60 p-2.5 rounded-lg">
                    <span className="text-xs text-blue-600 font-medium">Accepted</span>
                    <p className="text-lg font-bold text-blue-700">{data.ai_suggestions.accepted}</p>
                  </div>
                  <div className="bg-slate-50 p-2.5 rounded-lg">
                    <span className="text-xs text-slate-500 font-medium">Draft / Pending</span>
                    <p className="text-lg font-bold text-slate-700">{data.ai_suggestions.pending}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Second Row: Category & Priority Distributions */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Category Distribution */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">Tickets by Category</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Automated and manual classification distribution
                </p>

                <div className="h-60 w-full mt-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={data.categories}
                      margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#ffffff',
                          borderRadius: '0.5rem',
                          borderColor: '#e2e8f0',
                          fontSize: '0.75rem',
                        }}
                        formatter={(val: number) => [`${val} tickets`, 'Count']}
                      />
                      <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                        {data.categories.map((entry) => (
                          <Cell
                            key={`cat-${entry.category}`}
                            fill={CATEGORY_COLORS[entry.category] || '#3b82f6'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Priority Breakdown */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">Tickets by Priority</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Severity distribution across active tickets
                </p>

                <div className="h-60 w-full mt-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={data.priorities}
                      margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis
                        dataKey="priority"
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                        tickFormatter={(val: string) => val.charAt(0).toUpperCase() + val.slice(1)}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#ffffff',
                          borderRadius: '0.5rem',
                          borderColor: '#e2e8f0',
                          fontSize: '0.75rem',
                        }}
                        formatter={(val: number) => [`${val} tickets`, 'Count']}
                      />
                      <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                        {data.priorities.map((entry) => {
                          const color =
                            entry.priority === 'high'
                              ? '#ef4444'
                              : entry.priority === 'medium'
                              ? '#f59e0b'
                              : '#10b981';
                          return <Cell key={`prio-${entry.priority}`} fill={color} />;
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
};

export default Dashboard;
