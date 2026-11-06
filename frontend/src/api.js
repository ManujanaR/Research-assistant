const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function handleResponse(res) {
  if (!res.ok) {
    let errorMsg = 'An unexpected error occurred.';
    try {
      const errData = await res.json();
      if (errData && typeof errData.detail === 'string') {
        errorMsg = errData.detail;
      } else if (errData && typeof errData.message === 'string') {
        errorMsg = errData.message;
      }
    } catch {
      try {
        const text = await res.text();
        if (text) errorMsg = text;
      } catch {
        // use default errorMsg
      }
    }
    throw new Error(errorMsg);
  }
  return res.json();
}

export async function fetchDocument() {
  const res = await fetch(`${API_BASE}/document`);
  return handleResponse(res);
}

export async function fetchSummary() {
  const res = await fetch(`${API_BASE}/summary`);
  return handleResponse(res);
}

export async function fetchPage(pageNumber) {
  const res = await fetch(`${API_BASE}/pages/${pageNumber}`);
  return handleResponse(res);
}

export async function uploadPaper(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(res);
}

export async function askQuestion(question) {
  const res = await fetch(`${API_BASE}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question }),
  });
  return handleResponse(res);
}
