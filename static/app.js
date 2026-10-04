const form = document.querySelector('#speech-form');
const text = document.querySelector('#text');
const count = document.querySelector('#count');
const voice = document.querySelector('#voice');
const speed = document.querySelector('#speed');
const speedValue = document.querySelector('#speed-value');
const generate = document.querySelector('#generate');
const generateLabel = document.querySelector('#generate-label');
const status = document.querySelector('#status');
const result = document.querySelector('#result');
const player = document.querySelector('#player');
const download = document.querySelector('#download');
const resultVoice = document.querySelector('#result-voice');
let audioUrl = null;
let busy = false;

function setStatus(message, error = false) {
  status.textContent = message;
  status.classList.toggle('error', error);
}

function updateForm() {
  count.textContent = `${text.value.length.toLocaleString()} / 5,000`;
  generate.disabled = busy || !text.value.trim() || !voice.value;
}

function clearAudio() {
  player.pause();
  player.removeAttribute('src');
  player.load();
  download.removeAttribute('href');
  result.hidden = true;
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = null;
}

text.addEventListener('input', updateForm);
voice.addEventListener('change', updateForm);
speed.addEventListener('input', () => {
  speedValue.value = `${Number(speed.value).toFixed(2)}×`;
});

async function loadVoices() {
  try {
    const response = await fetch('/api/voices');
    if (!response.ok) throw new Error('Could not load voices. Refresh the page to try again.');
    const groups = await response.json();
    voice.replaceChildren();
    for (const group of groups) {
      const optgroup = document.createElement('optgroup');
      optgroup.label = group.group;
      for (const item of group.voices) {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = item.name;
        optgroup.append(option);
      }
      voice.append(optgroup);
    }
    voice.value = 'af_heart';
    voice.disabled = false;
    updateForm();
  } catch (error) {
    voice.replaceChildren(new Option('Voices unavailable', ''));
    setStatus(error.message, true);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !text.value.trim() || !voice.value) return;
  clearAudio();
  busy = true;
  generateLabel.textContent = 'Generating…';
  setStatus('Generating speech… The first run may download model files and take a few minutes.');
  updateForm();
  const selectedVoice = voice.selectedOptions[0].textContent;
  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value, voice: voice.value, speed: Number(speed.value) })
    });
    if (!response.ok) {
      let message = `Generation failed (HTTP ${response.status}).`;
      try {
        const body = await response.json();
        if (typeof body.detail === 'string') message = body.detail;
      } catch { /* Keep HTTP fallback. */ }
      throw new Error(message);
    }
    const blob = await response.blob();
    audioUrl = URL.createObjectURL(blob);
    player.src = audioUrl;
    download.href = audioUrl;
    resultVoice.textContent = selectedVoice;
    result.hidden = false;
    setStatus('Done. Play the audio or download the MP3.');
  } catch (error) {
    setStatus(error.message || 'Could not generate audio. Please try again.', true);
  } finally {
    busy = false;
    generateLabel.textContent = 'Generate audio';
    updateForm();
  }
});

window.addEventListener('pagehide', () => {
  if (audioUrl) URL.revokeObjectURL(audioUrl);
});
loadVoices();
