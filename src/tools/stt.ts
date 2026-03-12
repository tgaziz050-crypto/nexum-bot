import FormData from 'form-data';
import { getKey } from '../core/config.ts';

export async function transcribeVoice(audioBuffer: Buffer, filename = 'voice.ogg'): Promise<string> {
  const key = getKey('groq');
  if (!key) throw new Error('No Groq key for STT');

  const form = new FormData();
  form.append('file', audioBuffer, { filename, contentType: 'audio/ogg' });
  form.append('model', 'whisper-large-v3-turbo');
  form.append('response_format', 'text');

  const r = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, ...form.getHeaders() },
    body: form as any
  });

  if (!r.ok) {
    const err = await r.text();
    throw new Error(`Groq STT error ${r.status}: ${err}`);
  }

  const text = await r.text();
  return text.trim();
}
