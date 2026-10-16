const $ = selector => document.querySelector(selector);
const form = $('#form'), url = $('#url'), result = $('#result'), status = $('#status');
const analyze = $('#analyze'), download = $('#download'), quality = $('#quality'), container = $('#container');
const progress = $('#progress'), progressBar = $('#progress-bar'), progressLabel = $('#progress-label');
let selectedUrl = '', videoTitle = '', busy = false, audioContext, toastTimer;
let chosenLink = '', selectedRange = null, videoDuration = null, selectionTrigger = url;
let soundEnabled = localStorage.getItem('kupotube-sound') !== 'off';
function message(text, error = false) { status.textContent = text; status.classList.toggle('error', error); }
function setBusy(value) {
  busy = value;
  for (const element of [analyze, download, url, quality, container, $('#import-session'), $('#remove-session'), $('#edit-selection')]) element.disabled = value;
  quality.disabled = value || container.value === 'mp3';
}
function updateSound() {
  $('#sound').setAttribute('aria-pressed', String(soundEnabled));
  $('#sound').title = soundEnabled ? 'Desativar som de conclusão' : 'Ativar som de conclusão';
  $('#sound img').src = `/icons/speaker-${soundEnabled ? 'high' : 'slash'}.svg`;
}
$('#sound').addEventListener('click', () => {
  soundEnabled = !soundEnabled;
  localStorage.setItem('kupotube-sound', soundEnabled ? 'on' : 'off'); updateSound();
  window.pywebview?.api?.set_sound_enabled?.(soundEnabled).catch(() => {});
});
updateSound();
function prepareAudio() {
  if (!soundEnabled) return;
  try { audioContext ||= new (window.AudioContext || window.webkitAudioContext)(); audioContext.resume().catch(() => {}); } catch (_) {}
}
function notifyComplete(text) {
  $('#toast-text').textContent = text;
  $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 8000);
  if (!soundEnabled || !audioContext) return;
  try {
    const now = audioContext.currentTime;
    [660, 880].forEach((frequency, index) => {
      const oscillator = audioContext.createOscillator(), gain = audioContext.createGain();
      oscillator.type = 'sine'; oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0, now + index * .14);
      gain.gain.linearRampToValueAtTime(.045, now + index * .14 + .025);
      gain.gain.exponentialRampToValueAtTime(.001, now + index * .14 + .45);
      oscillator.connect(gain); gain.connect(audioContext.destination);
      oscillator.start(now + index * .14); oscillator.stop(now + index * .14 + .5);
    });
  } catch (_) {}
}
$('#toast-close').addEventListener('click', () => { $('#toast').hidden = true; });
function showProgress(data) {
  progress.hidden = false;
  const known = Number.isFinite(data.percent);
  progressBar.classList.toggle('indeterminate', !known);
  progressBar.style.width = known ? `${Math.max(0, Math.min(100, data.percent))}%` : '35%';
  const meter = $('#progress-meter');
  if (known) meter.setAttribute('aria-valuenow', String(Math.round(data.percent)));
  else meter.removeAttribute('aria-valuenow');
  const labels = {choosing: 'Escolha onde salvar', preparing: 'Preparando o download', processing: container.value === 'mp3' ? 'Convertendo áudio para MP3' : (selectedRange ? 'Recortando o trecho / ajustando formato' : 'Juntando áudio e vídeo / ajustando formato'), saving: 'Salvando arquivo', complete: 'Download concluído'};
  progressLabel.textContent = data.state === 'downloading' ? `Baixando ${data.track === 'Áudio' ? 'áudio' : 'vídeo'}` : (labels[data.state] || 'Preparando');
  $('#progress-value').textContent = known ? `${data.estimated ? '≈ ' : ''}${Math.floor(data.percent)}%` : '…';
  const details = [];
  if (data.speed > 0) details.push(`${(data.speed / 1024 / 1024).toFixed(1)} MB/s`);
  if (Number.isFinite(data.eta)) details.push(`Faltam ~${Math.ceil(data.eta)} s`);
  if (data.state === 'downloading') details.push('Progresso da faixa atual');
  $('#progress-detail').textContent = details.join(' · ');
}
async function request(path, body) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível concluir. Confira o link e tente novamente.');
  }
  return response;
}
const selectionDialog = $('#selection-dialog');
function parseTimestamp(text) {
  const value = text.trim();
  if (!/^\d+:([0-5]\d)(:([0-5]\d))?$/.test(value)) throw new Error('Use mm:ss ou hh:mm:ss em ambos os campos.');
  return value.split(':').reduce((total, part) => total * 60 + Number(part), 0);
}
function formatTimestamp(seconds) {
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds / 60) % 60;
  return `${hours ? hours + ':' + String(minutes).padStart(2, '0') : Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
function validateRange(range) {
  if (!range) return;
  if (!Number.isSafeInteger(range.start_time) || !Number.isSafeInteger(range.end_time) || range.end_time <= range.start_time) throw new Error('O fim do trecho precisa ser maior que o início.');
  if (Number.isFinite(videoDuration) && (range.start_time >= videoDuration || range.end_time > videoDuration)) throw new Error(`O trecho deve ficar dentro da duração do vídeo (${formatTimestamp(videoDuration)}).`);
}
function showSelection(trigger = url) {
  if (busy || selectionDialog.open) return;
  selectionTrigger = trigger;
  $('#selection-error').textContent = '';
  $(`input[name="selection-mode"][value="${selectedRange ? 'clip' : 'full'}"]`).checked = true;
  $('#clip-fields').hidden = !selectedRange;
  $('#clip-start').value = selectedRange ? formatTimestamp(selectedRange.start_time) : '';
  $('#clip-end').value = selectedRange ? formatTimestamp(selectedRange.end_time) : '';
  selectionDialog.showModal();
}
$('#selection-form').addEventListener('change', event => {
  if (event.target.name === 'selection-mode') {
    $('#clip-fields').hidden = event.target.value !== 'clip';
    $('#selection-error').textContent = '';
    if (event.target.value === 'clip') $('#clip-start').focus();
  }
});
$('#selection-form').addEventListener('submit', event => {
  event.preventDefault();
  try {
    const range = $('input[name="selection-mode"]:checked').value === 'clip' ? {start_time: parseTimestamp($('#clip-start').value), end_time: parseTimestamp($('#clip-end').value)} : null;
    validateRange(range);
    selectedRange = range; chosenLink = url.value.trim();
    $('#selection-label').textContent = range ? `Trecho · ${formatTimestamp(range.start_time)} → ${formatTimestamp(range.end_time)}` : 'Vídeo inteiro';
    selectionDialog.close();
    if (selectedUrl !== chosenLink) form.requestSubmit();
    else message('');
  } catch (error) { $('#selection-error').textContent = error.message; }
});
selectionDialog.addEventListener('close', () => selectionTrigger.focus());
$('#edit-selection').addEventListener('click', () => showSelection($('#edit-selection')));
url.addEventListener('input', () => { result.hidden = true; progress.hidden = true; selectedUrl = ''; chosenLink = ''; selectedRange = null; videoDuration = null; message(''); });
url.addEventListener('paste', event => {
  const pasted = event.clipboardData?.getData('text')?.trim();
  if (!pasted) return;
  setTimeout(() => { if (!busy && url.value.trim() && url.validity.valid) showSelection(); }, 0);
});
form.addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  if (chosenLink !== url.value.trim()) { showSelection(analyze); return; }
  setBusy(true); result.hidden = true; progress.hidden = true;
  message('Buscando o vídeo e as qualidades disponíveis…');
  try {
    const link = url.value.trim();
    const data = await (await request('/api/info', {url: link})).json();
    selectedUrl = link; videoTitle = data.title; videoDuration = Number.isFinite(data.duration) ? data.duration : null;
    $('#title').textContent = data.title;
    $('#meta').textContent = [data.uploader, data.duration ? `${Math.floor(data.duration / 60)}:${String(Math.floor(data.duration % 60)).padStart(2, '0')}` : ''].filter(Boolean).join(' · ');
    quality.replaceChildren(...data.qualities.map(height => {
      const option = document.createElement('option'); option.value = height;
      option.textContent = `${height}p${height === 2160 ? ' · 4K' : height === 1440 ? ' · QHD' : height === 1080 ? ' · Full HD' : height === 720 ? ' · HD' : ''}`;
      return option;
    }));
    if (!data.qualities.length) {
      const original = document.createElement('option'); original.value = 4320; original.textContent = 'Original · resolução não informada'; quality.append(original);
    } else { quality.value = data.qualities.find(h => h <= 1080) || data.qualities[0]; }
    result.hidden = false;
    try { validateRange(selectedRange); message(''); } catch (error) { message(error.message + ' Clique em Alterar trecho.', true); }
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
});
async function followDownload() {
  for (;;) {
    const data = await window.pywebview.api.get_progress();
    if (data.state === 'error') throw new Error(data.error);
    showProgress(data);
    if (data.state === 'complete') return data;
    await new Promise(resolve => setTimeout(resolve, 350));
  }
}
download.addEventListener('click', async () => {
  if (!selectedUrl || busy) return;
  try { validateRange(selectedRange); } catch (error) { message(error.message, true); showSelection($('#edit-selection')); return; }
  prepareAudio(); setBusy(true); message('');
  showProgress({state: 'preparing', percent: null});
  progress.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  try {
    if (window.pywebview?.api) {
      const outcome = await window.pywebview.api.start_download(selectedUrl, Number(quality.value), container.value, videoTitle, selectedRange?.start_time ?? null, selectedRange?.end_time ?? null);
      if (outcome.error) throw new Error(outcome.error);
      if (outcome.cancelled) { progress.hidden = true; message('Salvamento cancelado.'); return; }
      const completed = await followDownload();
      message(container.value === 'mp3' ? 'Áudio salvo! Pronto para ouvir.' : 'Vídeo salvo! Pronto para levar com você.');
      notifyComplete(completed.filename || 'Seu vídeo foi salvo.');
      return;
    }
    message('Preparando o vídeo. O progresso detalhado está disponível no aplicativo Windows.');
    const response = await request('/api/download', {url: selectedUrl, quality: Number(quality.value), container: container.value, ...(selectedRange || {})});
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = objectUrl;
    const disposition = response.headers.get('Content-Disposition') || '';
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    anchor.download = encoded ? decodeURIComponent(encoded[1]) : (disposition.match(/filename="([^"]+)"/)?.[1] || `kupotube.${container.value}`);
    document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    showProgress({state: 'complete', percent: 100});
    message('Arquivo enviado aos downloads do navegador.'); notifyComplete('Arquivo pronto para salvar no navegador.');
  } catch (error) { progress.hidden = true; message(error.message, true); }
  finally { setBusy(false); }
});

container.addEventListener('change', () => {
  const audio = container.value === 'mp3';
  $('#quality-field').hidden = audio;
  quality.disabled = busy || audio;
  $('#download-label').textContent = audio ? 'Baixar MP3' : 'Baixar vídeo';
  $('#format-note').textContent = audio ? 'Somente áudio · MP3 a 192 kbps. A conversão pode levar alguns segundos.' : 'Áudio incluído. WebM depende de faixas compatíveis; MKV aceita mais codecs.';
});
$('#import-session').addEventListener('click', async () => {
  if (!window.pywebview?.api) { message('Importar sessão está disponível no app Windows.'); return; }
  try {
    const answer = await window.pywebview.api.import_session();
    if (answer.error) throw new Error(answer.error);
    if (answer.imported) message('Sessão importada neste computador. Busque o vídeo novamente.');
  } catch (error) { message(error.message, true); }
});
$('#remove-session').addEventListener('click', async () => {
  if (!window.pywebview?.api) return;
  try {
    const answer = await window.pywebview.api.remove_session();
    if (answer.error) throw new Error(answer.error);
    message('Sessão removida deste computador.');
  } catch (error) { message(error.message, true); }
});
let checkingUpdate = false, lastUpdateCheck = 0, updateTimer;
function updateDialog(title, description, version = '', error = false) {
  $('#update-dialog-title').textContent = title;
  $('#update-dialog-description').textContent = description;
  $('#update-dialog-version').textContent = version ? `VERSÃO ${version}` : '';
  $('#update-dialog-version').hidden = !version;
  $('#update-dialog-icon').src = error ? '/icons/arrows-clockwise.svg' : '/icons/check-circle.svg';
  $('#update-dialog').classList.toggle('dialog-error', error);
  $('#update-dialog-confirm').textContent = error ? 'Entendi' : 'Tudo certo';
  if (!$('#update-dialog').open) $('#update-dialog').showModal();
}
$('#update-dialog').addEventListener('close', () => $('#check-update').focus());
$('#update-dialog').addEventListener('click', event => {
  if (event.target !== $('#update-dialog')) return;
  const box = event.target.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close();
});
async function checkUpdate(manual = false) {
  if (!window.pywebview?.api?.check_update) { if (manual) updateDialog('Atualizações no aplicativo', 'Abra o Kupotube para Windows para verificar e instalar atualizações.', '', true); return; }
  if (checkingUpdate) return;
  checkingUpdate = true; $('#check-update').disabled = true;
  $('#check-update').setAttribute('aria-busy', 'true');
  $('#check-update-label').textContent = 'Verificando…';
  try {
    const answer = await window.pywebview.api.check_update();
    if (answer.current) $('#app-version').textContent = 'v' + answer.current;
    if (answer.error) throw new Error(answer.error);
    lastUpdateCheck = Date.now();
    if (answer.available) {
      $('#update-title').textContent = `Kupotube ${answer.version} disponível`;
      $('#update-banner').hidden = false;
      $('#check-update').classList.add('has-update');
      $('#check-update').title = 'Uma nova versão está disponível';
      if (manual) $('#update-banner').scrollIntoView({behavior:'smooth', block:'start'});
    } else {
      $('#update-banner').hidden = true;
      $('#check-update').classList.remove('has-update');
      $('#check-update').removeAttribute('title');
      if (manual) updateDialog('O Kupo já está atualizado!', 'Você está com a versão mais recente. Tudo pronto para baixar seus próximos favoritos.', answer.current);
    }
  } catch (error) { if (manual) updateDialog('Não foi possível verificar', error.message, '', true); }
  finally {
    checkingUpdate = false; $('#check-update').disabled = false;
    $('#check-update').setAttribute('aria-busy', 'false');
    $('#check-update-label').textContent = 'Verificar atualizações';
  }
}
$('#check-update').addEventListener('click', () => checkUpdate(true));
async function desktopReady() {
  checkUpdate();
  updateTimer ||= setInterval(() => { if (!busy && !document.hidden) checkUpdate(); }, 15 * 60 * 1000);
  if (window.pywebview?.api?.get_preferences) {
    try { soundEnabled = (await window.pywebview.api.get_preferences()).sound !== false; updateSound(); } catch (_) {}
  }
}
window.addEventListener('focus', () => { if (!busy && Date.now() - lastUpdateCheck > 2 * 60 * 1000) checkUpdate(); });
window.addEventListener('pywebviewready', desktopReady);
if (window.pywebview?.api) desktopReady();
$('#install-update').addEventListener('click', async () => {
  if (busy || !window.pywebview?.api) return;
  setBusy(true); $('#install-update').disabled = true;
  try {
    const answer = await window.pywebview.api.install_update();
    if (answer.error) throw new Error(answer.error);
    for (;;) {
      const state = await window.pywebview.api.get_update_progress();
      if (state.state === 'error') throw new Error(state.error);
      $('#update-detail').textContent = state.state === 'restarting' ? 'Atualização verificada. Reiniciando o Kupotube…' : `Baixando atualização… ${state.percent || 0}%`;
      if (state.state === 'restarting') return;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); $('#install-update').disabled = false; }
});

const cookiesDialog = $('#cookies-dialog');
$('#cookies-help').addEventListener('click', () => { if (!cookiesDialog.open) cookiesDialog.showModal(); });
cookiesDialog.addEventListener('close', () => $('#cookies-help').focus());
cookiesDialog.addEventListener('click', event => {
  if (event.target !== cookiesDialog) return;
  const bounds = cookiesDialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) cookiesDialog.close();
});

const releasesDialog = $('#releases-dialog');
$('#release-news').addEventListener('click', () => { if (!releasesDialog.open) releasesDialog.showModal(); });
releasesDialog.addEventListener('close', () => $('#release-news').focus());
releasesDialog.addEventListener('click', event => {
  if (event.target !== releasesDialog) return;
  const bounds = releasesDialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) releasesDialog.close();
});
