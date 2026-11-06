import React, { useState, useRef, useEffect } from 'react';

const SUGGESTED_QUESTIONS = [
  'What dataset did they use?',
  'What are the limitations?',
  'Summarize the key results',
];

function formatSectionName(section) {
  if (!section) return 'General';
  // Strip leading numbering like "4 " or "4. "
  return section.replace(/^\d+[\.\s:\-]+/, '').trim();
}

export default function ChatPanel({
  messages,
  onSendMessage,
  onSelectCitation,
  activeCitation,
  loading,
  error,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    onSendMessage(trimmed);
    setInput('');
  };

  const handleSuggestedClick = (question) => {
    if (loading) return;
    onSendMessage(question);
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h2 className="chat-title">Ask about the paper</h2>
        <p className="chat-subtext">Answers are based only on this paper.</p>
      </div>

      <div className="chat-messages">
        {messages.map((msg, idx) => {
          if (msg.role === 'user') {
            return (
              <div key={idx} className="chat-message-user-wrapper">
                <div className="chat-message-user-bubble">{msg.content}</div>
              </div>
            );
          }

          return (
            <div key={idx} className="chat-message-assistant-wrapper">
              <div className="chat-message-assistant-text">{msg.content}</div>
              {msg.sources && msg.sources.length > 0 && (
                <div className="chat-citations">
                  {msg.sources.map((src, sIdx) => {
                    const label = `${sIdx + 1} ${formatSectionName(src.section)}, p. ${src.page}`;
                    const isActive =
                      activeCitation &&
                      activeCitation.page === src.page &&
                      (activeCitation.text === src.text || activeCitation.snippet === src.snippet);

                    return (
                      <button
                        key={sIdx}
                        type="button"
                        className={`citation-chip ${isActive ? 'citation-chip-active' : ''}`}
                        onClick={() => onSelectCitation(src)}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {loading && (
          <div className="chat-message-assistant-wrapper">
            <div className="chat-thinking">Thinking...</div>
          </div>
        )}

        {error && <div className="error-message">{error}</div>}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-footer">
        <div className="chat-suggested-questions">
          {SUGGESTED_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              type="button"
              className="suggested-chip"
              disabled={loading}
              onClick={() => handleSuggestedClick(q)}
            >
              {q}
            </button>
          ))}
        </div>

        <form className="chat-input-form" onSubmit={handleSubmit}>
          <input
            type="text"
            className="chat-input"
            placeholder="Ask a question about this paper"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
          />
          <button
            type="submit"
            className="chat-send-btn"
            disabled={!input.trim() || loading}
            aria-label="Send question"
          >
            <svg
              className="chat-send-icon"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
