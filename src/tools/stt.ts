import { getKey } from '../core/config';
// eslint-disable-next-line @typescript-eslint/no-var-requires
const FormData = require('form-data');

export async function transcribeVoice(audioBuffer: Buffer, filename = 'voice.ogg'): Promise<string> {
  const key = getKey('groq');
  if (!key) throw new Error('No Groq key for STT');

  const form = new FormData();
  form.append('file', audioBuffer, { filename, contentType: 'audio/ogg' });
  form.append('model', 'whisper-large-v3-turbo');
  form.append('response_format', 'text');

  // Use node-fetch v2 (CommonJS)
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const fetch = require('node-fetch');

  const r = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, ...form.getHeaders() },
    body: form
  });

  if (!r.ok) {
    const err = await r.text();
    throw new Error(`Groq STT error ${r.status}: ${err}`);
  }

  const text = await r.text();
  return text.trim();
}
