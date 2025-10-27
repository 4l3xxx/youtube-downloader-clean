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
  statusEl.textContent = 'Starting job...';
  savedEl.textContent = '';
  errBox.removeAttribute('open');
  logEl.textContent = '';
  const pg = document.getElementById('progress');
  const bar = document.getElementById('bar');
  const meta = document.getElementById('meta');
  pg.hidden = false; bar.style.width = '0%'; meta.textContent = '0% • ETA --s • -- MB/s';
  try{
    // Start async job on the server to avoid host timeouts
    const r = await api('/api/download',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url:u,quality:quality.value,async:true})
    });
    const j = await r.json().catch(()=>({ok:false,error:'Invalid JSON'}));
    if(!r.ok || !j.ok || !j.task_id){
      const msg = j.error || 'Failed to start job.';
      statusEl.innerHTML = `<span class="error">Failed.</span>`;
      savedEl.textContent = 'See error details below.';
      logEl.textContent = msg;
      errBox.setAttribute('open','');
      return;
    }
    const task = j.task_id;
    statusEl.textContent = 'Downloading...';
    let done = false;
    while(!done){
      await new Promise(r=>setTimeout(r,1000));
      let pr;
      try{ const rr = await api(`/api/progress?task=${encodeURIComponent(task)}`); pr = await rr.json(); }
      catch(e){ break; }
      if(!pr || !pr.ok){ break; }
      const pct = Math.max(0, Math.min(100, pr.progress||0));
      bar.style.width = pct + '%';
      const eta = pr.eta!=null ? pr.eta+'s' : '--s';
      const spd = pr.speed ? (pr.speed/1048576).toFixed(2)+' MB/s' : '-- MB/s';
      meta.textContent = `${pct}% • ETA ${eta} • ${spd}`;
      if(pr.status === 'completed'){
        done = true;
        // Fetch the result file
        const fr = await api(`/api/result?task=${encodeURIComponent(task)}`);
        if(!fr.ok){
          statusEl.innerHTML = `<span class="error">Failed to fetch file.</span>`;
          try{ const jj = await fr.json(); logEl.textContent = jj.error || 'Unknown error'; errBox.setAttribute('open',''); }catch{}
          break;
        }
        const cd = fr.headers.get('Content-Disposition') || '';
        let fname = 'video.mp4';
        const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
        if(m){ fname = decodeURIComponent(m[1] || m[2] || fname); }
        const blob = await fr.blob();
        const href = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = href;
        a.download = fname;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(href);
        statusEl.textContent = 'Done. Check your Downloads.';
      } else if(pr.status === 'error'){
        done = true;
        statusEl.innerHTML = `<span class="error">Failed.</span>`;
        savedEl.textContent = 'See error details below.';
        logEl.textContent = pr.log || 'Unknown error';
        errBox.setAttribute('open','');
      }
    }
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

