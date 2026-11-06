import React, { useState, useEffect, useRef } from 'react';
import {
  fetchDocument,
  fetchSummary,
  fetchPage,
  uploadPaper,
  askQuestion,
} from './api.js';
import UploadPanel from './components/UploadPanel.jsx';
import SummaryView from './components/SummaryView.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import SourceViewer from './components/SourceViewer.jsx';

function getDisplayTitle(fileName) {
  if (!fileName) return 'Research Paper';
  const base = fileName.replace(/\.pdf$/i, '');
  if (base.toLowerCase() === 'retrieval-augmented-generation') {
    return 'Retrieval-Augmented Generation';
  }
  return base
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function App() {
  const [docInfo, setDocInfo] = useState(null);
  const [summary, setSummary] = useState(null);
  const [activeTab, setActiveTab] = useState('summary');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageData, setPageData] = useState(null);
  const [activeCitation, setActiveCitation] = useState(null);
  const [messages, setMessages] = useState([]);

  const [uploading, setUploading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState(null);

  const fileInputRef = useRef(null);

  // Load document on mount if already uploaded
  useEffect(() => {
    async function init() {
      try {
        const doc = await fetchDocument();
        if (doc && doc.file_name) {
          setDocInfo(doc);
          const sum = await fetchSummary().catch(() => null);
          if (sum) setSummary(sum);
          loadPage(1);
        }
      } catch {
        // No document loaded yet
      }
    }
    init();
  }, []);

  const loadPage = async (pageNumber) => {
    setPageLoading(true);
    try {
      const data = await fetchPage(pageNumber);
      setPageData(data);
      setCurrentPage(pageNumber);
    } catch (err) {
      setError(err.message || 'Failed to load page.');
    } finally {
      setPageLoading(false);
    }
  };

  const handleUpload = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported.');
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const res = await uploadPaper(file);
      const totalPages = res.total_pages || res.pages || 1;
      const doc = {
        file_name: res.file_name || file.name,
        total_pages: totalPages,
      };
      setDocInfo(doc);
      setSummary(res.summary);
      setMessages([]);
      setActiveCitation(null);
      setActiveTab('summary');
      await loadPage(1);
    } catch (err) {
      setError(err.message || 'Failed to upload paper. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const handleSendMessage = async (question) => {
    if (!question || chatLoading) return;
    setError(null);
    const newMsg = { role: 'user', content: question };
    setMessages((prev) => [...prev, newMsg]);
    setChatLoading(true);

    try {
      const data = await askQuestion(question);
      const assistantMsg = {
        role: 'assistant',
        content: data.answer || '',
        sources: data.sources || [],
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setError(err.message || 'Failed to get an answer. Please try again.');
    } finally {
      setChatLoading(false);
    }
  };

  const handleSelectCitation = (citation) => {
    setActiveCitation(citation);
    if (citation.page && citation.page !== currentPage) {
      loadPage(citation.page);
    }
  };

  const handlePageChange = (newPage) => {
    if (newPage < 1 || (docInfo && newPage > docInfo.total_pages)) return;
    loadPage(newPage);
  };

  const documentTitle = getDisplayTitle(docInfo?.file_name);

  return (
    <div className="app-container">
      {/* Hidden file input for "Upload new paper" button */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleUpload(file);
          e.target.value = '';
        }}
      />

      {/* Top bar */}
      <header className="top-bar">
        <div className="top-bar-left">
          <div className="app-icon-wrapper">
            <svg
              className="app-icon"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
            </svg>
          </div>
          <span className="app-brand-name">Research Assistant</span>
        </div>

        <div className="top-bar-center">
          {docInfo && (
            <div className="current-file-badge">
              <span className="current-file-name">{docInfo.file_name}</span>
              <span className="status-dot" />
            </div>
          )}
        </div>

        <div className="top-bar-right">
          <button
            type="button"
            className="top-bar-upload-btn"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            <svg
              className="top-bar-upload-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>{uploading ? 'Uploading...' : 'Upload new paper'}</span>
          </button>
        </div>
      </header>

      {/* Main Two-Column Layout */}
      <main className="main-layout">
        {/* Left column (40%) */}
        <section className="left-column">
          {!docInfo ? (
            <UploadPanel
              onUpload={handleUpload}
              loading={uploading}
              error={error}
            />
          ) : (
            <>
              <div className="tabs-header">
                <button
                  type="button"
                  className={`tab-btn ${activeTab === 'summary' ? 'tab-btn-active' : ''}`}
                  onClick={() => setActiveTab('summary')}
                >
                  Summary
                </button>
                <button
                  type="button"
                  className={`tab-btn ${activeTab === 'chat' ? 'tab-btn-active' : ''}`}
                  onClick={() => setActiveTab('chat')}
                >
                  Chat
                </button>
              </div>

              <div className="tab-content">
                {activeTab === 'summary' ? (
                  <SummaryView
                    summary={summary}
                    loading={uploading}
                    error={error}
                  />
                ) : (
                  <ChatPanel
                    messages={messages}
                    onSendMessage={handleSendMessage}
                    onSelectCitation={handleSelectCitation}
                    activeCitation={activeCitation}
                    loading={chatLoading}
                    error={error}
                  />
                )}
              </div>
            </>
          )}
        </section>

        {/* Right column (60%) */}
        <section className="right-column">
          <SourceViewer
            pageData={pageData}
            currentPage={currentPage}
            totalPages={docInfo?.total_pages || 1}
            onPageChange={handlePageChange}
            activeCitation={activeCitation}
            documentTitle={documentTitle}
            loading={pageLoading}
          />
        </section>
      </main>
    </div>
  );
}
