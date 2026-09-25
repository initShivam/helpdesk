import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

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
}

interface TicketMessage {
  id: number;
  body: string;
  message_type: string;
  sender?: number | null;
  created_at: string;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

const TicketDetail: React.FC = () => {
  const { id } = useParams();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<TicketMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetch(`${API_BASE_URL}/api/tickets/${id}/`, { credentials: 'include' }),
      fetch(`${API_BASE_URL}/api/tickets/${id}/messages/`, { credentials: 'include' }),
    ])
      .then(async ([ticketResponse, messagesResponse]) => {
        if (!ticketResponse.ok || !messagesResponse.ok) {
          throw new Error('Unable to load this ticket.');
        }
        return Promise.all([ticketResponse.json(), messagesResponse.json()]);
      })
      .then(([ticketData, messagesData]) => {
        setTicket(ticketData);
        setMessages(Array.isArray(messagesData) ? messagesData : messagesData.results ?? []);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : 'Unable to load this ticket.');
      });
  }, [id]);

  if (error) {
    return <main className="p-8 text-red-600">{error}</main>;
  }
  if (!ticket) {
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
            <span>Category: <strong>{ticket.category}</strong></span>
            <span>Priority: <strong>{ticket.priority}</strong></span>
          </div>
          {ticket.ai_summary && (
            <div className="mt-5 rounded-lg bg-blue-50 p-4 text-sm text-blue-900">
              <strong>AI summary:</strong> {ticket.ai_summary}
              {ticket.ai_category_confidence !== null && ticket.ai_category_confidence !== undefined && (
                <span className="ml-2 text-blue-700">
                  ({Math.round(ticket.ai_category_confidence * 100)}% confidence)
                </span>
              )}
            </div>
          )}
        </section>
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-slate-900">Messages</h2>
          {messages.length === 0 ? (
            <p className="text-sm text-slate-500">No messages yet.</p>
          ) : messages.map((message) => (
            <article key={message.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">{message.message_type}</p>
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-800">{message.body}</p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
};

export default TicketDetail;
