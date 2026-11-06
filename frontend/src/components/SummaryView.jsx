import React from 'react';

const SECTIONS = [
  { key: 'title_authors_abstract', title: 'Title, Authors and Abstract' },
  { key: 'problem_statement', title: 'Problem Statement' },
  { key: 'methodology', title: 'Methodology' },
  { key: 'key_results', title: 'Key Results' },
  { key: 'conclusion', title: 'Conclusion' },
];

export default function SummaryView({ summary, loading, error }) {
  if (loading) {
    return (
      <div className="summary-loading">
        <p>Loading summary...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="summary-error">
        <p className="error-message">{error}</p>
      </div>
    );
  }

  return (
    <div className="summary-view">
      {SECTIONS.map(({ key, title }) => {
        const content = summary?.[key] || 'Not found in paper';
        const isNotFound = content === 'Not found in paper';

        return (
          <div key={key} className="summary-card">
            <h3 className="summary-card-heading">{title}</h3>
            <p
              className={`summary-card-body ${
                isNotFound ? 'summary-card-muted' : ''
              }`}
            >
              {content}
            </p>
          </div>
        );
      })}
    </div>
  );
}
