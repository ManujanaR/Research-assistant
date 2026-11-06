import React, { useRef } from 'react';

export default function UploadPanel({ onUpload, loading, error }) {
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  return (
    <div className="upload-panel">
      <div
        className="upload-dropzone"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <svg
          className="upload-panel-icon"
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
        <h3 className="upload-panel-title">Upload a Research Paper</h3>
        <p className="upload-panel-desc">
          Drag and drop a PDF file here, or click to browse
        </p>
        <button
          type="button"
          className="upload-browse-btn"
          disabled={loading}
        >
          {loading ? 'Processing paper...' : 'Select PDF'}
        </button>
      </div>
      {error && <div className="error-message">{error}</div>}
    </div>
  );
}
