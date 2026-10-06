import React, { useState, useContext } from 'react';
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
import { AuthContext } from '../context/AuthContext';
import { apiJson } from '../api';
import { AnalyticsOverview } from '../types';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/button';

const CATEGORY_COLORS: Record<string, string> = {
  general: '#64748b',
  technical: '#2563eb',
  refund: '#0f766e',
};

const AI_COLORS = ['#3b82f6', '#cbd5e1']; // blue (accepted), slate (pending)

const Dashboard: React.FC = () => {
  const auth = useContext(AuthContext);
  const [days, setDays] = useState<number>(14);

  const isStaffOrAgent = auth?.user?.role === 'ADMIN' || auth?.user?.role === 'AGENT';

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['analytics-overview', days],
    queryFn: () => apiJson<AnalyticsOverview>(`/api/analytics/overview?days=${days}`),
    enabled: Boolean(auth?.user && isStaffOrAgent),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
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
    <>
      <NavBar />

      <main className="app-main">
       <div className="mx-auto max-w-[1440px]">
        {/* Header & Controls */}
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <PageHeader
            title="Analytics"
            description="Monitor ticket volume, response times, and AI suggestion adoption."
          />
          <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1 rounded-md border border-slate-200 bg-white p-1">
                {([7, 14, 30] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDays(d)}
                    aria-pressed={days === d}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition cursor-pointer ${
                      days === d
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {d} days
                  </button>
                ))}
              </div>

              <Button
                type="button"
                onClick={() => void refetch()}
                disabled={isFetching}
                variant="outline"
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
              </Button>
          </div>
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-white p-8 text-center text-red-700">
            <p className="font-semibold text-base">Failed to load analytics data</p>
            <p className="text-sm text-red-600 mt-1">
              {error instanceof Error ? error.message : 'Unknown error occurred.'}
            </p>
            <button
              onClick={() => void refetch()}
              className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            >
              Retry
            </button>
          </div>
        ) : isLoading ? (
          <div className="space-y-4" aria-label="Loading analytics">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }, (_, index) => <div key={index} className="h-24 animate-pulse rounded-lg border border-slate-200 bg-white" />)}
            </div>
            <div className="grid gap-4 xl:grid-cols-3">
              <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white xl:col-span-2" />
              <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />
            </div>
          </div>
        ) : data ? (
          <>
            {/* KPI Summary Cards */}
            <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {/* Total Tickets */}
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Total Volume
                  </span>
                  <div className="flex size-8 items-center justify-center rounded-md bg-blue-50 text-blue-600">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                    </svg>
                  </div>
                </div>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{data.total_tickets}</p>
                <div className="mt-2 text-xs text-slate-500 flex items-center gap-2">
                  <span className="text-blue-600 font-medium">{data.open_tickets} open</span>
                  <span>•</span>
                  <span className="text-emerald-600 font-medium">{data.resolved_tickets} resolved</span>
                </div>
              </div>

              {/* Average First-Reply Time */}
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Avg First-Reply Time
                  </span>
                  <div className="flex size-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-600">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
                  {data.average_first_reply_time_formatted}
                </p>
                <div className="mt-2 text-xs text-slate-500">
                  {data.average_first_reply_time_minutes > 0
                    ? `~${data.average_first_reply_time_minutes} minutes on average`
                    : 'Awaiting initial agent responses'}
                </div>
              </div>

              {/* AI Suggestion Acceptance Rate */}
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    AI Suggestion Acceptance
                  </span>
                  <div className="flex size-8 items-center justify-center rounded-md bg-blue-50 text-blue-600">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                </div>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
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
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Resolution Status
                  </span>
                  <div className="flex size-8 items-center justify-center rounded-md bg-amber-50 text-amber-700">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
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
            <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-3">
              {/* Daily Ticket Trend (Area Chart) */}
              <div className="rounded-lg border border-slate-200 bg-white p-4 sm:p-5 xl:col-span-2">
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
                        formatter={(val: any) => [`${val ?? 0} tickets`, 'Volume']}
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
              <div className="flex flex-col rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
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
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {/* Category Distribution */}
              <div className="rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
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
                        formatter={(val: any) => [`${val ?? 0} tickets`, 'Count']}
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
              <div className="rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
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
                        formatter={(val: any) => [`${val ?? 0} tickets`, 'Count']}
                      />
                      <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                        {data.priorities.map((entry) => {
                          const color =
                            entry.priority === 'urgent'
                              ? '#dc2626'
                              : entry.priority === 'high'
                              ? '#ea580c'
                              : entry.priority === 'medium'
                              ? '#f59e0b'
                              : '#64748b';
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
       </div>
      </main>
    </>
  );
};

export default Dashboard;
