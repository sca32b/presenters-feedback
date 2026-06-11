/**
 * Audio recording component using the MediaRecorder API.
 */

import { getUploadUrl, uploadAudio, startAnalysis } from '../api.js';

let mediaRecorder = null;
let audioChunks = [];
let recordedBlob = null;

export function initRecorder() {
    const btnRecord = document.getElementById('btn-record');
    const btnStop = document.getElementById('btn-stop');
    const btnAnalyze = document.getElementById('btn-analyze');
    const status = document.getElementById('recording-status');
    const preview = document.getElementById('audio-preview');

    btnRecord.addEventListener('click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = () => {
                recordedBlob = new Blob(audioChunks, { type: 'audio/webm' });
                preview.src = URL.createObjectURL(recordedBlob);
                preview.classList.remove('hidden');
                btnAnalyze.classList.remove('hidden');
                status.textContent = 'Recording complete. Review and analyze.';
                stream.getTracks().forEach(t => t.stop());
            };

            mediaRecorder.start();
            btnRecord.disabled = true;
            btnStop.disabled = false;
            status.textContent = 'Recording...';
        } catch (err) {
            status.textContent = `Microphone access denied: ${err.message}`;
        }
    });

    btnStop.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            btnRecord.disabled = false;
            btnStop.disabled = true;
        }
    });

    btnAnalyze.addEventListener('click', async () => {
        if (!recordedBlob) return;
        status.textContent = 'Uploading...';
        btnAnalyze.disabled = true;

        try {
            const { upload_url, object_key } = await getUploadUrl('recording.webm', 'audio/webm');
            await uploadAudio(upload_url, recordedBlob, 'audio/webm');
            status.textContent = 'Analyzing your presentation...';

            const { analysis_id } = await startAnalysis(object_key);

            // Dispatch event for results component to pick up
            window.dispatchEvent(new CustomEvent('analysis-started', {
                detail: { analysisId: analysis_id }
            }));
        } catch (err) {
            status.textContent = `Error: ${err.message}`;
            btnAnalyze.disabled = false;
        }
    });
}
