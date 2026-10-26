/* Thin fetch wrappers — the ONLY place the frontend talks to the backend. */
const API = {
  overview: () => fetchJSON("/api/overview"),
  zombies: () => fetchJSON("/api/zombies"),
  inflation: () => fetchJSON("/api/inflation"),
  healthScore: () => fetchJSON("/api/health-score"),
  transactions: () => fetchJSON("/api/transactions"),
  charts: () => fetchJSON("/api/charts"),
  ingestSms: (text) => postJSON("/api/ingest-sms", { text }),
  ingestSmsFile: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/ingest-sms-file", { method: "POST", body: fd })
      .then(handleStatus);
  },
  uploadCsv: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/upload-csv", { method: "POST", body: fd })
      .then(handleStatus);
  },
  reset: () => postJSON("/api/reset", {}),
  clear: () => postJSON("/api/clear", {}),
};

async function fetchJSON(url) {
  const res = await fetch(url);
  return handleStatus(res);
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleStatus(res);
}

async function handleStatus(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
