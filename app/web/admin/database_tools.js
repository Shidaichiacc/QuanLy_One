(function () {
  const databaseForm = document.getElementById("databasePasswordForm");
  const revealForm = document.getElementById("databaseRevealForm");
  if (!databaseForm || !revealForm) return;

  const masked = "••••••••••••";
  const mysqlBox = document.getElementById("mysqlSecret");
  const mssqlBox = document.getElementById("mssqlSecret");
  const countdown = document.getElementById("secretCountdown");
  let visibleSecrets = null;
  let hideTimer = null;
  let tickTimer = null;

  function closeModal(modal) {
    modal.classList.remove("open");
  }

  function hideSecrets() {
    visibleSecrets = null;
    mysqlBox.textContent = masked;
    mssqlBox.textContent = masked;
    countdown.textContent = "";
    clearTimeout(hideTimer);
    clearInterval(tickTimer);
  }

  function showSecrets(data) {
    hideSecrets();
    visibleSecrets = {mysql: data.mysql, mssql: data.mssql};
    mysqlBox.textContent = data.mysql;
    mssqlBox.textContent = data.mssql;
    let seconds = 30;
    countdown.textContent = "Tự ẩn sau 30 giây";
    tickTimer = setInterval(function () {
      seconds -= 1;
      countdown.textContent = seconds > 0 ? "Tự ẩn sau " + seconds + " giây" : "";
    }, 1000);
    hideTimer = setTimeout(hideSecrets, 30000);
  }

  revealForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    const errorBox = document.getElementById("databaseRevealError");
    errorBox.textContent = "";
    try {
      const response = await fetch(revealForm.action, {
        method: "POST",
        body: new FormData(revealForm),
        cache: "no-store",
        headers: {Accept: "application/json", "X-Requested-With": "XMLHttpRequest"}
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Không xem được mật khẩu");
      showSecrets(data);
      revealForm.reset();
      closeModal(document.getElementById("databaseRevealModal"));
    } catch (error) {
      errorBox.textContent = error.message;
    }
  });

  function strongPassword() {
    const groups = ["abcdefghijkmnopqrstuvwxyz", "ABCDEFGHJKLMNPQRSTUVWXYZ", "23456789", "@_!-"];
    const all = groups.join("");
    const values = groups.map(function (group) {
      return group[crypto.getRandomValues(new Uint32Array(1))[0] % group.length];
    });
    while (values.length < 16) values.push(all[crypto.getRandomValues(new Uint32Array(1))[0] % all.length]);
    for (let index = values.length - 1; index > 0; index -= 1) {
      const other = crypto.getRandomValues(new Uint32Array(1))[0] % (index + 1);
      [values[index], values[other]] = [values[other], values[index]];
    }
    return values.join("");
  }

  document.getElementById("generateDatabasePasswords").addEventListener("click", function () {
    const mysql = strongPassword();
    const mssql = strongPassword();
    databaseForm.elements.mysql_password.value = mysql;
    databaseForm.elements.mysql_confirm.value = mysql;
    databaseForm.elements.mssql_password.value = mssql;
    databaseForm.elements.mssql_confirm.value = mssql;
  });

  const modal = document.getElementById("databasePasswordModal");
  const progressBox = document.getElementById("databasePasswordProgress");
  const progressBar = document.getElementById("databasePasswordBar");
  const progressPercent = document.getElementById("databasePasswordPercent");
  const progressPhase = document.getElementById("databasePasswordPhase");
  const progressMessage = document.getElementById("databasePasswordMessage");
  const submitButton = document.getElementById("databasePasswordSubmit");
  const statusUrl = databaseForm.action.replace(/\/server-setup\/database-password$/, "/database-job/status");

  function drawProgress(data) {
    const value = Math.max(0, Math.min(100, Number(data.percent) || 0));
    progressBar.value = value;
    progressPercent.textContent = Math.round(value) + "%";
    progressPhase.textContent = data.phase || "Đang xử lý";
    progressMessage.textContent = data.message || "";
  }

  async function poll() {
    try {
      const response = await fetch(statusUrl, {cache: "no-store", headers: {Accept: "application/json"}});
      const data = await response.json();
      drawProgress(data);
      if (data.state === "working") {
        setTimeout(poll, 1000);
        return;
      }
      delete modal.dataset.busy;
      submitButton.disabled = false;
      if (data.state === "done") hideSecrets();
    } catch (error) {
      progressMessage.textContent = "Mất kết nối tạm thời, đang thử lại…";
      setTimeout(poll, 1800);
    }
  }

  async function sendRotation() {
    const response = await fetch(databaseForm.action, {
      method: "POST",
      body: new FormData(databaseForm),
      headers: {Accept: "application/json", "X-Requested-With": "XMLHttpRequest"}
    });
    const data = await response.json();
    if (response.status === 409 && data.requires_stop) {
      const approved = await window.JXDialog.confirm(
        "Server đang chạy. Hệ thống sẽ Stop All an toàn, chờ lưu dữ liệu rồi mới đổi mật khẩu database. Game sẽ không tự bật lại. Tiếp tục?",
        {danger: true, confirmText: "Stop All và đổi"}
      );
      if (!approved) throw new Error("Đã hủy yêu cầu");
      databaseForm.elements.stop_server.value = "1";
      return sendRotation();
    }
    if (!response.ok) throw new Error(data.error || "Không bắt đầu được");
    poll();
  }

  databaseForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!databaseForm.reportValidity()) return;
    databaseForm.elements.stop_server.value = "0";
    modal.dataset.busy = "1";
    submitButton.disabled = true;
    progressBox.hidden = false;
    drawProgress({percent: 1, phase: "Đang gửi yêu cầu", message: ""});
    try {
      await sendRotation();
    } catch (error) {
      delete modal.dataset.busy;
      submitButton.disabled = false;
      drawProgress({percent: 100, phase: "Không thể bắt đầu", message: error.message});
    }
  });
})();
