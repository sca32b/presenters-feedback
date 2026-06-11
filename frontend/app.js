/* ============================================
   Presenter Feedback - Application Logic
   ============================================ */

(function () {
    'use strict';

    // --- Configuration ---
    // In local dev, backend runs on port 8000; in production, use API Gateway
    const API_BASE = window.location.hostname === 'localhost'
        ? 'http://localhost:8000/api'
        : 'https://3whupzg7gd.execute-api.us-east-1.amazonaws.com/dev/api';

    // Cognito configuration
    const COGNITO_REGION = 'us-east-1';
    const COGNITO_USER_POOL_ID = 'us-east-1_FDjGBrWet';
    const COGNITO_CLIENT_ID = '3iq28lj6uu333jb4fvqen7j5rs';
    const COGNITO_ENDPOINT = `https://cognito-idp.${COGNITO_REGION}.amazonaws.com`;
    const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB (matches presigned URL policy)
    const ACCEPTED_TYPES = ['audio/wav', 'audio/mpeg', 'audio/mp4', 'audio/x-m4a', 'audio/webm', 'audio/ogg'];
    const ACCEPTED_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.webm', '.ogg'];
    const VISUALIZER_BARS = 24;
    const HISTORY_KEY = 'presenter-feedback-history';
    const MAX_SCORE = 100; // Architecture uses 1-100 scale

    // --- State ---
    let mediaRecorder = null;
    let audioChunks = [];
    let audioStream = null;
    let analyserNode = null;
    let audioContext = null;
    let timerInterval = null;
    let animationFrameId = null;
    let recordingState = 'idle'; // idle | recording | paused | stopped
    let currentAudioBlob = null;
    let selectedFile = null;
    let authToken = null; // JWT token from Cognito
    let processingRefreshTimers = []; // timers for auto-refreshing processing items

    // --- DOM Elements ---
    const $ = (id) => document.getElementById(id);
    const els = {
        recordBtn: $('recordBtn'),
        pauseBtn: $('pauseBtn'),
        stopBtn: $('stopBtn'),
        timer: $('timer'),
        visualizer: $('visualizer'),
        visualizerContainer: $('visualizerContainer'),
        uploadZone: $('uploadZone'),
        fileInput: $('fileInput'),
        fileInfo: $('fileInfo'),
        fileName: $('fileName'),
        fileSize: $('fileSize'),
        clearFileBtn: $('clearFileBtn'),
        analyzeBtn: $('analyzeBtn'),
        discardBtn: $('discardBtn'),
        recordingSection: $('recordingSection'),
        loadingSection: $('loadingSection'),
        loadingTitle: $('loadingTitle'),
        loadingStep: $('loadingStep'),
        progressFill: $('progressFill'),
        feedbackSection: $('feedbackSection'),
        newRecordingBtn: $('newRecordingBtn'),
        scoreRingFill: $('scoreRingFill'),
        scoreNumber: $('scoreNumber'),
        scoreSummary: $('scoreSummary'),
        voiceScoreBar: $('voiceScoreBar'),
        voiceScoreText: $('voiceScoreText'),
        voiceSummary: $('voiceSummary'),
        voiceDetail: $('voiceDetail'),
        vocabScoreBar: $('vocabScoreBar'),
        vocabScoreText: $('vocabScoreText'),
        vocabSummary: $('vocabSummary'),
        vocabDetail: $('vocabDetail'),
        speedScoreBar: $('speedScoreBar'),
        speedScoreText: $('speedScoreText'),
        speedSummary: $('speedSummary'),
        speedDetail: $('speedDetail'),
        readinessScoreBar: $('readinessScoreBar'),
        readinessScoreText: $('readinessScoreText'),
        readinessSummary: $('readinessSummary'),
        readinessDetail: $('readinessDetail'),
        suggestionsList: $('suggestionsList'),
        suggestionsSection: $('suggestionsSection'),
        executivePresenceSection: $('executivePresenceSection'),
        executivePresenceList: $('executivePresenceList'),
        historyBtn: $('historyBtn'),
        historyPanel: $('historyPanel'),
        historyOverlay: $('historyOverlay'),
        closeHistoryBtn: $('closeHistoryBtn'),
        historyList: $('historyList'),
        historyEmpty: $('historyEmpty'),
        recordingHistorySection: $('recordingHistorySection'),
        recordingHistoryList: $('recordingHistoryList'),
        recordingHistoryEmpty: $('recordingHistoryEmpty'),
        micModal: $('micModal'),
        closeMicModal: $('closeMicModal'),
        toastContainer: $('toastContainer'),
    };

    // --- Auth / Login ---
    function checkAuth() {
        // Skip auth on localhost
        if (window.location.hostname === 'localhost') {
            showApp();
            return;
        }
        const token = sessionStorage.getItem('pf_id_token');
        const expiry = sessionStorage.getItem('pf_token_expiry');
        if (token && expiry && Date.now() < parseInt(expiry)) {
            authToken = token;
            showApp();
        } else {
            showLogin();
        }
    }

    function showLogin() {
        document.getElementById('loginScreen').classList.remove('hidden');
        document.getElementById('app').classList.add('hidden');
        document.getElementById('loginForm').addEventListener('submit', handleLogin);
    }

    function showApp() {
        document.getElementById('loginScreen').classList.add('hidden');
        document.getElementById('app').classList.remove('hidden');
        init();
    }

    async function handleLogin(e) {
        e.preventDefault();
        const email = document.getElementById('loginEmail').value.trim();
        const password = document.getElementById('loginPassword').value;
        const errorEl = document.getElementById('loginError');
        const btn = document.getElementById('loginBtn');
        const btnText = document.getElementById('loginBtnText');
        const spinner = document.getElementById('loginSpinner');

        errorEl.classList.add('hidden');
        btn.disabled = true;
        btnText.textContent = '';
        spinner.classList.remove('hidden');

        try {
            const result = await cognitoAuth(email, password);
            authToken = result.IdToken;
            sessionStorage.setItem('pf_id_token', result.IdToken);
            sessionStorage.setItem('pf_access_token', result.AccessToken);
            // Tokens are valid for 8 hours
            sessionStorage.setItem('pf_token_expiry', String(Date.now() + 8 * 60 * 60 * 1000));
            showApp();
        } catch (err) {
            errorEl.textContent = err.message || 'Authentication failed.';
            errorEl.classList.remove('hidden');
        } finally {
            btn.disabled = false;
            btnText.textContent = 'Enter';
            spinner.classList.add('hidden');
        }
    }

    async function cognitoAuth(email, password) {
        const response = await fetch(COGNITO_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-amz-json-1.1',
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
            },
            body: JSON.stringify({
                AuthFlow: 'USER_PASSWORD_AUTH',
                ClientId: COGNITO_CLIENT_ID,
                AuthParameters: {
                    USERNAME: email,
                    PASSWORD: password,
                },
            }),
        });

        const data = await response.json();

        if (data.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
            throw new Error('Password reset required. Contact admin.');
        }

        if (data.__type && data.__type.includes('NotAuthorizedException')) {
            throw new Error('Invalid email or password.');
        }

        if (data.__type && data.__type.includes('UserNotFoundException')) {
            throw new Error('Invalid email or password.');
        }

        if (data.__type) {
            throw new Error(data.message || 'Authentication failed.');
        }

        if (!data.AuthenticationResult) {
            throw new Error('Unexpected response from auth service.');
        }

        return data.AuthenticationResult;
    }

    // --- Initialize ---
    function init() {
        createVisualizerBars();
        bindEvents();
        loadHistory();
        fetchRecordingHistory();
    }

    function createVisualizerBars() {
        els.visualizer.innerHTML = '';
        for (let i = 0; i < VISUALIZER_BARS; i++) {
            const bar = document.createElement('div');
            bar.className = 'bar';
            bar.style.height = '4px';
            els.visualizer.appendChild(bar);
        }
    }

    // --- Event Binding ---
    function bindEvents() {
        els.recordBtn.addEventListener('click', handleRecord);
        els.pauseBtn.addEventListener('click', handlePause);
        els.stopBtn.addEventListener('click', handleStop);
        els.uploadZone.addEventListener('click', () => els.fileInput.click());
        els.uploadZone.addEventListener('dragover', handleDragOver);
        els.uploadZone.addEventListener('dragleave', handleDragLeave);
        els.uploadZone.addEventListener('drop', handleDrop);
        els.fileInput.addEventListener('change', handleFileSelect);
        els.clearFileBtn.addEventListener('click', clearFile);
        els.analyzeBtn.addEventListener('click', handleAnalyze);
        els.discardBtn.addEventListener('click', handleDiscard);
        els.newRecordingBtn.addEventListener('click', resetToRecording);
        els.historyBtn.addEventListener('click', openHistory);
        els.historyOverlay.addEventListener('click', closeHistory);
        els.closeHistoryBtn.addEventListener('click', closeHistory);
        els.closeMicModal.addEventListener('click', () => els.micModal.classList.add('hidden'));

        // Logout
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                sessionStorage.removeItem('pf_id_token');
                sessionStorage.removeItem('pf_access_token');
                sessionStorage.removeItem('pf_token_expiry');
                authToken = null;
                window.location.reload();
            });
        }

        // Expand/collapse category details
        document.querySelectorAll('.expand-btn').forEach(btn => {
            btn.addEventListener('click', function () {
                const card = this.closest('.category-card');
                const detail = card.querySelector('.category-detail');
                this.classList.toggle('expanded');
                detail.classList.toggle('hidden');
            });
        });
    }

    // --- Auth Helper ---
    function getAuthHeaders() {
        const headers = {};
        // Always use ID Token (has 'aud' claim matching the Cognito client ID)
        const token = authToken || sessionStorage.getItem('pf_id_token');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    }

    // --- Recording ---
    async function handleRecord() {
        if (recordingState === 'idle' || recordingState === 'stopped') {
            await startRecording();
        }
    }

    async function startRecording() {
        try {
            audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                els.micModal.classList.remove('hidden');
            } else {
                showToast('Could not access microphone. Please check your device settings.', 'error');
            }
            return;
        }

        // Clear any previously selected file
        clearFile();

        // Set up audio analysis for visualizer
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(audioStream);
        analyserNode = audioContext.createAnalyser();
        analyserNode.fftSize = 64;
        source.connect(analyserNode);

        // Set up MediaRecorder
        const mimeType = getSupportedMimeType();
        const options = mimeType ? { mimeType } : {};
        mediaRecorder = new MediaRecorder(audioStream, options);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                audioChunks.push(e.data);
            }
        };

        mediaRecorder.onstop = () => {
            const mimeUsed = mediaRecorder.mimeType || 'audio/webm';
            currentAudioBlob = new Blob(audioChunks, { type: mimeUsed });
            showAnalyzeButton();
        };

        mediaRecorder.start(100);
        recordingState = 'recording';

        updateUI();
        startTimer();
        startVisualizer();
    }

    function handlePause() {
        if (recordingState === 'recording' && mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.pause();
            recordingState = 'paused';
            stopTimer();
            updateUI();
        } else if (recordingState === 'paused' && mediaRecorder && mediaRecorder.state === 'paused') {
            mediaRecorder.resume();
            recordingState = 'recording';
            startTimer();
            updateUI();
        }
    }

    function handleStop() {
        if (mediaRecorder && (mediaRecorder.state === 'recording' || mediaRecorder.state === 'paused')) {
            mediaRecorder.stop();
        }
        stopRecordingResources();
        recordingState = 'stopped';
        stopTimer();
        stopVisualizer();
        updateUI();
    }

    // --- Discard Recording ---
    function handleDiscard() {
        recordingState = 'idle';
        currentAudioBlob = null;
        selectedFile = null;
        audioChunks = [];

        resetTimer();
        stopVisualizer();
        els.analyzeBtn.classList.add('hidden');
        els.analyzeBtn.disabled = true;
        els.discardBtn.classList.add('hidden');
        els.fileInput.value = '';
        els.fileInfo.classList.add('hidden');
        els.uploadZone.classList.remove('hidden');

        updateUI();
    }

    function stopRecordingResources() {
        if (audioStream) {
            audioStream.getTracks().forEach(t => t.stop());
            audioStream = null;
        }
        if (audioContext) {
            audioContext.close().catch(() => {});
            audioContext = null;
            analyserNode = null;
        }
    }

    function getSupportedMimeType() {
        const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) return type;
        }
        return '';
    }

    // --- Timer ---
    let elapsedMs = 0;
    let timerStartMs = 0;

    function startTimer() {
        timerStartMs = Date.now() - elapsedMs;
        timerInterval = setInterval(() => {
            elapsedMs = Date.now() - timerStartMs;
            els.timer.textContent = formatTime(elapsedMs);
        }, 200);
    }

    function stopTimer() {
        clearInterval(timerInterval);
        timerInterval = null;
    }

    function resetTimer() {
        elapsedMs = 0;
        els.timer.textContent = '00:00';
    }

    function formatTime(ms) {
        const totalSec = Math.floor(ms / 1000);
        const min = String(Math.floor(totalSec / 60)).padStart(2, '0');
        const sec = String(totalSec % 60).padStart(2, '0');
        return `${min}:${sec}`;
    }

    // --- Visualizer ---
    function startVisualizer() {
        els.visualizer.classList.add('active');
        updateVisualizer();
    }

    function stopVisualizer() {
        els.visualizer.classList.remove('active');
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        const bars = els.visualizer.querySelectorAll('.bar');
        bars.forEach(bar => {
            bar.style.height = '4px';
            bar.className = 'bar';
        });
    }

    function updateVisualizer() {
        if (!analyserNode || recordingState !== 'recording') {
            if (recordingState === 'paused') {
                animationFrameId = requestAnimationFrame(updateVisualizer);
            }
            return;
        }

        const data = new Uint8Array(analyserNode.frequencyBinCount);
        analyserNode.getByteFrequencyData(data);

        const bars = els.visualizer.querySelectorAll('.bar');
        const barCount = bars.length;
        const step = Math.floor(data.length / barCount);

        for (let i = 0; i < barCount; i++) {
            const value = data[i * step] || 0;
            const percent = value / 255;
            const height = Math.max(4, percent * 56);
            bars[i].style.height = height + 'px';

            bars[i].classList.remove('high', 'peak');
            if (percent > 0.85) {
                bars[i].classList.add('peak');
            } else if (percent > 0.6) {
                bars[i].classList.add('high');
            }
        }

        animationFrameId = requestAnimationFrame(updateVisualizer);
    }

    // --- File Upload ---
    function handleDragOver(e) {
        e.preventDefault();
        els.uploadZone.classList.add('dragover');
    }

    function handleDragLeave(e) {
        e.preventDefault();
        els.uploadZone.classList.remove('dragover');
    }

    function handleDrop(e) {
        e.preventDefault();
        els.uploadZone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) processFile(file);
    }

    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) processFile(file);
    }

    function processFile(file) {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (!ACCEPTED_EXTENSIONS.includes(ext) && !ACCEPTED_TYPES.includes(file.type)) {
            showToast('Unsupported file format. Please use WAV, MP3, M4A, WebM, or OGG.', 'error');
            return;
        }

        if (file.size > MAX_FILE_SIZE) {
            showToast('File is too large. Maximum size is 50 MB.', 'error');
            return;
        }

        selectedFile = file;
        currentAudioBlob = null;

        els.fileName.textContent = file.name;
        els.fileSize.textContent = formatFileSize(file.size);
        els.fileInfo.classList.remove('hidden');
        els.uploadZone.classList.add('hidden');

        showAnalyzeButton();
    }

    function clearFile() {
        selectedFile = null;
        els.fileInput.value = '';
        els.fileInfo.classList.add('hidden');
        els.uploadZone.classList.remove('hidden');

        if (!currentAudioBlob) {
            els.analyzeBtn.classList.add('hidden');
            els.discardBtn.classList.add('hidden');
        }
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function showAnalyzeButton() {
        els.analyzeBtn.classList.remove('hidden');
        els.analyzeBtn.disabled = false;
        els.discardBtn.classList.remove('hidden');
    }

    // --- UI State Updates ---
    function updateUI() {
        const isIdle = recordingState === 'idle' || recordingState === 'stopped';
        const isRecording = recordingState === 'recording';
        const isPaused = recordingState === 'paused';

        els.recordBtn.classList.toggle('recording', isRecording);

        if (isIdle) {
            els.pauseBtn.classList.add('hidden');
            els.stopBtn.classList.add('hidden');
            els.recordBtn.classList.remove('recording');
        } else {
            els.pauseBtn.classList.remove('hidden');
            els.stopBtn.classList.remove('hidden');
        }

        els.pauseBtn.classList.toggle('active', isPaused);
        els.pauseBtn.querySelector('span').textContent = isPaused ? 'Resume' : 'Pause';
        els.timer.classList.toggle('recording', isRecording);

        if (isRecording || isPaused) {
            els.uploadZone.classList.add('hidden');
            els.fileInfo.classList.add('hidden');
            els.analyzeBtn.classList.add('hidden');
            els.discardBtn.classList.add('hidden');
        } else if (!selectedFile) {
            els.uploadZone.classList.remove('hidden');
        }
    }

    // --- Analysis (aligned with architecture API) ---
    async function handleAnalyze() {
        const audioData = selectedFile || currentAudioBlob;
        if (!audioData) {
            showToast('No audio to analyze. Please record or upload audio first.', 'error');
            return;
        }

        showLoading();

        try {
            const feedback = await submitAudio(audioData);
            saveToHistory(feedback);
            showFeedback(feedback);
            fetchRecordingHistory();
        } catch (err) {
            showRecordingSection();
            showToast(err.message || 'Analysis failed. Please try again.', 'error');
        }
    }

    async function submitAudio(audioData) {
        // Determine filename and content type
        const filename = selectedFile
            ? selectedFile.name
            : 'recording-' + new Date().toISOString().slice(0, 19).replace(/[:.]/g, '-') + '.webm';
        const contentType = selectedFile
            ? selectedFile.type || 'audio/webm'
            : currentAudioBlob?.type || 'audio/webm';

        // Step 1: Get presigned upload URL from backend
        updateLoadingStep('Preparing upload...', 5);

        let uploadInfo;
        try {
            const response = await fetch(`${API_BASE}/uploads`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders(),
                },
                body: JSON.stringify({ filename, content_type: contentType }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => null);
                throw new Error(errData?.detail || `Upload preparation failed (${response.status}).`);
            }

            uploadInfo = await response.json();
        } catch (err) {
            if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
                throw new Error('Network error. Please check your connection and try again.');
            }
            throw err;
        }

        // Step 2: Upload audio directly to S3 via presigned URL
        updateLoadingStep('Uploading audio...', 15);

        try {
            const uploadResponse = await fetch(uploadInfo.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': contentType },
                body: audioData,
            });

            if (!uploadResponse.ok) {
                throw new Error('Audio upload failed. Please try again.');
            }
        } catch (err) {
            if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
                throw new Error('Network error during upload. Please try again.');
            }
            throw err;
        }

        // Step 3: Start analysis
        updateLoadingStep('Starting analysis...', 25);

        let analysisInfo;
        try {
            const response = await fetch(`${API_BASE}/analyses`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders(),
                },
                body: JSON.stringify({ object_key: uploadInfo.object_key }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => null);
                throw new Error(errData?.detail || `Failed to start analysis (${response.status}).`);
            }

            analysisInfo = await response.json();
        } catch (err) {
            if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
                throw new Error('Network error. Please try again.');
            }
            throw err;
        }

        // Step 4: Poll for results
        return await pollForResults(analysisInfo.analysis_id);
    }

    async function pollForResults(analysisId) {
        const steps = [
            { msg: 'Transcribing speech...', pct: 35 },
            { msg: 'Analyzing presentation...', pct: 55 },
            { msg: 'Generating feedback...', pct: 75 },
            { msg: 'Finalizing results...', pct: 90 },
        ];
        let stepIndex = 0;
        const maxAttempts = 60;
        const pollInterval = 3000;

        for (let attempt = 0; attempt < maxAttempts; attempt++) {
            await sleep(pollInterval);

            if (stepIndex < steps.length) {
                updateLoadingStep(steps[stepIndex].msg, steps[stepIndex].pct);
                stepIndex++;
            }

            let response;
            try {
                response = await fetch(`${API_BASE}/analyses/${analysisId}`, {
                    headers: getAuthHeaders(),
                });
            } catch {
                continue; // Retry on network error
            }

            if (response.status === 202) continue; // Still processing

            if (!response.ok) {
                throw new Error('Analysis failed on the server. Please try again.');
            }

            const data = await response.json();

            if (data.status === 'completed' && data.results) {
                updateLoadingStep('Complete!', 100);
                await sleep(500); // Brief pause so user sees 100%
                return data;
            }

            if (data.status === 'failed') {
                throw new Error('Analysis failed. The audio may be too short or unclear. Please try again.');
            }
        }

        throw new Error('Analysis is taking too long. Please try again later.');
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // --- Loading UI ---
    function showLoading() {
        els.recordingSection.classList.add('hidden');
        els.feedbackSection.classList.add('hidden');
        els.loadingSection.classList.remove('hidden');
        els.progressFill.classList.add('indeterminate');
        els.progressFill.style.width = '0%';
        els.loadingStep.textContent = 'Preparing...';
    }

    function updateLoadingStep(text, percent) {
        els.loadingStep.textContent = text;
        if (percent !== undefined) {
            els.progressFill.classList.remove('indeterminate');
            els.progressFill.style.width = percent + '%';
        }
    }

    function showRecordingSection() {
        els.loadingSection.classList.add('hidden');
        els.feedbackSection.classList.add('hidden');
        els.recordingSection.classList.remove('hidden');
    }

    // --- Feedback Display ---
    function showFeedback(data) {
        els.loadingSection.classList.add('hidden');
        els.recordingSection.classList.add('hidden');
        els.feedbackSection.classList.remove('hidden');

        const feedback = normalizeFeedback(data);

        // Overall score animation (scores are 0-100)
        animateScore(feedback.overall_score);

        els.scoreSummary.textContent = feedback.overall_summary || '';

        // Category scores
        setCategory('voice', feedback.voice_tone);
        setCategory('vocab', feedback.vocabulary);
        setCategory('speed', feedback.pacing);
        setCategory('readiness', feedback.readiness);

        // Executive Presence Tips
        displayExecutivePresenceTips(feedback.executive_presence);

        // Suggestions / Recommendations
        els.suggestionsList.innerHTML = '';
        if (feedback.recommendations && feedback.recommendations.length > 0) {
            els.suggestionsSection.classList.remove('hidden');
            feedback.recommendations.forEach(s => {
                const li = document.createElement('li');
                li.textContent = s;
                els.suggestionsList.appendChild(li);
            });
        } else {
            els.suggestionsSection.classList.add('hidden');
        }

        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function normalizeFeedback(data) {
        // The architecture returns: { analysis_id, status, created_at, results: { ... } }
        // Support both nested (results.voice_tone) and flat structures
        const r = data.results || data;

        return {
            analysis_id: data.analysis_id,
            overall_score: r.overall_score ?? 0,
            overall_summary: r.overall_summary ?? '',
            voice_tone: {
                score: r.voice_tone?.score ?? 0,
                summary: r.voice_tone?.summary ?? '',
                detail: buildVoiceDetail(r.voice_tone),
            },
            vocabulary: {
                score: r.vocabulary?.score ?? 0,
                summary: r.vocabulary?.summary ?? '',
                detail: buildVocabDetail(r.vocabulary),
            },
            pacing: {
                score: r.pacing?.score ?? 0,
                summary: r.pacing?.summary ?? '',
                detail: buildPacingDetail(r.pacing),
            },
            readiness: {
                score: r.overall_score ?? 0,
                summary: r.overall_summary ?? '',
                detail: '',
            },
            executive_presence: r.executive_presence ?? null,
            recommendations: r.recommendations ?? [],
        };
    }

    // --- Executive Presence Tips ---
    function displayExecutivePresenceTips(execPresence) {
        els.executivePresenceList.innerHTML = '';

        if (!execPresence || !execPresence.tips || execPresence.tips.length === 0) {
            els.executivePresenceSection.classList.add('hidden');
            return;
        }

        els.executivePresenceSection.classList.remove('hidden');
        execPresence.tips.forEach(tip => {
            const li = document.createElement('li');
            li.textContent = tip;
            els.executivePresenceList.appendChild(li);
        });
    }

    function buildVoiceDetail(voice) {
        if (!voice) return '';
        const parts = [];
        if (voice.summary) parts.push(voice.summary);
        if (voice.confidence_level) parts.push('Confidence: ' + voice.confidence_level);
        if (voice.warmth) parts.push('Warmth: ' + voice.warmth);
        if (voice.monotone_detected !== undefined) {
            parts.push(voice.monotone_detected ? 'Monotone tendencies detected.' : 'Good vocal variety.');
        }
        return parts.join(' ');
    }

    function buildVocabDetail(vocab) {
        if (!vocab) return '';
        const parts = [];
        if (vocab.summary) parts.push(vocab.summary);
        if (vocab.filler_word_count !== undefined) parts.push('Filler words: ' + vocab.filler_word_count);
        if (vocab.unique_word_ratio !== undefined) parts.push('Unique word ratio: ' + (vocab.unique_word_ratio * 100).toFixed(0) + '%');
        if (vocab.readability_level) parts.push('Readability: ' + vocab.readability_level);
        return parts.join(' ');
    }

    function buildPacingDetail(pacing) {
        if (!pacing) return '';
        const parts = [];
        if (pacing.summary) parts.push(pacing.summary);
        if (pacing.words_per_minute) parts.push(pacing.words_per_minute + ' words per minute.');
        if (pacing.variation) parts.push('Variation: ' + pacing.variation);
        if (pacing.pause_usage) parts.push('Pause usage: ' + pacing.pause_usage);
        return parts.join(' ');
    }

    function animateScore(score) {
        // score is 0-100; ring shows proportion
        const circumference = 2 * Math.PI * 52; // r=52
        const offset = circumference - (score / MAX_SCORE) * circumference;

        els.scoreRingFill.classList.remove('medium', 'low');
        if (score <= 40) {
            els.scoreRingFill.classList.add('low');
        } else if (score <= 65) {
            els.scoreRingFill.classList.add('medium');
        }

        setTimeout(() => {
            els.scoreRingFill.style.strokeDashoffset = offset;
        }, 100);

        animateNumber(els.scoreNumber, 0, score, 1200);
    }

    function animateNumber(el, from, to, duration) {
        const start = performance.now();

        function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = from + (to - from) * eased;

            el.textContent = Math.round(current);

            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }

        requestAnimationFrame(update);
    }

    function setCategory(prefix, data) {
        const scoreBar = els[prefix + 'ScoreBar'];
        const scoreText = els[prefix + 'ScoreText'];
        const summary = els[prefix + 'Summary'];
        const detail = els[prefix + 'Detail'];

        const score = data?.score ?? 0;

        // Score bars fill based on 0-100 scale
        setTimeout(() => {
            scoreBar.style.width = score + '%';
        }, 200);
        scoreText.textContent = score;
        summary.textContent = data?.summary ?? '';
        detail.textContent = data?.detail ?? '';

        const card = detail.closest('.category-card');
        const expandBtn = card.querySelector('.expand-btn');
        if (!data?.detail) {
            expandBtn.style.display = 'none';
        } else {
            expandBtn.style.display = '';
            expandBtn.classList.remove('expanded');
            detail.classList.add('hidden');
        }
    }

    // --- Reset ---
    function resetToRecording() {
        recordingState = 'idle';
        currentAudioBlob = null;
        selectedFile = null;
        audioChunks = [];

        resetTimer();
        stopVisualizer();
        els.analyzeBtn.classList.add('hidden');
        els.analyzeBtn.disabled = true;
        els.discardBtn.classList.add('hidden');
        els.fileInput.value = '';
        els.fileInfo.classList.add('hidden');
        els.uploadZone.classList.remove('hidden');

        // Reset score ring
        els.scoreRingFill.style.strokeDashoffset = 326.73;
        els.scoreNumber.textContent = '0';

        updateUI();
        showRecordingSection();
    }

    // --- Local History (sidebar panel) ---
    function saveToHistory(feedback) {
        const history = getHistory();
        const r = feedback.results || feedback;
        const entry = {
            id: feedback.analysis_id || Date.now().toString(),
            date: feedback.created_at || new Date().toISOString(),
            overall_score: r.overall_score ?? 0,
            summary: r.overall_summary ?? '',
            data: feedback,
        };
        history.unshift(entry);
        if (history.length > 50) history.length = 50;
        localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    }

    function getHistory() {
        try {
            return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
        } catch {
            return [];
        }
    }

    function loadHistory() {
        renderHistory();
    }

    function renderHistory() {
        const history = getHistory();
        els.historyList.innerHTML = '';

        if (history.length === 0) {
            els.historyList.innerHTML = '<div class="history-empty"><p>No analyses yet. Record or upload audio to get started.</p></div>';
            return;
        }

        history.forEach(entry => {
            const item = document.createElement('div');
            item.className = 'history-item';
            item.setAttribute('role', 'button');
            item.setAttribute('tabindex', '0');

            const score = entry.overall_score ?? 0;
            // Thresholds for 0-100 scale
            const scoreClass = score > 70 ? 'high' : score > 50 ? 'medium' : 'low';
            const date = new Date(entry.date);
            const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
            const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

            item.innerHTML = `
                <div class="history-item-score ${scoreClass}">${score}</div>
                <div class="history-item-info">
                    <div class="history-item-date">${dateStr} at ${timeStr}</div>
                    <div class="history-item-summary">${escapeHtml(entry.summary || 'No summary')}</div>
                </div>
                <div class="history-item-arrow">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                        <polyline points="9 18 15 12 9 6"/>
                    </svg>
                </div>
            `;

            item.addEventListener('click', () => {
                closeHistory();
                showFeedback(entry.data);
            });
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    closeHistory();
                    showFeedback(entry.data);
                }
            });

            els.historyList.appendChild(item);
        });
    }

    function openHistory() {
        renderHistory();
        els.historyPanel.classList.remove('hidden');
        els.historyOverlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    function closeHistory() {
        els.historyPanel.classList.add('hidden');
        els.historyOverlay.classList.add('hidden');
        document.body.style.overflow = '';
    }

    // --- Recording History (server-side, inline section) ---
    function clearProcessingTimers() {
        processingRefreshTimers.forEach(t => clearTimeout(t));
        processingRefreshTimers = [];
    }

    async function fetchRecordingHistory() {
        clearProcessingTimers();
        try {
            const response = await fetch(`${API_BASE}/analyses?page=1&page_size=20`, {
                headers: getAuthHeaders(),
            });

            if (!response.ok) {
                els.recordingHistorySection.classList.add('hidden');
                return;
            }

            const data = await response.json();
            renderRecordingHistory(data.items || []);
        } catch {
            // Silently fail - the section just won't show
            els.recordingHistorySection.classList.add('hidden');
        }
    }

    function renderRecordingHistory(items) {
        els.recordingHistoryList.innerHTML = '';

        if (!items || items.length === 0) {
            els.recordingHistorySection.classList.add('hidden');
            return;
        }

        els.recordingHistorySection.classList.remove('hidden');
        let hasProcessing = false;

        items.forEach(item => {
            const card = document.createElement('div');
            card.className = 'rh-card';
            card.setAttribute('data-analysis-id', item.analysis_id);

            const score = item.results?.overall_score ?? 0;
            const status = item.status || 'processing';
            const date = new Date(item.created_at);
            const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
            const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

            // Score color class: green >=70, yellow 40-69, red <40
            const scoreColorClass = status !== 'completed' ? '' : (score >= 70 ? 'rh-score-green' : score >= 40 ? 'rh-score-yellow' : 'rh-score-red');

            // Status badge
            const statusBadgeClass = status === 'completed' ? 'rh-badge-completed' : status === 'failed' ? 'rh-badge-failed' : 'rh-badge-processing';

            if (status === 'processing') {
                hasProcessing = true;
            }

            const summaryText = item.results?.overall_summary || '';

            card.innerHTML = `
                <div class="rh-card-top">
                    <div class="rh-card-left">
                        <div class="rh-date">${dateStr} at ${timeStr}</div>
                        <span class="rh-badge ${statusBadgeClass}">${status === 'processing' ? '<span class="rh-spinner"></span> ' : ''}${escapeHtml(status)}</span>
                    </div>
                    <div class="rh-card-right">
                        ${status === 'completed' ? `<div class="rh-score ${scoreColorClass}">${score}</div>` : ''}
                        <div class="rh-card-actions">
                            ${status === 'completed' ? `<button class="btn btn-ghost btn-sm rh-view-btn" data-id="${item.analysis_id}" aria-label="View analysis">View</button>` : ''}
                            <button class="btn btn-ghost btn-sm rh-delete-btn" data-id="${item.analysis_id}" aria-label="Delete analysis">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                                    <polyline points="3 6 5 6 21 6"/>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>
                ${status === 'completed' && summaryText ? `<div class="rh-card-summary hidden" data-expand-id="${item.analysis_id}">${escapeHtml(summaryText)}</div>` : ''}
                ${status === 'completed' && item.results ? `<div class="rh-card-details hidden" data-details-id="${item.analysis_id}"></div>` : ''}
            `;

            // Bind view button
            const viewBtn = card.querySelector('.rh-view-btn');
            if (viewBtn) {
                viewBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const detailsEl = card.querySelector(`[data-details-id="${item.analysis_id}"]`);
                    const summaryEl = card.querySelector(`[data-expand-id="${item.analysis_id}"]`);
                    if (detailsEl && detailsEl.classList.contains('hidden')) {
                        // Show expanded view
                        if (summaryEl) summaryEl.classList.remove('hidden');
                        renderInlineAnalysis(detailsEl, item);
                        detailsEl.classList.remove('hidden');
                        viewBtn.textContent = 'Hide';
                    } else if (detailsEl) {
                        if (summaryEl) summaryEl.classList.add('hidden');
                        detailsEl.classList.add('hidden');
                        viewBtn.textContent = 'View';
                    }
                });
            }

            // Bind delete button
            const deleteBtn = card.querySelector('.rh-delete-btn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    handleDeleteAnalysis(item.analysis_id, card);
                });
            }

            els.recordingHistoryList.appendChild(card);
        });

        // Auto-refresh if any items are still processing
        if (hasProcessing) {
            const timer = setTimeout(() => fetchRecordingHistory(), 5000);
            processingRefreshTimers.push(timer);
        }
    }

    function renderInlineAnalysis(container, item) {
        if (!item.results) {
            container.innerHTML = '<p class="rh-no-results">No results available.</p>';
            return;
        }

        const r = item.results;
        const tips = r.executive_presence?.tips || [];

        let html = `
            <div class="rh-inline-results">
                <div class="rh-inline-categories">
                    <div class="rh-inline-cat">
                        <span class="rh-inline-cat-label">Voice & Tone</span>
                        <span class="rh-inline-cat-score">${r.voice_tone?.score ?? '--'}</span>
                    </div>
                    <div class="rh-inline-cat">
                        <span class="rh-inline-cat-label">Vocabulary</span>
                        <span class="rh-inline-cat-score">${r.vocabulary?.score ?? '--'}</span>
                    </div>
                    <div class="rh-inline-cat">
                        <span class="rh-inline-cat-label">Pacing</span>
                        <span class="rh-inline-cat-score">${r.pacing?.score ?? '--'}</span>
                    </div>
                </div>
        `;

        if (r.recommendations && r.recommendations.length > 0) {
            html += `<div class="rh-inline-recs"><strong>Recommendations:</strong><ul>`;
            r.recommendations.forEach(rec => {
                html += `<li>${escapeHtml(rec)}</li>`;
            });
            html += `</ul></div>`;
        }

        if (tips.length > 0) {
            html += `<div class="rh-inline-exec-tips">
                <div class="executive-presence-header">
                    <span class="executive-presence-icon">&#128188;</span>
                    <strong>Executive Presence Tips</strong>
                </div>
                <ul class="executive-presence-list">`;
            tips.forEach(tip => {
                html += `<li>${escapeHtml(tip)}</li>`;
            });
            html += `</ul></div>`;
        }

        html += `</div>`;
        container.innerHTML = html;
    }

    async function handleDeleteAnalysis(analysisId, cardElement) {
        if (!confirm('Are you sure you want to delete this recording and its analysis?')) {
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/analyses/${analysisId}`, {
                method: 'DELETE',
                headers: getAuthHeaders(),
            });

            if (!response.ok && response.status !== 204) {
                throw new Error('Failed to delete analysis.');
            }

            // Remove from DOM
            cardElement.remove();

            // Remove from local history too if present
            const history = getHistory();
            const filtered = history.filter(h => h.id !== analysisId);
            localStorage.setItem(HISTORY_KEY, JSON.stringify(filtered));
            renderHistory();

            // If no more cards, hide the section
            if (els.recordingHistoryList.children.length === 0) {
                els.recordingHistorySection.classList.add('hidden');
            }

            showToast('Analysis deleted.', 'success');
        } catch (err) {
            showToast(err.message || 'Failed to delete analysis.', 'error');
        }
    }

    // --- Toast Notifications ---
    function showToast(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast ${type || ''}`;
        toast.textContent = message;
        els.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'toastOut 0.3s ease forwards';
            toast.addEventListener('animationend', () => toast.remove());
        }, 4000);
    }

    // --- Utilities ---
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // --- Start ---
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkAuth);
    } else {
        checkAuth();
    }

})();
