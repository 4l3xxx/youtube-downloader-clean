const $ = (s) => document.querySelector(s);
const url = $('#url');
const quality = $('#quality');
const btn = $('#btn');
const statusEl = $('#status');
const savedEl = $('#saved');
const logEl = $('#log');
const errBox = $('#errbox');
const ytPill = $('#yt-pill');
const ffPill = $('#ff-pill');
const dlPath = $('#dlpath');
const refreshBtn = $('#refresh');
const ffLoc = $('#ffloc');

// Determine API base: same origin if served via http, otherwise fallback to localhost
const API_BASE = (() => {
  try{
    const o = window.location.origin || '';
    if (o.startsWith('http')) return o;
  }catch{}
  return 'http://127.0.0.1:5231';
})();

function api(path, opts){
  return fetch(`${API_BASE}${path}`, opts);
}

async function refreshHealth(){
  try{
    const r = await api('/api/health');
    const j = await r.json();
    ytPill.classList.toggle('ok', !!j.yt_dlp);
    ytPill.classList.toggle('bad', !j.yt_dlp);
    ffPill.classList.toggle('ok', !!j.ffmpeg);
    ffPill.classList.toggle('bad', !j.ffmpeg);
    dlPath.textContent = `Downloads folder: ${j.download_dir}`;
    ffLoc.textContent = `FFmpeg: ${j.ffmpeg_location || '(unknown)'}`;
  }catch(e){
    ytPill.classList.remove('ok'); ytPill.classList.add('bad');
    ffPill.classList.remove('ok'); ffPill.classList.add('bad');
    dlPath.textContent = 'Downloads folder: (unknown)';
    ffLoc.textContent = 'FFmpeg: (unknown)';
  }
}

refreshHealth();
refreshBtn?.addEventListener('click', refreshHealth);

async function download(){
  const u = url.value.trim();
  if(!u){
    statusEl.textContent = 'Please paste a YouTube URL.';
    return;
  }
  btn.disabled = true;
  statusEl.textContent = 'Preparing download...';
  savedEl.textContent = '';
  errBox.removeAttribute('open');
  logEl.textContent = '';
  const pg = document.getElementById('progress');
  pg.hidden = true;
  try{
    const r = await api('/api/download',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url:u,quality:quality.value})
    });
    if(!r.ok){
      let msg = 'Request failed.';
      try{ const j = await r.json(); msg = j.error || j.output || msg; }catch{}
      statusEl.innerHTML = `<span class="error">Failed.</span>`;
      savedEl.textContent = 'See error details below.';
      logEl.textContent = msg;
      errBox.setAttribute('open','');
      return;
    }
    const cd = r.headers.get('Content-Disposition') || '';
    let fname = 'video.mp4';
    const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
    if(m){ fname = decodeURIComponent(m[1] || m[2] || fname); }
    const blob = await r.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = href;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);
    statusEl.textContent = 'Download started. Check your Downloads.';
  }catch(e){
    statusEl.innerHTML = `<span class="error">Failed.</span>`;
    savedEl.textContent = 'See error details below.';
    logEl.textContent = String(e);
    errBox.setAttribute('open','');
  }finally{
    btn.disabled = false;
  }
}

btn.addEventListener('click', download);
url.addEventListener('keydown', (e)=>{ if(e.key==='Enter') download(); });

