import React, { useEffect, useState } from 'react';

interface Ticket {
  id: number;
  ticket_number: string;
  subject: string;
  status: string;
  priority: string;
  created_at: string;
}

const App: React.FC = () => {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    // Assuming the backend API is reachable at http://localhost:8000/api/tickets/
    fetch('http://localhost:8000/api/tickets/', {
      credentials: 'include',
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        setTickets(data);
      })
      .catch((err) => console.error('Failed to fetch tickets:', err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: '2rem', fontFamily: 'Arial, sans-serif' }}>
      <h1>Helpdesk Tickets</h1>
      {loading ? (
        <p>Loading tickets...</p>
      ) : tickets.length === 0 ? (
        <p>No tickets found.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>#</th>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Subject</th>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Status</th>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Priority</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id}>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>{t.ticket_number}</td>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>{t.subject}</td>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>{t.status}</td>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>{t.priority}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default App;
