// src/types.ts
export interface MeResponse {
  id: number;
  username: string;
  email?: string;
  role?: string;
}

export type TicketCategory = 'general' | 'technical' | 'refund';
export type TicketStatus = 'open' | 'resolved' | 'closed';
export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent';

export interface Ticket {
  id: number;
  ticket_number: string;
  subject: string;
  description?: string;
  requester_email?: string;
  status: TicketStatus;
  category: TicketCategory;
  classification?: string;
  priority: TicketPriority;
  ai_summary?: string | null;
  ai_category_confidence?: number | null;
  source?: string;
  created_at: string;
  updated_at?: string;
  attachments?: Attachment[];
}

export interface Attachment {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  download_url: string;
}

export interface TicketMessage {
  id: number;
  ticket?: number;
  body: string;
  message_type: 'customer' | 'agent' | 'system';
  sender?: number | null;
  created_at: string;
  updated_at?: string;
  is_ai_generated?: boolean;
  is_draft?: boolean;
}

export interface DailyTicketCount {
  date: string;
  count: number;
}

export interface CategoryMetric {
  category: string;
  label: string;
  count: number;
}

export interface PriorityMetric {
  priority: string;
  count: number;
}

export interface AISuggestionMetrics {
  total: number;
  accepted: number;
  pending: number;
  acceptance_rate: number;
}

export interface AnalyticsOverview {
  total_tickets: number;
  open_tickets: number;
  resolved_tickets: number;
  closed_tickets: number;
  average_first_reply_time_seconds: number;
  average_first_reply_time_minutes: number;
  average_first_reply_time_formatted: string;
  ai_suggestions: AISuggestionMetrics;
  tickets_per_day: DailyTicketCount[];
  categories: CategoryMetric[];
  priorities: PriorityMetric[];
}
