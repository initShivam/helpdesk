import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiJson, API_BASE_URL, getCsrfToken } from '../api';

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
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isClassifying, setIsClassifying] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [suggestionDraft, setSuggestionDraft] = useState('');

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
  const ticket = ticketQuery.data ?? null;
  const messages = messagesQuery.data ?? [];
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
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        throw new Error('Unable to update the ticket status.');
      }
      await queryClient.invalidateQueries({ queryKey: ['ticket', id] });
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : 'Ticket update failed.');
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
      <main className="p-8 text-red-600">
        {error instanceof Error ? error.message : 'Unable to load this ticket.'}
      </main>
    );
  }
  if (ticketQuery.isLoading || messagesQuery.isLoading || !ticket) {
    return <main className="p-8 text-slate-500">Loading ticket...</main>;
  }

  return (
    <main className="min-h-screen bg-slate-50 p-4 sm:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <Link to="/" className="text-sm font-medium text-blue-600 hover:underline">
          ← Back to tickets
        </Link>
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm font-semibold text-blue-600">{ticket.ticket_number}</p>
          <h1 className="mt-2 text-2xl font-bold text-slate-900">{ticket.subject}</h1>
          <p className="mt-2 text-sm text-slate-500">{ticket.requester_email}</p>
          <div className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
            <span>Status: <strong>{ticket.status}</strong></span>
            <span>Category: <strong className="capitalize">{ticket.category}</strong></span>
            <span>Priority: <strong className="capitalize">{ticket.priority}</strong></span>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            {ticket.status === 'open' && (
              <button
                type="button"
                onClick={() => updateTicket('resolved')}
                disabled={isSaving}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 cursor-pointer"
              >
                {isSaving ? 'Saving...' : 'Resolve ticket'}
              </button>
            )}
            {ticket.status === 'resolved' && (
              <button
                type="button"
                onClick={() => updateTicket('open')}
                disabled={isSaving}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
              >
                Reopen ticket
              </button>
            )}

            <button
              type="button"
              onClick={classifyTicket}
              disabled={isClassifying}
              className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 cursor-pointer inline-flex items-center gap-2"
            >
              <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              {isClassifying ? 'Classifying...' : 'Classify with AI'}
            </button>

            <button
              type="button"
              onClick={summarizeTicket}
              disabled={isSummarizing}
              className="rounded-lg border border-purple-200 bg-purple-50 px-4 py-2 text-sm font-semibold text-purple-700 hover:bg-purple-100 disabled:opacity-50 cursor-pointer inline-flex items-center gap-2"
            >
              <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {isSummarizing ? 'Summarizing...' : 'Summarize with AI'}
            </button>
          </div>
          {actionError && <p className="mt-3 text-sm text-red-600">{actionError}</p>}
          {suggestionError && <p className="mt-3 text-sm text-red-600">{suggestionError}</p>}
          {ticket.ai_summary && (
            <div className="mt-5 min-w-0 rounded-lg bg-blue-50 p-4 text-sm text-blue-900 [overflow-wrap:anywhere]">
              <strong className="block">AI summary:</strong>
              <p className="mt-1 whitespace-pre-wrap break-words">{ticket.ai_summary}</p>
              {ticket.ai_category_confidence !== null && ticket.ai_category_confidence !== undefined && (
                <span className="ml-2 text-blue-700">
                  ({Math.round(ticket.ai_category_confidence * 100)}% confidence)
                </span>
              )}
            </div>
          )}
          {ticket.attachments && ticket.attachments.length > 0 && (
            <div className="mt-5">
              <h2 className="text-sm font-semibold text-slate-900">Attachments</h2>
              <div className="mt-2 flex flex-wrap gap-2">
                {ticket.attachments.map((attachment) => (
                  <a
                    key={attachment.id}
                    href={`${API_BASE_URL}${attachment.download_url}`}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-blue-700 hover:bg-blue-50"
                    download={attachment.filename}
                  >
                    Download {attachment.filename}
                  </a>
                ))}
              </div>
            </div>
          )}
        </section>
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-slate-900">Messages</h2>
          {messages.length === 0 ? (
            <p className="text-sm text-slate-500">No messages yet.</p>
          ) : messages.map((message) => (
            <article key={message.id} className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  {message.is_ai_generated ? 'AI suggested reply' : message.message_type}
                </p>
                {message.is_ai_generated && message.is_draft && (
                  <button
                    type="button"
                    onClick={() => acceptSuggestion(message)}
                    className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
                  >
                    Accept suggestion
                  </button>
                )}
              </div>
              {message.is_ai_generated && message.is_draft ? (
                <textarea
                  aria-label="Edit AI suggested reply"
                  value={suggestionDraft || message.body}
                  onChange={(event) => setSuggestionDraft(event.target.value)}
                  rows={5}
                  className="mt-2 w-full rounded-lg border border-blue-200 p-3 text-sm text-slate-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              ) : (
                <p className="mt-2 min-w-0 whitespace-pre-wrap break-words text-sm text-slate-800 [overflow-wrap:anywhere]">{message.body}</p>
              )}
            </article>
          ))}
        </section>
        <form onSubmit={addReply} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <label htmlFor="reply" className="text-lg font-semibold text-slate-900">
            Add final reply
          </label>
          <button
            type="button"
            onClick={suggestReply}
            disabled={isSuggesting}
            className="mt-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          >
            {isSuggesting ? 'Generating suggestion...' : 'Suggest reply with AI'}
          </button>
          <textarea
            id="reply"
            value={reply}
            onChange={(event) => setReply(event.target.value)}
            rows={4}
            placeholder="Write a response for the requester..."
            className="mt-3 w-full rounded-lg border border-slate-300 p-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <button
            type="submit"
            disabled={isSaving || !reply.trim()}
            className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isSaving ? 'Sending...' : 'Add reply'}
          </button>
        </form>
      </div>
    </main>
  );
};

export default TicketDetail;
