import React, { FormEvent, useCallback, useContext, useEffect, useState } from 'react';
import { LoaderCircle, Mail, MessageCircle, Save, Sparkles, Trash2, UserPlus, Users } from 'lucide-react';
import { Navigate } from 'react-router-dom';

import { AuthContext } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import NavBar from '@/components/NavBar';
import { PageHeader } from '@/components/ui/PageHeader';
import { apiFetch } from '@/api';

interface Agent {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
}

interface AutoResolutionSettings {
  enabled: boolean;
  email_auto_reply: boolean;
  whatsapp_auto_reply: boolean;
  simulation_mode: boolean;
  minimum_threshold: number;
  changed_at: string;
  changed_by: string | null;
  stats: {
    auto_resolved_today: number;
    auto_resolved_this_week: number;
    sent_successfully: number;
    sent_failed: number;
    sent_to_agent_review: number;
  };
}

type AutoResolutionSettingsDraft = Pick<
  AutoResolutionSettings,
  'enabled' | 'email_auto_reply' | 'whatsapp_auto_reply' | 'simulation_mode' | 'minimum_threshold'
>;

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

async function getCsrfToken(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/auth/csrf/`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Unable to initialize a secure request.');
  }
  const data: { csrfToken: string } = await response.json();
  return data.csrfToken;
}

async function getErrorMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  if (body && typeof body === 'object') {
    const values = Object.values(body).flat();
    const message = values.find((value) => typeof value === 'string');
    if (message) {
      return message;
    }
  }
  return `Request failed (HTTP ${response.status}).`;
}

const AdminAgents: React.FC = () => {
  const auth = useContext(AuthContext);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [autoResolutionSettings, setAutoResolutionSettings] = useState<AutoResolutionSettings | null>(null);
  const [autoResolutionDraft, setAutoResolutionDraft] = useState<AutoResolutionSettingsDraft | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch('/api/agents/');
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      const data: Agent[] | { results: Agent[] } = await response.json();
      setAgents(Array.isArray(data) ? data : data.results);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load agents.');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAutoResolutionSettings = useCallback(async () => {
    setSettingsLoading(true);
    setSettingsError(null);
    try {
      const response = await apiFetch('/api/admin/auto-resolution/');
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      const data: AutoResolutionSettings = await response.json();
      setAutoResolutionSettings(data);
      setAutoResolutionDraft({
        enabled: data.enabled,
        email_auto_reply: data.email_auto_reply,
        whatsapp_auto_reply: data.whatsapp_auto_reply,
        simulation_mode: data.simulation_mode,
        minimum_threshold: data.minimum_threshold,
      });
    } catch (requestError) {
      setSettingsError(requestError instanceof Error ? requestError.message : 'Unable to load auto-resolution settings.');
    } finally {
      setSettingsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth?.user?.role === 'ADMIN') {
      void loadAgents();
      void loadAutoResolutionSettings();
    }
  }, [auth?.user?.role, loadAgents, loadAutoResolutionSettings]);

  if (!auth || auth.loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <LoaderCircle className="size-6 animate-spin" aria-label="Loading" />
      </main>
    );
  }
  if (!auth.user) {
    return <Navigate to="/login" replace />;
  }
  if (auth.user.role !== 'ADMIN') {
    return <Navigate to="/" replace />;
  }

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const csrfToken = await getCsrfToken();
      const response = await apiFetch('/api/agents/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim(),
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          password,
          role: 'AGENT',
        }),
      });
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      setUsername('');
      setEmail('');
      setFirstName('');
      setLastName('');
      setPassword('');
      setNotice('Agent account created.');
      await loadAgents();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to create agent.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (agent: Agent) => {
    if (!window.confirm(`Delete agent "${agent.username}"? This cannot be undone.`)) {
      return;
    }
    setDeletingId(agent.id);
    setError(null);
    setNotice(null);
    try {
      const csrfToken = await getCsrfToken();
      const response = await apiFetch(`/api/agents/${agent.id}/`, {
        method: 'DELETE',
        headers: { 'X-CSRFToken': csrfToken },
      });
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      setAgents((current) => current.filter((item) => item.id !== agent.id));
      setNotice('Agent account deleted.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to delete agent.');
    } finally {
      setDeletingId(null);
    }
  };

  const saveAutoResolutionSettings = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!autoResolutionDraft) return;
    setSettingsSaving(true);
    setSettingsError(null);
    try {
      const csrfToken = await getCsrfToken();
      const response = await apiFetch('/api/admin/auto-resolution/', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify(autoResolutionDraft),
      });
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      const data: AutoResolutionSettings = await response.json();
      setAutoResolutionSettings(data);
      setAutoResolutionDraft({
        enabled: data.enabled,
        email_auto_reply: data.email_auto_reply,
        whatsapp_auto_reply: data.whatsapp_auto_reply,
        simulation_mode: data.simulation_mode,
        minimum_threshold: data.minimum_threshold,
      });
    } catch (requestError) {
      setSettingsError(requestError instanceof Error ? requestError.message : 'Unable to save auto-resolution settings.');
    } finally {
      setSettingsSaving(false);
    }
  };

  const updateAutoResolutionMasterSwitch = async (enabled: boolean) => {
    if (!autoResolutionDraft || settingsSaving) return;
    setSettingsSaving(true);
    setSettingsError(null);
    setAutoResolutionDraft((current) => current && ({
      ...current,
      enabled,
    }));
    try {
      const csrfToken = await getCsrfToken();
      const response = await apiFetch('/api/admin/auto-resolution/', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      const data: AutoResolutionSettings = await response.json();
      setAutoResolutionSettings(data);
      setAutoResolutionDraft((current) => current && ({
        ...current,
        enabled: data.enabled,
      }));
    } catch (requestError) {
      setAutoResolutionDraft((current) => current && ({
        ...current,
        enabled: autoResolutionSettings?.enabled ?? !enabled,
      }));
      setSettingsError(requestError instanceof Error ? requestError.message : 'Unable to update auto-resolution status.');
    } finally {
      setSettingsSaving(false);
    }
  };

  return (
    <>
    <NavBar />
    <main className="app-main">
      <div className="mx-auto max-w-[1200px]">
        <PageHeader
          eyebrow="Administration"
          title="Agent management"
          description="Create and remove agent accounts. Only administrators can access this page."
        />

        {error && (
          <div className="mb-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="mb-5 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700" role="status">
            {notice}
          </div>
        )}

        <section className="mb-5 rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <Sparkles className="size-5 text-blue-600" aria-hidden="true" />
              <div>
                <h2 className="font-semibold text-slate-900">AI Auto-Resolution</h2>
                <p className="text-sm text-slate-500">Configure safe automatic responses to newly received tickets.</p>
              </div>
            </div>
            {autoResolutionSettings && (
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${autoResolutionSettings.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                {autoResolutionSettings.enabled ? 'ON' : 'OFF'}
              </span>
            )}
          </div>

          {settingsError && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
              {settingsError}
            </div>
          )}

          {settingsLoading ? (
            <div className="flex items-center gap-2 py-5 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Loading settings...
            </div>
          ) : !autoResolutionDraft || !autoResolutionSettings ? (
            <Button type="button" variant="outline" onClick={() => void loadAutoResolutionSettings()}>
              Retry loading settings
            </Button>
          ) : (
            <>
              <form className="space-y-5" onSubmit={(event) => void saveAutoResolutionSettings(event)}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                    <span className="font-medium text-slate-800">Master switch</span>
                    <input
                      aria-label="AI Auto-Resolution master switch"
                      type="checkbox"
                      checked={autoResolutionDraft.enabled}
                      disabled={settingsSaving}
                      onChange={(event) => void updateAutoResolutionMasterSwitch(event.target.checked)}
                      className="size-4 accent-blue-600"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                    <span className="flex items-center gap-2 text-sm text-slate-700"><Mail className="size-4" aria-hidden="true" /> Email Auto-Reply</span>
                    <input
                      aria-label="Email Auto-Reply"
                      type="checkbox"
                      checked={autoResolutionDraft.email_auto_reply}
                      onChange={(event) => setAutoResolutionDraft({ ...autoResolutionDraft, email_auto_reply: event.target.checked })}
                      className="size-4 accent-blue-600"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                    <span className="flex items-center gap-2 text-sm text-slate-700"><MessageCircle className="size-4" aria-hidden="true" /> WhatsApp Auto-Reply</span>
                    <input
                      aria-label="WhatsApp Auto-Reply"
                      type="checkbox"
                      checked={autoResolutionDraft.whatsapp_auto_reply}
                      onChange={(event) => setAutoResolutionDraft({ ...autoResolutionDraft, whatsapp_auto_reply: event.target.checked })}
                      className="size-4 accent-blue-600"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                    <span className="font-medium text-slate-800">Simulation / dry-run</span>
                    <input
                      aria-label="Simulation mode"
                      type="checkbox"
                      checked={autoResolutionDraft.simulation_mode}
                      onChange={(event) => setAutoResolutionDraft({ ...autoResolutionDraft, simulation_mode: event.target.checked })}
                      className="size-4 accent-blue-600"
                    />
                  </label>
                </div>
                <p className="text-xs text-slate-500">
                  WhatsApp generated replies currently remain in agent review because the configured Meta integration sends only approved fixed templates.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="text-sm font-medium text-slate-700" htmlFor="auto-resolution-threshold">
                    Minimum similarity / confidence
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="auto-resolution-threshold"
                      className="w-24"
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={Math.round(autoResolutionDraft.minimum_threshold * 100)}
                      onChange={(event) => setAutoResolutionDraft({
                        ...autoResolutionDraft,
                        minimum_threshold: Number(event.target.value) / 100,
                      })}
                    />
                    <span className="text-sm text-slate-500">%</span>
                  </div>
                  <Button type="submit" disabled={settingsSaving} className="sm:ml-auto">
                    {settingsSaving ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
                    {settingsSaving ? 'Saving...' : 'Save settings'}
                  </Button>
                </div>
              </form>

              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-slate-100 pt-4 text-xs text-slate-500">
                <span>Runtime status: {autoResolutionSettings.enabled ? 'ON' : 'OFF'}</span>
                <span>Mode: {autoResolutionSettings.simulation_mode ? 'Simulation' : 'Live delivery'}</span>
                <span>Last changed: {new Date(autoResolutionSettings.changed_at).toLocaleString()}</span>
                {autoResolutionSettings.changed_by && <span>By {autoResolutionSettings.changed_by}</span>}
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {[
                  ['Auto-resolved today', autoResolutionSettings.stats.auto_resolved_today],
                  ['Auto-resolved this week', autoResolutionSettings.stats.auto_resolved_this_week],
                  ['Sent successfully', autoResolutionSettings.stats.sent_successfully],
                  ['Send failed', autoResolutionSettings.stats.sent_failed],
                  ['Sent to agent review', autoResolutionSettings.stats.sent_to_agent_review],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xl font-semibold text-slate-900">{value}</div>
                    <div className="text-xs text-slate-500">{label}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="mb-5 rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
          <div className="mb-5 flex items-center gap-3">
            <UserPlus className="size-5 text-blue-600" aria-hidden="true" />
            <div>
              <h2 className="font-semibold text-slate-900">Create an agent</h2>
              <p className="text-sm text-slate-500">New accounts are created with the Agent role.</p>
            </div>
          </div>
          <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" onSubmit={handleCreate}>
            <div className="space-y-2">
              <Label htmlFor="agent-username">Username</Label>
              <Input id="agent-username" value={username} onChange={(event) => setUsername(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-email">Email</Label>
              <Input id="agent-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-password">Temporary password</Label>
              <Input
                id="agent-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-first-name">First name</Label>
              <Input id="agent-first-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-last-name">Last name</Label>
              <Input id="agent-last-name" value={lastName} onChange={(event) => setLastName(event.target.value)} />
            </div>
            <div className="flex items-end">
              <Button className="w-full sm:w-auto" type="submit" disabled={saving}>
                {saving ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <UserPlus aria-hidden="true" />}
                {saving ? 'Creating...' : 'Create agent'}
              </Button>
            </div>
          </form>
        </section>

        <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-4">
            <Users className="size-5 text-slate-500" aria-hidden="true" />
            <div>
              <h2 className="font-semibold text-slate-900">Agents</h2>
              <p className="text-sm text-slate-500">{agents.length} account{agents.length === 1 ? '' : 's'}</p>
            </div>
          </div>
          {loading ? (
            <div className="flex items-center justify-center gap-2 p-10 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Loading agents...
            </div>
          ) : agents.length === 0 ? (
            <p className="p-10 text-center text-sm text-slate-500">No agents have been created yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-6 py-3">Agent</th>
                    <th className="px-6 py-3">Email</th>
                    <th className="px-6 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {agents.map((agent) => (
                    <tr key={agent.id}>
                      <td className="px-6 py-4 text-sm font-medium text-slate-900">
                        {[agent.first_name, agent.last_name].filter(Boolean).join(' ') || agent.username}
                        <span className="ml-2 text-xs font-normal text-slate-500">@{agent.username}</span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-600">{agent.email || '—'}</td>
                      <td className="px-6 py-4 text-right">
                        <Button
                          variant="destructive"
                          size="sm"
                          type="button"
                          disabled={deletingId === agent.id}
                          onClick={() => void handleDelete(agent)}
                        >
                          {deletingId === agent.id ? (
                            <LoaderCircle className="animate-spin" aria-hidden="true" />
                          ) : (
                            <Trash2 aria-hidden="true" />
                          )}
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
    </>
  );
};

export default AdminAgents;
