// Shared API helper for all pages. Handles JWT storage + auth headers.
// Port 5000 is occupied on macOS by AirPlay Receiver, so the backend often runs on 5001.
// Probe the active port automatically to avoid stale hardcoded URLs.
const API_BASE_CANDIDATES = [
  "http://127.0.0.1:5001/api",
  "http://127.0.0.1:5000/api",
];

let API_BASE = API_BASE_CANDIDATES[0];

async function detectApiBase() {
  for (const candidate of API_BASE_CANDIDATES) {
    try {
      const res = await fetch(candidate.replace(/\/api$/, ""), { method: "GET" });
      if (res.ok) {
        API_BASE = candidate;
        return candidate;
      }
    } catch (e) {
      // Keep trying the next candidate.
    }
  }
  API_BASE = API_BASE_CANDIDATES[0];
  return API_BASE;
}

(async function initApiBase() {
  await detectApiBase();
})();

const Auth = {
  getToken() {
    return localStorage.getItem("token") || "";
  },
  getUser() {
    const raw = localStorage.getItem("user");
    try {
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  },
  setSession(token, user) {
    if (!token) {
      console.error("Auth.setSession: Token is empty or undefined!");
      return;
    }
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user || {}));
  },
  clear() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  },
  requireRole(roles) {
    const user = Auth.getUser();
    return user;
  },
};

async function api(path, { method = "GET", body, auth = true } = {}) {
  await detectApiBase();

  const headers = { "Content-Type": "application/json" };
  const user = Auth.getUser();
  const token = Auth.getToken();

  if (auth) {
    if (!token) {
      console.warn("api: No token found for protected path:", path);
      throw new Error("Missing bearer token");
    }
    headers["Authorization"] = `Bearer ${token}`;
    if (user) {
      headers["X-User-ID"] = user.id || user.student_id || user.email || "";
      headers["X-Role"] = user.role || "";
    }
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const contentType = res.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await res.json() : null;

  if (res.status === 401) {
    console.error("401 Unauthorized from backend on:", path, data);
    throw new Error((data && (data.error || data.message)) || "Unauthorized");
  }

  if (!res.ok) {
    throw new Error((data && (data.error || data.message)) || `Request failed (${res.status})`);
  }
  return data;
}

// Phase 9 — shared helper for file downloads (PDF reports, CSV/Excel
// exports). fetch() is used directly (not api()) because these endpoints
// return a binary file, not JSON, and api() expects JSON.
async function downloadFile(path, filename) {
  const token = Auth.getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    let message = `Download failed (${res.status})`;
    try {
      const data = await res.json();
      message = data.error || data.message || message;
    } catch (e) { /* response wasn't JSON, keep default message */ }
    throw new Error(message);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function logout() {
  Auth.clear();
  window.location.href = "./login.html";
}

function riskBadgeClass(level) {
  return (
    {
      LOW: "risk-low",
      MEDIUM: "risk-medium",
      HIGH: "risk-high",
      CRITICAL: "risk-critical",
    }[level] || "risk-unknown"
  );
}

// Faculty Student Data Management API Helpers
async function getFacultyStudents() {
  return await api("/faculty/students");
}

async function getFacultyStudent(studentId) {
  return await api(`/faculty/students/${encodeURIComponent(studentId)}`);
}

async function addFacultyStudent(data) {
  return await api("/faculty/students", { method: "POST", body: data });
}

async function updateFacultyStudent(studentId, data) {
  return await api(`/faculty/students/${encodeURIComponent(studentId)}`, { method: "PUT", body: data });
}

async function deleteFacultyStudent(studentId) {
  return await api(`/faculty/students/${encodeURIComponent(studentId)}`, { method: "DELETE" });
}