/**
 * API client for communicating with the backend.
 */

const API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8000/api'
    : '/api';

async function request(method, path, body = null) {
    const headers = { 'Content-Type': 'application/json' };

    // TODO: Add auth token header when Cognito is integrated
    // const token = getAuthToken();
    // if (token) headers['Authorization'] = `Bearer ${token}`;

    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);

    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

export async function getUploadUrl(filename, contentType) {
    return request('POST', '/uploads', { filename, content_type: contentType });
}

export async function uploadAudio(uploadUrl, blob, contentType) {
    const response = await fetch(uploadUrl, {
        method: 'PUT',
        headers: { 'Content-Type': contentType },
        body: blob,
    });
    if (!response.ok) throw new Error('Upload failed');
}

export async function startAnalysis(objectKey) {
    return request('POST', '/analyses', { object_key: objectKey });
}

export async function getAnalysis(analysisId) {
    return request('GET', `/analyses/${analysisId}`);
}

export async function listAnalyses(page = 1, pageSize = 10) {
    return request('GET', `/analyses?page=${page}&page_size=${pageSize}`);
}
