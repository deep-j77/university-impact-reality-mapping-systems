const API_BASE = "http://127.0.0.1:5000";

const user_id = localStorage.getItem("user_id");
const role = localStorage.getItem("role");

if (!user_id || !role) {
  window.location.href = "login.html";
}

// ---------- SUMMARY ----------
fetch(`${API_BASE}/summary`, {
  headers: {
    "X-User-ID": user_id,
    "X-Role": role
  }
})
.then(res => res.json())
.then(data => {
  document.getElementById("burnout").innerText = data.BURNOUT_RISK;
  document.getElementById("learning").innerText = data.LEARNING_GAP;
  document.getElementById("outcome").innerText = data.OUTCOME_MISMATCH;
  document.getElementById("policy").innerText = data.PLACEMENT_POLICY_MISMATCH;
});

// ---------- TABLE ----------
fetch(`${API_BASE}/students/triggers`, {
  headers: {
    "X-User-ID": user_id,
    "X-Role": role
  }
})
.then(res => res.json())
.then(students => {
  const table = document.getElementById("student-table");
  table.innerHTML = "";

  students.forEach(s => {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${s.student_id}</td>
      <td>${s.university}</td>
      <td>${s.semester}</td>
      <td>${s.cgpa}</td>
      <td>${s.skills_acquired}</td>
      <td>${s.triggers.join(", ")}</td>
      <td>
        <a href="${API_BASE}/student/report/${s.student_id}?uid=${user_id}&role=${role}" target="_blank">
          Download PDF
        </a>
      </td>
    `;

    table.appendChild(row);
  });
});
