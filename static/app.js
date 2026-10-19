const $ = selector => document.querySelector(selector);
const form = $('#form'), url = $('#url'), result = $('#result'), status = $('#status');
const analyze = $('#analyze'), download = $('#download'), quality = $('#quality'), container = $('#container');
const progress = $('#progress'), progressBar = $('#progress-bar'), progressLabel = $('#progress-label');
let selectedUrl = '', videoTitle = '', busy = false, audioContext, toastTimer;
let chosenLink = '', selectedRange = null, videoDuration = null, selectionTrigger = url;
let toastExit;
const expansionAnimations = new Map();
let soundEnabled = localStorage.getItem('kupotube-sound') !== 'off';
function message(text, error = false) { $('#reveal-download').hidden = true; status.textContent = text; status.classList.toggle('error', error); }
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
  toastExit?.cancel(); toastExit = null;
  $('#toast-text').textContent = text;
  $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(dismissToast, 8000);
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
async function dismissToast() {
  clearTimeout(toastTimer);
  const toast = $('#toast');
  if (toast.hidden || toastExit) return;
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const animation = toast.animate([{opacity:1,transform:'translateY(0)'},{opacity:0,transform:'translateY(6px)'}], {duration:160,easing:'ease-in',fill:'forwards'});
    toastExit = animation;
    try { await animation.finished; } catch (_) { return; }
    if (toastExit !== animation) return;
    toast.hidden = true; toastExit = null; animation.cancel();
  } else toast.hidden = true;
  if (toast.contains(document.activeElement)) download.focus();
}
$('#toast-close').addEventListener('click', dismissToast);
function resetDownloadDisplay() {
  $('#reveal-download').hidden = true;
  $('#clear-result').hidden = true;
  $('#download-destination').hidden = true;
  $('#download-destination span').textContent = '';
}
$('#clear-result').addEventListener('click', () => {
  if (busy) return;
  url.value = ''; url.dispatchEvent(new Event('input'));
  videoTitle = ''; quality.replaceChildren(); $('#title').textContent = ''; $('#meta').textContent = '';
  $('#clip-start').value = ''; $('#clip-end').value = '';
  dismissToast(); url.focus();
});
$('#reveal-download').addEventListener('click', async () => {
  try {
    const answer = await window.pywebview.api.reveal_download();
    if (answer.error) message(answer.error, true);
  } catch (_) { message('Não foi possível abrir o local do arquivo.', true); }
});
function showProgress(data) {
  if (data.folder) {
    $('#download-destination').hidden = false;
    $('#download-destination span').textContent = data.folder;
  }
  progress.hidden = false;
  const known = Number.isFinite(data.percent);
  progressBar.classList.toggle('indeterminate', !known);
  progressBar.style.width = known ? `${Math.max(0, Math.min(100, data.percent))}%` : '35%';
  const meter = $('#progress-meter');
  if (known) meter.setAttribute('aria-valuenow', String(Math.round(data.percent)));
  else meter.removeAttribute('aria-valuenow');
  const labels = {cutting: 'Recortando o arquivo baixado', choosing: 'Escolha onde salvar', preparing: 'Preparando o download', processing: container.value === 'mp3' ? 'Convertendo áudio para MP3' : (selectedRange ? 'Recortando o trecho / ajustando formato' : 'Juntando áudio e vídeo / ajustando formato'), saving: 'Salvando arquivo', complete: 'Download concluído'};
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
  resetReveal($('#clip-fields'), Boolean(selectedRange));
  $('#clip-start').value = selectedRange ? formatTimestamp(selectedRange.start_time) : '';
  $('#clip-end').value = selectedRange ? formatTimestamp(selectedRange.end_time) : '';
  $('#clip-format').value = container.value;
  selectionDialog.showModal();
}
$('#selection-form').addEventListener('change', event => {
  if (event.target.name === 'selection-mode') {
    reveal($('#clip-fields'), event.target.value === 'clip');
    $('#selection-error').textContent = '';
    if (event.target.value === 'clip') $('#clip-start').focus();
  }
});
$('#selection-form').addEventListener('submit', event => {
  event.preventDefault();
  try {
    const range = $('input[name="selection-mode"]:checked').value === 'clip' ? {start_time: parseTimestamp($('#clip-start').value), end_time: parseTimestamp($('#clip-end').value)} : null;
    validateRange(range);
    if (range) { container.value = $('#clip-format').value; container.dispatchEvent(new Event('change')); }
    selectedRange = range; chosenLink = url.value.trim();
    $('#selection-label').textContent = range ? `Trecho · ${formatTimestamp(range.start_time)} → ${formatTimestamp(range.end_time)}` : 'Vídeo inteiro';
    selectionDialog.close();
    if (selectedUrl !== chosenLink) form.requestSubmit();
    else message('');
  } catch (error) { $('#selection-error').textContent = error.message; }
});
selectionDialog.addEventListener('close', () => selectionTrigger.focus());
$('#edit-selection').addEventListener('click', () => showSelection($('#edit-selection')));
url.addEventListener('input', () => { resetDownloadDisplay(); result.hidden = true; progress.hidden = true; selectedUrl = ''; chosenLink = ''; selectedRange = null; videoDuration = null; container.value = 'mp4'; container.dispatchEvent(new Event('change')); message(''); });
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
  resetDownloadDisplay(); prepareAudio(); setBusy(true); message('');
  showProgress({state: 'preparing', percent: null});
  progress.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  try {
    if (window.pywebview?.api) {
      const outcome = await window.pywebview.api.start_download(selectedUrl, Number(quality.value), container.value, videoTitle, selectedRange?.start_time ?? null, selectedRange?.end_time ?? null);
      if (outcome.error) throw new Error(outcome.error);
      if (outcome.cancelled) { progress.hidden = true; message('Salvamento cancelado.'); return; }
      const completed = await followDownload();
      message(container.value === 'mp3' ? 'Áudio salvo na pasta escolhida.' : 'Vídeo salvo na pasta escolhida.');
      $('#reveal-download').hidden = false; $('#clear-result').hidden = false;
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
    $('#clear-result').hidden = false;
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
      if (manual) updateDialog('O Kupo já está atualizado!', 'Nenhuma atualização disponível para esta versão.', answer.current);
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

// Animate only an empty, unfocused input; never change the user's text.
const placeholderPhrases = ['Cole o link do vídeo aqui…', 'Um vídeo do YouTube? Cole aqui…', 'TikTok ou Reels? É só colar o link…'];
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let placeholderTimer, phraseIndex = 0, typedCharacters = placeholderPhrases[0].length, erasingPlaceholder = true;
function animatePlaceholder() {
  clearTimeout(placeholderTimer);
  if (reducedMotion.matches || document.hidden || document.activeElement === url || url.value || busy) {
    url.placeholder = placeholderPhrases[0]; return;
  }
  const phrase = placeholderPhrases[phraseIndex];
  typedCharacters += erasingPlaceholder ? -1 : 1;
  url.placeholder = phrase.slice(0, Math.max(0, typedCharacters));
  let delay = erasingPlaceholder ? 32 : 65;
  if (typedCharacters <= 0) { phraseIndex = (phraseIndex + 1) % placeholderPhrases.length; erasingPlaceholder = false; delay = 250; }
  else if (typedCharacters >= phrase.length) { erasingPlaceholder = true; delay = 2200; }
  placeholderTimer = setTimeout(animatePlaceholder, delay);
}
function restartPlaceholder() {
  clearTimeout(placeholderTimer);
  phraseIndex = 0; typedCharacters = placeholderPhrases[0].length; erasingPlaceholder = true;
  url.placeholder = placeholderPhrases[0];
  if (!reducedMotion.matches && !document.hidden && document.activeElement !== url && !url.value) placeholderTimer = setTimeout(animatePlaceholder, 2200);
}
url.addEventListener('focus', restartPlaceholder);
url.addEventListener('blur', restartPlaceholder);
url.addEventListener('input', restartPlaceholder);
document.addEventListener('visibilitychange', restartPlaceholder);
reducedMotion.addEventListener('change', restartPlaceholder);
restartPlaceholder();

// One version at a time; the archived notes stay available without growing the dialog.
const releaseEntries = [...$('#release-archive').content.querySelectorAll('details')];
const releasePicker = $('#release-picker');
releasePicker.replaceChildren(...releaseEntries.map((entry,index) => {
  const option = document.createElement('option'); option.value = index;
  const version = entry.querySelector('summary span').firstChild.textContent.trim();
  option.textContent = version + (index === 0 ? ' · atual' : '');
  return option;
}));
let releaseAnimation;
function showRelease(index, animate = true) {
  const entry = releaseEntries[index], panel = $('#release-content');
  if (!entry) return;
  const oldHeight = panel.getBoundingClientRect().height;
  releaseAnimation?.cancel(); panel.style.removeProperty('overflow');
  releasePicker.value = String(index);
  const meta = document.createElement('div'); meta.className = 'release-meta';
  const version = document.createElement('span'); version.className = 'release-version';
  version.textContent = entry.querySelector('summary span').firstChild.textContent.trim();
  const badge = document.createElement('span'); badge.className = 'release-badge';
  badge.textContent = index === 0 ? 'ATUAL' : 'ARQUIVO';
  meta.append(version,badge);
  const title = document.createElement('h3'); title.textContent = entry.querySelector('summary span:last-child').textContent;
  panel.replaceChildren(meta,title,entry.querySelector('ul').cloneNode(true));
  $('#release-newer').disabled = index === 0;
  $('#release-older').disabled = index === releaseEntries.length - 1;
  $('#release-position').textContent = `${index + 1} / ${releaseEntries.length}`;
  if (animate && !reducedMotion.matches) {
    const newHeight = panel.getBoundingClientRect().height; panel.style.overflow = 'hidden';
    const animation = panel.animate([{height:oldHeight+'px',opacity:.25},{height:newHeight+'px',opacity:1}],{duration:180,easing:'ease-out'});
    releaseAnimation = animation;
    animation.finished.then(() => { if (releaseAnimation === animation) panel.style.removeProperty('overflow'); }).catch(() => {});
  }
}
releasePicker.addEventListener('change', () => showRelease(Number(releasePicker.value)));
$('#release-newer').addEventListener('click', () => showRelease(Number(releasePicker.value) - 1));
$('#release-older').addEventListener('click', () => showRelease(Number(releasePicker.value) + 1));
showRelease(0,false);

// Native details keep keyboard semantics. Only their height is animated.
function finishExpansion(element) {
  const existing = expansionAnimations.get(element);
  if (existing) { existing.cancel(); expansionAnimations.delete(element); }
  element.style.removeProperty('height'); element.style.removeProperty('overflow'); element.style.removeProperty('opacity');
}
function resetReveal(element, expanded) { finishExpansion(element); element.hidden = !expanded; }
function reveal(element, expanded) {
  const currentHeight = element.hidden ? 0 : element.getBoundingClientRect().height;
  finishExpansion(element);
  if (reducedMotion.matches) { element.hidden = !expanded; return; }
  element.hidden = false;
  const endHeight = expanded ? element.scrollHeight : 0;
  element.style.overflow = 'hidden';
  const animation = element.animate([{height:currentHeight+'px',opacity:currentHeight ? 1 : 0},{height:endHeight+'px',opacity:expanded ? 1 : 0}],{duration:220,easing:'cubic-bezier(.2,.7,.2,1)'});
  expansionAnimations.set(element,animation);
  animation.finished.then(() => {
    if (expansionAnimations.get(element) !== animation) return;
    expansionAnimations.delete(element); element.hidden = !expanded;
    element.style.removeProperty('overflow');
  }).catch(() => {});
}
document.querySelectorAll('details').forEach(details => {
  const summary = details.querySelector('summary');
  const body = document.createElement('div'); body.className = 'details-body';
  [...details.childNodes].filter(node => node !== summary).forEach(node => body.append(node));
  details.append(body);
  let expanded = details.open;
  summary.addEventListener('click', event => {
    event.preventDefault(); expanded = !expanded;
    const start = details.getBoundingClientRect().height;
    finishExpansion(details);
    if (reducedMotion.matches) { details.open = expanded; return; }
    details.open = true;
    const style = getComputedStyle(details);
    const collapsed = summary.getBoundingClientRect().height + parseFloat(style.paddingTop) + parseFloat(style.paddingBottom) + parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    const end = expanded ? details.getBoundingClientRect().height : collapsed;
    details.style.overflow = 'hidden';
    const animation = details.animate([{height:start+'px'},{height:end+'px'}],{duration:220,easing:'cubic-bezier(.2,.7,.2,1)'});
    expansionAnimations.set(details,animation);
    animation.finished.then(() => {
      if (expansionAnimations.get(details) !== animation) return;
      expansionAnimations.delete(details); details.open = expanded; details.style.removeProperty('overflow');
    }).catch(() => {});
  });
});
reducedMotion.addEventListener('change', () => {
  if (!reducedMotion.matches) return;
  releaseAnimation?.cancel(); $('#release-content').style.removeProperty('overflow');
  for (const animation of expansionAnimations.values()) animation.finish();
});
