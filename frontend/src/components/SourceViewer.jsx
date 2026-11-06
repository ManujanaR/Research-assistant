import React from 'react';

function formatSectionLabel(section, pageNum) {
  if (!section) return `${pageNum} · DOCUMENT`;
  const clean = section.trim();
  const match = clean.match(/^(\d+)[\.\s:\-]+(.*)$/);
  if (match) {
    return `${match[1]} · ${match[2].trim().toUpperCase()}`;
  }
  return `${pageNum} · ${clean.toUpperCase()}`;
}

function findPassageRange(fullText, passage) {
  if (!fullText || !passage) return null;
  const cleaned = passage.trim();
  if (!cleaned) return null;

  const exactIdx = fullText.indexOf(cleaned);
  if (exactIdx !== -1) {
    return { start: exactIdx, end: exactIdx + cleaned.length };
  }

  // Regex matching whitespace sequences across linebreaks
  const maxLen = Math.min(cleaned.length, 250);
  const snippetPart = cleaned.slice(0, maxLen);
  const escaped = snippetPart
    .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\s+/g, '\\s+');

  try {
    const regex = new RegExp(escaped, 'i');
    const match = fullText.match(regex);
    if (match && match.index !== undefined) {
      return { start: match.index, end: match.index + match[0].length };
    }
  } catch {
    // Ignore regex compilation issues
  }

  // Fallback to shorter snippet (e.g. first 60 chars)
  if (cleaned.length > 60) {
    const shortEscaped = cleaned
      .slice(0, 60)
      .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      .replace(/\s+/g, '\\s+');
    try {
      const regex = new RegExp(shortEscaped, 'i');
      const match = fullText.match(regex);
      if (match && match.index !== undefined) {
        return { start: match.index, end: match.index + match[0].length };
      }
    } catch {
      // Ignore
    }
  }

  return null;
}

export default function SourceViewer({
  pageData,
  currentPage,
  totalPages,
  onPageChange,
  activeCitation,
  documentTitle,
  loading,
}) {
  const isCitedPage =
    activeCitation && Number(activeCitation.page) === Number(currentPage);

  const citationText = isCitedPage
    ? activeCitation.text || activeCitation.snippet || ''
    : '';

  const fullText = pageData?.text || '';
  const range = isCitedPage ? findPassageRange(fullText, citationText) : null;

  const sectionLabel = formatSectionLabel(pageData?.section, currentPage);

  return (
    <div className="source-viewer">
      <div className="source-header">
        <div className="source-header-titles">
          <h2 className="source-header-title">Source</h2>
          <span className="source-header-subtext">Cited passage highlighted</span>
        </div>

        <div className="source-pagination">
          <button
            type="button"
            className="source-page-btn"
            disabled={currentPage <= 1 || loading}
            onClick={() => onPageChange(currentPage - 1)}
            aria-label="Previous page"
          >
            <svg
              className="source-nav-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <span className="source-page-indicator">
            Page {currentPage} of {totalPages || 1}
          </span>
          <button
            type="button"
            className="source-page-btn"
            disabled={currentPage >= totalPages || loading}
            onClick={() => onPageChange(currentPage + 1)}
            aria-label="Next page"
          >
            <svg
              className="source-nav-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      </div>

      <div className="source-body">
        <div className="source-paper-card">
          <div className="source-section-label">{sectionLabel}</div>
          <h1 className="source-page-title">{documentTitle}</h1>
          <hr className="source-divider" />

          <div className="source-page-content">
            {loading ? (
              <p className="source-loading">Loading page...</p>
            ) : range ? (
              <>
                {fullText.slice(0, range.start)}
                <mark className="source-highlight">
                  {fullText.slice(range.start, range.end)}
                </mark>
                {fullText.slice(range.end)}
              </>
            ) : (
              fullText || <p className="source-empty">No text available on this page.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
