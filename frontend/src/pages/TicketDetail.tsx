import React, { useContext, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Bot, CalendarDays, Check, Clock3, LoaderCircle, Paperclip, Send, Sparkles, WandSparkles } from 'lucide-react';
import { apiJson, API_BASE_URL, getCsrfToken } from '../api';
import { AuthContext } from '../context/AuthContext';
import NavBar from '../components/NavBar';
import { CategoryBadge, PriorityBadge, StatusBadge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/button';

interface Ticket {
  id: number;
  ticket_number: string;
  subject: string;
  requester_email: string;
  status: string;
  category: string;
  priority: string;
  ai_summary?: string | null;
  ai_category_confidence?: number | null;
  created_at: string;
  updated_at?: string;
  attachments?: Attachment[];
}

interface Attachment {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  download_url: string;
}

interface TicketMessage {
  id: number;
  body: string;
  message_type: string;
  sender?: number | null;
  created_at: string;
  is_ai_generated?: boolean;
  is_draft?: boolean;
}

const getResponseError = async (response: Response, fallback: string) => {
  try {
    const data = await response.json();
    return data.detail || data.error || fallback;
  } catch {
    return fallback;
  }
};

const TicketDetail: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const auth = useContext(AuthContext);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [resolutionNote, setResolutionNote] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [suggestionDraft, setSuggestionDraft] = useState('');
  const [whatsappNumber, setWhatsappNumber] = useState('');
  const [whatsappConsent, setWhatsappConsent] = useState(false);
  const [retryingWhatsAppId, setRetryingWhatsAppId] = useState<number | null>(null);
  const initializedWhatsAppContact = useRef<string | null>(null);

  const ticketQuery = useQuery({
    queryKey: ['ticket', id],
    queryFn: () => apiJson<Ticket>(`/api/tickets/${id}/`),
    enabled: Boolean(id),
  });
  const messagesQuery = useQuery({
    queryKey: ['ticket-messages', id],
    queryFn: async () => {
      const data = await apiJson<TicketMessage[] | { results: TicketMessage[] }>(`/api/tickets/${id}/messages/`);
      return Array.isArray(data) ? data : data.results;
    },
    enabled: Boolean(id),
  });
  const notificationQuery = useQuery({
    queryKey: ['resolution-notification', id],
    queryFn: () => apiJson<{ status: string; attempt_count: number; max_attempts: number; sent_at: string | null }>(`/api/tickets/${id}/resolution-notification/`),
    enabled: Boolean(id) && ticketQuery.data?.status === 'resolved',
    refetchInterval: (query) => ['pending', 'sending'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const whatsappQuery = useQuery({
    queryKey: ['whatsapp-notifications', id],
    queryFn: () => apiJson<{ contact: { number: string; consent: boolean }; notifications: Array<{ id: number; status: string; attempt_count: number; max_attempts: number; last_attempt_at: string | null; delivered_at: string | null; error_code: string; error_detail: string }> }>(`/api/tickets/${id}/whatsapp-notifications/`),
    enabled: Boolean(id),
    refetchInterval: (query) => query.state.data?.notifications.some((n) => ['pending', 'queued', 'sent'].includes(n.status)) ? 5000 : false,
  });
  useEffect(() => {
    if (whatsappQuery.data && initializedWhatsAppContact.current !== id) {
      setWhatsappNumber(whatsappQuery.data.contact.number || '');
      setWhatsappConsent(whatsappQuery.data.contact.consent);
      initializedWhatsAppContact.current = id ?? null;
    }
  }, [id, whatsappQuery.data]);
  const ticket = ticketQuery.data ?? null;
  const messages = messagesQuery.data ?? [];
  // Summaries already have their own panel above. They are persisted as system
  // messages for audit/history, so keep them out of the customer conversation.
  const conversationMessages = messages.filter(
    (message) => !(message.is_ai_generated && !message.is_draft && message.message_type === 'system'),
  );
  const setMessages = (updater: (current: TicketMessage[]) => TicketMessage[]) => {
    queryClient.setQueryData<TicketMessage[]>(['ticket-messages', id], (current = []) => updater(current));
  };
  const error = ticketQuery.error || messagesQuery.error;

  const updateTicket = async (status: string) => {
    if (!id) return;
    setActionError(null);
    setIsSaving(true);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify(status === 'resolved' ? { status, resolution_note: resolutionNote.trim() } : { status }),
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response, 'Unable to update the ticket status.'));
      }
      await queryClient.invalidateQueries({ queryKey: ['ticket', id] });
      await queryClient.invalidateQueries({ queryKey: ['resolution-notification', id] });
      setResolutionNote('');
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : 'Ticket update failed.');
    } finally {
      setIsSaving(false);
    }
  };

  const retryResolutionNotification = async () => {
    if (!id) return;
    setActionError(null);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/retry-resolution-notification/`, {
        method: 'POST', credentials: 'include', headers: { 'X-CSRFToken': csrfToken },
      });
      if (!response.ok) throw new Error(await getResponseError(response, 'Unable to retry the notification.'));
      await queryClient.invalidateQueries({ queryKey: ['resolution-notification', id] });
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : 'Unable to retry the notification.');
    }
  };

  const saveWhatsAppContact = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!id) return;
    try {
      const csrfToken = await getCsrfToken();
      await apiJson(`/api/tickets/${id}/whatsapp-contact/`, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: JSON.stringify({ number: whatsappNumber, consent: whatsappConsent }) });
      await queryClient.invalidateQueries({ queryKey: ['whatsapp-notifications', id] });
    } catch (reason) { setActionError(reason instanceof Error ? reason.message : 'Unable to save WhatsApp contact.'); }
  };

  const retryWhatsApp = async (notificationId: number) => {
    if (!id || retryingWhatsAppId !== null) return;
    const notification = whatsappQuery.data?.notifications.find((item) => item.id === notificationId);
    const retryAfterFix = Boolean(notification && notification.attempt_count >= notification.max_attempts);
    if (retryAfterFix && !window.confirm('The automatic attempts are used up. First fix the WhatsApp configuration issue, then start a new manual send attempt?')) return;
    setActionError(null);
    setRetryingWhatsAppId(notificationId);
    try {
      const csrfToken = await getCsrfToken();
      await apiJson(`/api/tickets/${id}/retry-whatsapp-notification/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ notification_id: notificationId, retry_after_fix: retryAfterFix }),
      });
      await queryClient.invalidateQueries({ queryKey: ['whatsapp-notifications', id] });
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : 'Unable to retry WhatsApp notification.');
      await queryClient.invalidateQueries({ queryKey: ['whatsapp-notifications', id] });
    } finally {
      setRetryingWhatsAppId(null);
    }
  };

  const deleteTicket = async () => {
    if (!id || !window.confirm(`Delete ticket ${ticket?.ticket_number}? This cannot be undone.`)) return;
    setActionError(null);
    setIsSaving(true);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'X-CSRFToken': csrfToken },
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response, 'Unable to delete this ticket.'));
      }
      await queryClient.invalidateQueries({ queryKey: ['tickets'] });
      navigate('/tickets');
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : 'Ticket deletion failed.');
    } finally {
      setIsSaving(false);
    }
  };

  const addReply = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!id || !reply.trim()) return;
    setActionError(null);
    setIsSaving(true);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/messages/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ body: reply.trim(), message_type: 'agent' }),
      });
      if (!response.ok) {
        throw new Error('Unable to add the reply.');
      }
      const message = await response.json() as TicketMessage;
      setMessages((current) => [...current, message]);
      setReply('');
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : 'Reply could not be added.');
    } finally {
      setIsSaving(false);
    }
  };

  const suggestReply = async () => {
    if (!id) return;
    setSuggestionError(null);
    setIsSuggesting(true);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/suggest-reply/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRFToken': csrfToken },
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response, 'Unable to generate an AI suggestion.'));
      }
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const statusResponse = await fetch(
          `${API_BASE_URL}/api/tickets/${id}/suggestion-status/`,
          { credentials: 'include' },
        );
        const data = await statusResponse.json();
        if (data.status === 'succeeded' && data.message) {
          setMessages((current) => [
            ...current.filter((message) => message.id !== data.message.id),
            data.message,
          ]);
          setSuggestionDraft(data.message.body);
          return;
        }
        if (data.status === 'failed') {
          throw new Error(data.error_message || 'AI suggestion generation failed.');
        }
      }
      throw new Error('AI suggestion generation timed out.');
    } catch (reason: unknown) {
      setSuggestionError(reason instanceof Error ? reason.message : 'AI suggestion failed.');
    } finally {
      setIsSuggesting(false);
    }
  };

  const acceptSuggestion = async (message: TicketMessage) => {
    if (!id) return;
    setSuggestionError(null);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/accept-suggestion/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          message_id: message.id,
          body: suggestionDraft.trim() || message.body,
        }),
      });
      if (!response.ok) {
        throw new Error('Unable to accept the AI suggestion.');
      }
      const updated = await response.json();
      setMessages((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (reason: unknown) {
      setSuggestionError(reason instanceof Error ? reason.message : 'Unable to accept suggestion.');
    }
  };

  const classifyTicket = async () => {
    if (!id) return;
    setActionError(null);
    setIsClassifying(true);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/classify/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRFToken': csrfToken },
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response, 'Unable to trigger AI classification.'));
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await queryClient.invalidateQueries({ queryKey: ['ticket', id] });
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : 'AI classification failed.');
    } finally {
      setIsClassifying(false);
    }
  };

  const summarizeTicket = async () => {
    if (!id) return;
    setActionError(null);
    setIsSummarizing(true);
    try {
      const csrfToken = await getCsrfToken();
      const response = await fetch(`${API_BASE_URL}/api/tickets/${id}/summarize/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRFToken': csrfToken },
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response, 'Unable to trigger AI summarization.'));
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await queryClient.invalidateQueries({ queryKey: ['ticket', id] });
      await queryClient.invalidateQueries({ queryKey: ['ticket-messages', id] });
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : 'AI summarization failed.');
    } finally {
      setIsSummarizing(false);
    }
  };

  if (error) {
    return (
      <>
        <NavBar />
        <main className="app-main">
          <div className="mx-auto max-w-[1440px] rounded-lg border border-red-200 bg-white p-5 text-sm text-red-700" role="alert">
            {error instanceof Error ? error.message : 'Unable to load this ticket.'}
          </div>
        </main>
      </>
    );
  }
  if (ticketQuery.isLoading || messagesQuery.isLoading || !ticket) {
    return (
      <>
        <NavBar />
        <main className="app-main">
          <div className="mx-auto max-w-[1440px] space-y-4" aria-label="Loading ticket">
            <div className="h-4 w-28 animate-pulse rounded bg-slate-200" />
            <div className="h-24 animate-pulse rounded-lg border border-slate-200 bg-white" />
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />
              <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />
            </div>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
    <NavBar />
    <main className="app-main">
      <div className="mx-auto max-w-[1440px] space-y-5">
        <Link to="/tickets" className="text-sm font-medium text-blue-600 hover:underline">
          <span className="inline-flex items-center gap-2"><ArrowLeft className="size-4" aria-hidden="true" />Back to tickets</span>
        </Link>
        <section className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:p-5 xl:grid-cols-2">
          <PageHeader
            className="mb-0 xl:col-span-2"
            eyebrow={ticket.ticket_number}
            title={ticket.subject}
            description={ticket.requester_email}
            actions={ticket.status === 'open' ? (
              <Button type="button" onClick={() => updateTicket('resolved')} disabled={isSaving} className="bg-emerald-700 hover:bg-emerald-800">
                {isSaving ? 'Saving…' : 'Resolve ticket'}
              </Button>
            ) : ticket.status === 'resolved' ? (
              <Button type="button" variant="outline" onClick={() => updateTicket('open')} disabled={isSaving}>Reopen ticket</Button>
            ) : undefined}
          />
          <div className="flex flex-wrap items-center gap-2 xl:col-span-2">
            <StatusBadge status={ticket.status} />
            <CategoryBadge category={ticket.category} />
            <PriorityBadge priority={ticket.priority} />
            <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-slate-500">
              <CalendarDays className="size-3.5" aria-hidden="true" />
              Created {new Date(ticket.created_at).toLocaleDateString()}
            </span>
          </div>
          <div className="flex flex-wrap gap-2 xl:col-span-2">
            {auth?.user?.role === 'ADMIN' && (
              <Button type="button" variant="destructive" onClick={deleteTicket} disabled={isSaving}>
                {isSaving ? 'Deleting...' : 'Delete ticket'}
              </Button>
            )}

            <Button type="button" variant="outline" onClick={classifyTicket} disabled={isClassifying}>
            {isClassifying ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Bot className="size-4" aria-hidden="true" />}
            {isClassifying ? 'Classifying…' : 'Classify with AI'}
            </Button>

            <Button type="button" variant="outline" onClick={summarizeTicket} disabled={isSummarizing}>
            {isSummarizing ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Sparkles className="size-4" aria-hidden="true" />}
            {isSummarizing ? 'Summarizing…' : 'Summarize with AI'}
            </Button>
          </div>
          {ticket.status === 'open' && (
            <label className="block text-sm font-medium text-slate-700 xl:col-start-1" htmlFor="resolution-note">
              Resolution details (optional)
              <textarea id="resolution-note" value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} maxLength={10000} rows={3} className="mt-1 w-full rounded-lg border border-slate-300 p-3 font-normal" />
            </label>
          )}
          {ticket.status === 'resolved' && notificationQuery.data && notificationQuery.data.status !== 'not_started' && (
            <div className="text-sm text-slate-700 xl:col-start-1" role="status">
              Resolution email: <strong className="capitalize">{notificationQuery.data.status}</strong>
              {notificationQuery.data.status === 'failed' && notificationQuery.data.attempt_count < notificationQuery.data.max_attempts && (
                <button type="button" onClick={retryResolutionNotification} className="ml-3 rounded border border-slate-300 px-3 py-1 font-medium hover:bg-slate-50">Retry email</button>
              )}
            </div>
          )}
          <section className="min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white xl:col-start-2 xl:row-start-4" aria-labelledby="whatsapp-heading">
            <div className="border-b border-slate-200 px-4 py-3.5">
              <h2 id="whatsapp-heading" className="text-sm font-semibold text-slate-900">WhatsApp</h2>
              <p className="mt-0.5 text-xs text-slate-500">Customer contact and notification status</p>
            </div>

            <div className="space-y-4 p-4">
              <div>
                <p className="text-xs font-medium text-slate-500">Current contact</p>
                <p className="mt-1 break-all text-sm font-semibold text-slate-900">
                  {whatsappQuery.data?.contact?.number || 'No number saved'}
                </p>
                {whatsappQuery.data?.contact?.consent ? (
                  <p className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700">
                    <Check className="size-3.5" aria-hidden="true" /> Customer consent recorded
                  </p>
                ) : (
                  <p className="mt-1.5 text-xs text-slate-500">Customer consent not recorded</p>
                )}
              </div>

              <div className="border-t border-slate-200" />

              <form onSubmit={saveWhatsAppContact} className="space-y-3">
                <label htmlFor="whatsapp-number" className="block text-xs font-medium text-slate-700">
                  WhatsApp number
                  <input
                    id="whatsapp-number"
                    type="tel"
                    autoComplete="tel"
                    inputMode="tel"
                    value={whatsappNumber}
                    onChange={(event) => setWhatsappNumber(event.target.value)}
                    placeholder="Enter number with country code"
                    className="mt-1.5 block h-10 w-full min-w-0 rounded-md border border-slate-300 bg-white px-3 text-sm font-normal text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                </label>
                <label htmlFor="whatsapp-consent" className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 text-sm text-slate-700">
                  <input
                    id="whatsapp-consent"
                    type="checkbox"
                    checked={whatsappConsent}
                    onChange={(event) => setWhatsappConsent(event.target.checked)}
                    className="size-4 shrink-0 cursor-pointer rounded border-slate-300 accent-blue-600 focus-visible:ring-2 focus-visible:ring-blue-500"
                  />
                  <span>Customer consent recorded</span>
                </label>
                <Button type="submit" size="sm" className="w-full">Save contact</Button>
              </form>

              <div className="border-t border-slate-200" />

              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Notifications</h3>
                {(whatsappQuery.data?.notifications ?? []).map((item) => (
                  <div key={item.id} className="min-w-0 rounded-md border border-slate-200 px-3 py-3" role="status">
                    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                      <StatusBadge status={item.status} />
                      {item.last_attempt_at && (
                        <time className="inline-flex min-w-0 items-center gap-1.5 text-xs text-slate-500" dateTime={item.last_attempt_at}>
                          <Clock3 className="size-3.5 shrink-0" aria-hidden="true" />
                          <span>{new Date(item.last_attempt_at).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
                        </time>
                      )}
                    </div>
                    {item.status === 'failed' && item.error_code && (
                      <p className="mt-2 break-words text-xs text-red-700">
                        {item.error_code.startsWith('meta_') ? `Meta WhatsApp error ${item.error_code.slice('meta_'.length)}.` : item.error_code.startsWith('provider_rejected_') ? `Meta WhatsApp rejected the request (${item.error_code.slice('provider_rejected_'.length)}).` : item.error_code}
                      </p>
                    )}
                    {item.status === 'failed' && item.error_detail && <p className="mt-1 break-words text-xs text-red-700">{item.error_detail}</p>}
                    {item.delivered_at && (
                      <p className="mt-2 text-xs text-emerald-700">
                        Delivered {new Date(item.delivered_at).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}
                      </p>
                    )}
                    {item.status === 'failed' && (
                      <Button type="button" variant="outline" size="sm" className="mt-3 w-full" disabled={retryingWhatsAppId !== null} onClick={() => void retryWhatsApp(item.id)}>
                        {retryingWhatsAppId === item.id && <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />}
                        {retryingWhatsAppId === item.id ? 'Retrying…' : item.attempt_count < item.max_attempts ? 'Retry WhatsApp' : 'Retry after fixing'}
                      </Button>
                    )}
                  </div>
                ))}
                {whatsappQuery.isLoading && <p className="text-xs text-slate-500">Loading notification history…</p>}
                {whatsappQuery.isError && <p className="text-xs text-red-700">Unable to load WhatsApp history.</p>}
                {!whatsappQuery.isLoading && !whatsappQuery.isError && !whatsappQuery.data?.notifications.length && (
                  <p className="text-xs text-slate-500">No WhatsApp notifications yet.</p>
                )}
              </div>
            </div>
          </section>
          {actionError && <p className="text-sm text-red-600 xl:col-span-2" role="alert">{actionError}</p>}
          {suggestionError && <p className="text-sm text-red-600 xl:col-span-2" role="alert">{suggestionError}</p>}
          {ticket.ai_summary && (
            <div className="min-w-0 rounded-lg border border-blue-100 bg-blue-50/60 p-4 text-sm text-blue-900 [overflow-wrap:anywhere] xl:col-start-2">
              <strong className="block"><Sparkles className="mr-1 inline size-4" aria-hidden="true" />AI summary</strong>
              <p className="mt-1 whitespace-pre-wrap break-words">{ticket.ai_summary}</p>
              {ticket.ai_category_confidence !== null && ticket.ai_category_confidence !== undefined && (
                <span className="ml-2 text-blue-700">
                  ({Math.round(ticket.ai_category_confidence * 100)}% confidence)
                </span>
              )}
            </div>
          )}
          {ticket.attachments && ticket.attachments.length > 0 && (
            <div className="xl:col-start-2">
              <h2 className="text-sm font-semibold text-slate-900">Attachments</h2>
              <div className="mt-2 flex flex-wrap gap-2">
                {ticket.attachments.map((attachment) => (
                  <a
                    key={attachment.id}
                    href={`${API_BASE_URL}${attachment.download_url}`}
                    className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm text-blue-700 transition hover:bg-blue-50"
                    download={attachment.filename}
                  >
                    <Paperclip className="size-4" aria-hidden="true" />{attachment.filename}
                  </a>
                ))}
              </div>
            </div>
          )}
        </section>
        <section className="space-y-3">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Conversation</h2>
              <p className="text-xs text-slate-500">{conversationMessages.length} message{conversationMessages.length === 1 ? '' : 's'}</p>
            </div>
          </div>
          {conversationMessages.length === 0 ? (
            <EmptyState title="No messages yet" description="Customer messages and agent replies will appear here." />
          ) : conversationMessages.map((message) => (
            <article key={message.id} className="min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold capitalize text-slate-800">
                    {message.is_ai_generated && message.is_draft ? 'AI suggested reply' : message.message_type}
                  </p>
                  <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-slate-500"><Clock3 className="size-3" aria-hidden="true" />{new Date(message.created_at).toLocaleString()}</p>
                </div>
                {message.is_ai_generated && message.is_draft && (
                  <Button type="button" size="sm" onClick={() => acceptSuggestion(message)}>
                    <Check className="size-4" aria-hidden="true" /> Use reply
                  </Button>
                )}
              </div>
              {message.is_ai_generated && message.is_draft ? (
                <textarea
                  aria-label="Edit AI suggested reply"
                  value={suggestionDraft || message.body}
                  onChange={(event) => setSuggestionDraft(event.target.value)}
                  rows={5}
                  className="mt-3 w-full rounded-md border border-blue-200 bg-blue-50/40 p-3 text-sm text-slate-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              ) : (
                <p className="mt-3 min-w-0 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700 [overflow-wrap:anywhere]">{message.body}</p>
              )}
            </article>
          ))}
        </section>
        <form onSubmit={addReply} className="rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <label htmlFor="reply" className="text-sm font-semibold text-slate-900">Reply to customer</label>
            <Button type="button" variant="outline" size="sm" onClick={suggestReply} disabled={isSuggesting}>
              {isSuggesting ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <WandSparkles className="size-4" aria-hidden="true" />}
              {isSuggesting ? 'Generating suggestion…' : 'Suggest with AI'}
            </Button>
          </div>
          <textarea
            id="reply"
            value={reply}
            onChange={(event) => setReply(event.target.value)}
            rows={4}
            placeholder="Write a response for the requester…"
            className="w-full rounded-md border border-slate-200 p-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <div className="mt-3 flex justify-end">
            <Button type="submit" disabled={isSaving || !reply.trim()}>
              {isSaving ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Send className="size-4" aria-hidden="true" />}
              {isSaving ? 'Sending…' : 'Add reply'}
            </Button>
          </div>
        </form>
      </div>
    </main>
    </>
  );
};

export default TicketDetail;
