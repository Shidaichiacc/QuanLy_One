/* Shared update popup. Opening it only checks status; only its button starts work. */
(function () {
  const byId = id => document.getElementById(id);
  const link = byId('sidebarUpdate'), dialog = byId('updateDialog');
  if (!link || !dialog) return;
  const label = link.querySelector('.sidebar-update-label'), icon = link.querySelector('.sidebar-update-icon');
  const title = byId('updateDialogTitle'), message = byId('updateDialogMessage'), note = byId('updateDialogNote');
  const start = byId('updateCenter'), retry = byId('updateRetry'), releaseLink = byId('updateRelease'), download = byId('updateDownload');
  const progress = byId('updatePopupProgress'), phase = byId('updatePopupPhase'), percent = byId('updatePopupPercent');
  const bar = byId('updatePopupBar'), detail = byId('updatePopupMessage'), log = byId('updatePopupLog'), close = byId('updatePopupClose');
  const markerKey = 'jx-update-running';
  let release = null, active = false, posting = false, polling = false, timer = null, mode = 'release';
  let statusReady = false, lastUpdated = 0, marker = null, refreshSequence = 0;
  try { marker = JSON.parse(sessionStorage.getItem(markerKey) || 'null'); } catch (_) {}
  function remember(value) {
    marker = value;
    try { if (value) sessionStorage.setItem(markerKey, JSON.stringify(value)); else sessionStorage.removeItem(markerKey); } catch (_) {}
  }
  function open() { if (!dialog.open) dialog.showModal(); }
  function controls() {
    retry.hidden = active;
    releaseLink.hidden = active || mode !== 'release' || !release?.url;
    download.hidden = active || mode !== 'release' || !release?.download_url;
    start.hidden = active || (mode !== 'success' && !(release?.status === 'ok' && release.available));
    start.disabled = posting || !statusReady || (!(release?.status === 'ok' && release.available) && mode !== 'success');
    start.textContent = mode === 'success' ? 'Hoàn tất' : (mode === 'error' ? 'Thử lại' : 'Cập nhật ngay');
    close.textContent = active ? 'Ẩn' : 'Đóng';
  }
  function renderRelease() {
    if (mode !== 'release' || !release) return;
    progress.hidden = true; note.hidden = true; dialog.dataset.state = 'idle';
    link.classList.remove('available', 'checked', 'failed');
    if (release.status === 'ok' && release.available) {
      link.classList.add('available'); icon.textContent = '↑'; label.textContent = 'Có bản v' + release.latest;
      title.textContent = 'Có bản mới v' + release.latest;
      message.textContent = 'Máy đang dùng v' + release.current + '. Bấm cập nhật để cài bản mới.'; note.hidden = false;
    } else if (release.status === 'ok') {
      link.classList.add('checked'); icon.textContent = '✓'; label.textContent = 'Đã là bản mới nhất';
      title.textContent = 'Đã là bản mới nhất'; message.textContent = 'Máy đang dùng v' + release.current + '.';
    } else {
      link.classList.add('failed'); icon.textContent = '!'; label.textContent = 'Không kiểm tra được';
      title.textContent = 'Chưa kiểm tra được bản mới'; message.textContent = release.message || 'Hãy bấm Kiểm tra lại.';
    }
    byId('updateDialogIcon').textContent = icon.textContent;
    if (release.url) releaseLink.href = release.url;
    if (release.download_url) download.href = release.download_url;
    controls();
  }
  function renderJob(data) {
    const success = data.state === 'success', failed = data.state === 'error';
    mode = success ? 'success' : (failed ? 'error' : 'progress'); active = !success && !failed;
    dialog.dataset.state = data.state; progress.hidden = false; note.hidden = true;
    const value = Number(data.percent || 0), amount = success ? 100 : Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
    title.textContent = success ? 'Cập nhật thành công' : (failed ? 'Cập nhật chưa hoàn tất' : 'Đang cập nhật JXNative');
    message.textContent = success ? 'Đã cài xong bản cập nhật.' : (failed ? 'Xem nguyên nhân bên dưới.' : 'Có thể ẩn popup; tiến trình vẫn tiếp tục chạy.');
    phase.textContent = success ? 'Cập nhật thành công' : (data.phase || 'Đang cập nhật');
    percent.textContent = amount + '%'; bar.value = amount; detail.textContent = data.message || '';
    log.textContent = (Array.isArray(data.logs) ? data.logs : []).map(row => `[${row.time || ''}] ${row.phase || ''}${row.message ? ' — ' + row.message : ''}`).join('\n');
    byId('updateDialogIcon').textContent = success ? '✓' : (failed ? '!' : '↑');
    label.textContent = success ? 'Cập nhật thành công' : (failed ? 'Cập nhật gặp lỗi' : 'Đang cập nhật ' + amount + '%');
    if (!active) { clearTimeout(timer); remember(null); }
    controls();
  }
  async function check(force = false) {
    const sequence = ++refreshSequence; retry.disabled = true;
    try {
      const response = await fetch(link.dataset.checkUrl + (force ? '?refresh=1' : ''), {cache: 'no-store', headers: {Accept: 'application/json'}});
      if (!response.ok || response.redirected) throw new Error('Hãy đăng nhập lại hoặc kiểm tra kết nối.');
      const result = await response.json();
      if (sequence !== refreshSequence) return;
      release = result; renderRelease(); controls();
    } catch (error) {
      if (sequence !== refreshSequence) return;
      release = {status: 'error', message: error.message}; renderRelease(); controls();
    } finally { if (sequence === refreshSequence) retry.disabled = false; }
  }
  async function readStatus() {
    if (polling) return; polling = true;
    try {
      const response = await fetch(dialog.dataset.statusUrl, {cache: 'no-store', headers: {Accept: 'application/json'}});
      if (response.redirected || response.status === 401 || response.status === 403) {
        if (active || marker) renderJob({state: 'error', percent: bar.value, phase: 'Cần đăng nhập lại', message: 'Đăng nhập lại rồi mở popup để xem tiến độ.'});
        return;
      }
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json(); statusReady = true;
      lastUpdated = Math.max(lastUpdated, Number(data.updated || 0));
      if (posting) return; // Old success may remain while this request is stopping game.
      if (['queued', 'working'].includes(data.state)) {
        if (!marker) remember({after: 0});
        renderJob(data);
      } else if (marker && lastUpdated > Number(marker.after || 0) && ['success', 'error'].includes(data.state)) {
        renderJob(data);
      } else if (marker) {
        active = true;
        renderJob({state: 'working', percent: bar.value, phase: 'Đang chờ tiến trình cập nhật', message: 'Đang kiểm tra kết quả yêu cầu…'});
      }
    } catch (_) {
      if (active || marker) {
        active = true; mode = 'progress'; progress.hidden = false;
        title.textContent = 'Đang cập nhật JXNative'; phase.textContent = 'Đang chờ Web kết nối lại';
        detail.textContent = 'Trang sẽ tự kết nối lại và tiếp tục hiển thị tiến độ.';
      }
    } finally {
      polling = false; controls(); clearTimeout(timer);
      if (active && !posting) timer = setTimeout(readStatus, 1200);
    }
  }
  async function launch() {
    if (mode === 'success') { location.reload(); return; }
    if (active || posting || !statusReady || !(release?.status === 'ok' && release.available)) return;
    posting = true; remember({after: lastUpdated});
    renderJob({state: 'working', percent: 0, phase: 'Đang chuẩn bị cập nhật', message: 'Đang kiểm tra bản mới và Stop All an toàn nếu game đang chạy…'});
    const body = new FormData(); body.set('csrf_token', dialog.dataset.csrf); body.set('stop_server', '1');
    let accepted = false;
    try {
      const response = await fetch(dialog.dataset.startUrl, {method: 'POST', body, headers: {Accept: 'application/json'}});
      if (response.redirected) { renderJob({state: 'error', percent: 0, message: 'Phiên đăng nhập đã hết. Hãy đăng nhập lại.'}); return; }
      const data = await response.json();
      if (!response.ok) { renderJob({state: 'error', percent: 0, message: data.error || 'Không bắt đầu được cập nhật.'}); return; }
      accepted = true;
      renderJob({state: 'queued', percent: 1, phase: 'Đã nhận yêu cầu', message: 'Đang bắt đầu tải bản cập nhật…'});
    } catch (_) {
      // The POST may have reached the server. Recover from status instead of resubmitting.
      accepted = true; phase.textContent = 'Đang kiểm tra yêu cầu cập nhật';
      detail.textContent = 'Kết nối bị gián đoạn. Đang kiểm tra tiến trình để tránh gửi yêu cầu trùng.';
    } finally {
      posting = false; controls(); if (accepted) readStatus();
    }
  }
  link.addEventListener('click', () => { open(); check(true); readStatus(); });
  start.addEventListener('click', launch);
  retry.addEventListener('click', () => { if (!active) { mode = 'release'; check(true); readStatus(); } });
  dialog.querySelectorAll('.update-dialog-close').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  const url = new URL(location.href);
  if (url.searchParams.get('update') === '1') { url.searchParams.delete('update'); history.replaceState(null, '', url); open(); }
  check(); readStatus();
})();
