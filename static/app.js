const form = document.querySelector('#form');
const url = document.querySelector('#url');
const result = document.querySelector('#result');
const status = document.querySelector('#status');
const analyze = document.querySelector('#analyze');
const download = document.querySelector('#download');
const quality = document.querySelector('#quality');
let selectedUrl = '';
let busy = false;
function message(text, error = false) { status.textContent = text; status.classList.toggle('error', error); }
async function request(path, body) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível concluir. Confira o link e tente novamente.');
  }
  return response;
}
url.addEventListener('input', () => { result.hidden = true; selectedUrl = ''; message(''); });
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  busy = true; analyze.disabled = true; url.disabled = true; result.hidden = true;
  message('Buscando o vídeo e as qualidades disponíveis…');
  try {
    const link = url.value.trim();
    const data = await (await request('/api/info', {url: link})).json();
    selectedUrl = link;
    document.querySelector('#title').textContent = data.title;
    document.querySelector('#meta').textContent = [data.uploader, data.duration ? `${Math.floor(data.duration / 60)}:${String(Math.floor(data.duration % 60)).padStart(2, '0')}` : ''].filter(Boolean).join(' · ');
    quality.replaceChildren(...data.qualities.map(height => {
      const option = document.createElement('option'); option.value = height;
      option.textContent = `${height}p${height === 2160 ? ' · 4K' : height === 1440 ? ' · QHD' : height === 1080 ? ' · Full HD' : height === 720 ? ' · HD' : ''}`;
      return option;
    }));
    quality.value = data.qualities.find(h => h <= 1080) || data.qualities[0];
    result.hidden = false; message('');
  } catch (error) { message(error.message, true); }
  finally { busy = false; analyze.disabled = false; url.disabled = false; }
});
download.addEventListener('click', async () => {
  if (!selectedUrl || busy) return;
  busy = true; download.disabled = true; analyze.disabled = true; url.disabled = true;
  message('Preparando seu vídeo… O download começará quando o arquivo estiver pronto.');
  try {
    if (window.pywebview?.api) {
      const outcome = await window.pywebview.api.save_video(selectedUrl, Number(quality.value));
      if (outcome.error) throw new Error(outcome.error);
      message(outcome.cancelled ? 'Salvamento cancelado.' : 'Vídeo salvo! Pronto para levar com você.');
      return;
    }
    const response = await request('/api/download', {url: selectedUrl, quality: Number(quality.value)});
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = objectUrl;
    const disposition = response.headers.get('Content-Disposition') || '';
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    anchor.download = encoded ? decodeURIComponent(encoded[1]) : (disposition.match(/filename="([^"]+)"/)?.[1] || 'kupotube.mp4');
    document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    message('Arquivo pronto! Confira os downloads do navegador.');
  } catch (error) { message(error.message, true); }
  finally { busy = false; download.disabled = false; analyze.disabled = false; url.disabled = false; }
});
