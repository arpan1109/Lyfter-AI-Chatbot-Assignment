import React, { useState, useRef, useEffect } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function generateSessionId() {
  return 's-' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
}

export default function App() {
  const [sessionId, setSessionId] = useState(() => generateSessionId());
  const [systemPrompt, setSystemPrompt] = useState('');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [simHeader, setSimHeader] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleNewSession = () => {
    setSessionId(generateSessionId());
    setMessages([]);
    setInput('');
  };

  const handleSend = async (e) => {
    if (e) e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const userMsg = { role: 'user', content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (simHeader.trim()) {
        headers['X-Simulate-Failure'] = simHeader.trim();
      }

      const body = {
        session_id: sessionId,
        message: trimmed,
      };
      if (systemPrompt.trim()) {
        body.system_prompt = systemPrompt.trim();
      }

      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });

      const data = await res.json();

      if (!res.ok) {
        const errText =
          typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail || 'Request failed');
        setMessages((prev) => [
          ...prev,
          { role: 'error', content: `Error (${res.status}): ${errText}` },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: data.reply,
            metadata: data.metadata,
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'error', content: `Network error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div>
          <h1>Lyftr AI Gateway</h1>
          <span className="session-badge">Session: {sessionId}</span>
        </div>
        <button type="button" className="new-session-btn" onClick={handleNewSession}>
          + New Session
        </button>
      </header>

      <div className="controls-bar">
        <div className="control-group">
          <label htmlFor="sys-prompt">System Prompt (Optional)</label>
          <input
            id="sys-prompt"
            data-testid="system-prompt-input"
            type="text"
            placeholder="e.g., You are a pirate. Answer in 1 sentence."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </div>
        <div className="control-group sim-group">
          <label htmlFor="sim-header">Simulate Failure Header (Demo Hook)</label>
          <input
            id="sim-header"
            type="text"
            placeholder="e.g., key_1=429 or *=429"
            value={simHeader}
            onChange={(e) => setSimHeader(e.target.value)}
          />
        </div>
      </div>

      <main className="chat-window">
        {messages.length === 0 && (
          <div className="empty-state">
            Send a message to test multi-turn memory, key failover, and response caching.
          </div>
        )}

        {messages.map((msg, idx) => {
          if (msg.role === 'user') {
            return (
              <div key={idx} className="message-row user-row">
                <div className="bubble user-bubble">{msg.content}</div>
              </div>
            );
          }

          if (msg.role === 'error') {
            return (
              <div key={idx} className="message-row assistant-row">
                <div className="bubble error-bubble">{msg.content}</div>
              </div>
            );
          }

          const meta = msg.metadata || {};
          const isCache = meta.resolution_source === 'LLM_CACHE';

          return (
            <div key={idx} className="message-row assistant-row">
              <div className="bubble assistant-bubble" data-testid="assistant-message">
                <div className="reply-text">{msg.content}</div>
                <div className="meta-bar">
                  <span
                    className={`badge ${isCache ? 'badge-cache' : 'badge-live'}`}
                    data-testid="meta-source"
                  >
                    {meta.resolution_source}
                  </span>
                  <span className="meta-item" data-testid="meta-model">
                    {meta.model}
                  </span>
                  <span className="meta-item" data-testid="meta-latency">
                    {meta.latency_ms} ms
                  </span>
                  <span className="meta-item">
                    In: <strong data-testid="meta-input-tokens">{meta.input_tokens}</strong>
                  </span>
                  <span className="meta-item">
                    Out: <strong data-testid="meta-output-tokens">{meta.output_tokens}</strong>
                  </span>
                  {meta.key_id && (
                    <span className="meta-item">
                      Key: <strong>{meta.key_id}</strong> (fallbacks: {meta.fallback_attempts})
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="message-row assistant-row">
            <div className="bubble assistant-bubble loading-bubble">Thinking...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      <form className="input-area" onSubmit={handleSend}>
        <textarea
          data-testid="chat-input"
          rows={2}
          placeholder="Type your message... (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button type="submit" data-testid="send-button" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}