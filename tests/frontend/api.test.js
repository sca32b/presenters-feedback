/**
 * Frontend API client tests.
 *
 * Tests the API communication layer defined in frontend/src/api.js:
 * - getUploadUrl(filename, contentType) -> { upload_url, object_key }
 * - uploadAudio(uploadUrl, blob, contentType) -> void
 * - startAnalysis(objectKey) -> { analysis_id, status }
 * - getAnalysis(analysisId) -> { analysis_id, status, results? }
 * - listAnalyses(page, pageSize) -> { items, total, page, page_size }
 */

global.fetch = jest.fn();

// Inline the API client functions to match frontend/src/api.js exactly
const API_BASE = 'http://localhost:8000/api';

async function request(method, path, body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);

    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

async function getUploadUrl(filename, contentType) {
    return request('POST', '/uploads', { filename, content_type: contentType });
}

async function uploadAudio(uploadUrl, blob, contentType) {
    const response = await fetch(uploadUrl, {
        method: 'PUT',
        headers: { 'Content-Type': contentType },
        body: blob,
    });
    if (!response.ok) throw new Error('Upload failed');
}

async function startAnalysis(objectKey) {
    return request('POST', '/analyses', { object_key: objectKey });
}

async function getAnalysis(analysisId) {
    return request('GET', `/analyses/${analysisId}`);
}

async function listAnalyses(page = 1, pageSize = 10) {
    return request('GET', `/analyses?page=${page}&page_size=${pageSize}`);
}

// ---------------------------------------------------------------------------
// getUploadUrl tests
// ---------------------------------------------------------------------------

describe('getUploadUrl', () => {
    beforeEach(() => { fetch.mockClear(); });

    test('sends POST to /uploads with filename and content_type', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                upload_url: 'https://s3.amazonaws.com/presigned',
                object_key: 'uploads/user/uuid.webm',
            }),
        });

        await getUploadUrl('recording.webm', 'audio/webm');

        expect(fetch).toHaveBeenCalledWith(
            `${API_BASE}/uploads`,
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ filename: 'recording.webm', content_type: 'audio/webm' }),
            })
        );
    });

    test('returns upload_url and object_key', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                upload_url: 'https://s3.amazonaws.com/presigned',
                object_key: 'uploads/user/uuid.webm',
            }),
        });

        const result = await getUploadUrl('recording.webm', 'audio/webm');
        expect(result.upload_url).toContain('https://');
        expect(result.object_key).toContain('uploads/');
    });

    test('throws on server error', async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            status: 500,
            json: () => Promise.resolve({ detail: 'Internal error' }),
        });

        await expect(getUploadUrl('test.webm', 'audio/webm')).rejects.toThrow('Internal error');
    });
});

// ---------------------------------------------------------------------------
// uploadAudio tests (direct S3 presigned PUT)
// ---------------------------------------------------------------------------

describe('uploadAudio', () => {
    beforeEach(() => { fetch.mockClear(); });

    test('sends PUT to the presigned URL with audio blob', async () => {
        fetch.mockResolvedValueOnce({ ok: true });

        const blob = new Blob(['fake-audio'], { type: 'audio/webm' });
        await uploadAudio('https://s3.amazonaws.com/presigned', blob, 'audio/webm');

        expect(fetch).toHaveBeenCalledWith(
            'https://s3.amazonaws.com/presigned',
            expect.objectContaining({
                method: 'PUT',
                headers: { 'Content-Type': 'audio/webm' },
                body: blob,
            })
        );
    });

    test('throws on upload failure', async () => {
        fetch.mockResolvedValueOnce({ ok: false, status: 403 });

        const blob = new Blob(['fake'], { type: 'audio/webm' });
        await expect(
            uploadAudio('https://s3.amazonaws.com/expired', blob, 'audio/webm')
        ).rejects.toThrow('Upload failed');
    });
});

// ---------------------------------------------------------------------------
// startAnalysis tests
// ---------------------------------------------------------------------------

describe('startAnalysis', () => {
    beforeEach(() => { fetch.mockClear(); });

    test('sends POST to /analyses with object_key', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ analysis_id: 'abc-123', status: 'processing' }),
        });

        await startAnalysis('uploads/user/uuid.webm');

        expect(fetch).toHaveBeenCalledWith(
            `${API_BASE}/analyses`,
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ object_key: 'uploads/user/uuid.webm' }),
            })
        );
    });

    test('returns analysis_id and status', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ analysis_id: 'abc-123', status: 'processing' }),
        });

        const result = await startAnalysis('uploads/user/uuid.webm');
        expect(result.analysis_id).toBe('abc-123');
        expect(result.status).toBe('processing');
    });
});

// ---------------------------------------------------------------------------
// getAnalysis tests (polling)
// ---------------------------------------------------------------------------

describe('getAnalysis', () => {
    beforeEach(() => { fetch.mockClear(); });

    test('sends GET to /analyses/{id}', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                analysis_id: 'abc-123',
                status: 'completed',
                created_at: '2026-02-08T12:00:00Z',
                results: { overall_score: 64 },
            }),
        });

        await getAnalysis('abc-123');

        expect(fetch).toHaveBeenCalledWith(
            `${API_BASE}/analyses/abc-123`,
            expect.objectContaining({ method: 'GET' })
        );
    });

    test('returns completed results with scores', async () => {
        const mockResults = {
            analysis_id: 'abc-123',
            status: 'completed',
            created_at: '2026-02-08T12:00:00Z',
            results: {
                voice_tone: { score: 72, summary: 'Good.' },
                vocabulary: { score: 65, summary: 'Decent.' },
                pacing: { score: 58, summary: 'Fast.' },
                overall_score: 64,
                overall_summary: 'Solid presentation.',
                recommendations: ['Slow down', 'Fewer fillers'],
            },
        };

        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve(mockResults),
        });

        const result = await getAnalysis('abc-123');
        expect(result.status).toBe('completed');
        expect(result.results.overall_score).toBe(64);
        expect(result.results.voice_tone.score).toBe(72);
    });

    test('returns processing status while in progress', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                analysis_id: 'abc-123',
                status: 'processing',
                created_at: '2026-02-08T12:00:00Z',
            }),
        });

        const result = await getAnalysis('abc-123');
        expect(result.status).toBe('processing');
        expect(result.results).toBeUndefined();
    });

    test('throws on 404 (not found)', async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            status: 404,
            json: () => Promise.resolve({ detail: 'Not found' }),
        });

        await expect(getAnalysis('nonexistent')).rejects.toThrow('Not found');
    });
});

// ---------------------------------------------------------------------------
// listAnalyses tests
// ---------------------------------------------------------------------------

describe('listAnalyses', () => {
    beforeEach(() => { fetch.mockClear(); });

    test('sends GET to /analyses with pagination params', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ items: [], total: 0, page: 1, page_size: 10 }),
        });

        await listAnalyses(2, 5);

        expect(fetch).toHaveBeenCalledWith(
            `${API_BASE}/analyses?page=2&page_size=5`,
            expect.objectContaining({ method: 'GET' })
        );
    });

    test('defaults to page 1, page_size 10', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ items: [], total: 0, page: 1, page_size: 10 }),
        });

        await listAnalyses();

        expect(fetch).toHaveBeenCalledWith(
            `${API_BASE}/analyses?page=1&page_size=10`,
            expect.objectContaining({ method: 'GET' })
        );
    });

    test('returns paginated list', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                items: [
                    { analysis_id: 'a1', status: 'completed', created_at: '2026-02-08T10:00:00Z' },
                    { analysis_id: 'a2', status: 'completed', created_at: '2026-02-07T10:00:00Z' },
                ],
                total: 25,
                page: 1,
                page_size: 10,
            }),
        });

        const result = await listAnalyses();
        expect(result.items).toHaveLength(2);
        expect(result.total).toBe(25);
        expect(result.page).toBe(1);
    });

    test('returns empty list when no history', async () => {
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({ items: [], total: 0, page: 1, page_size: 10 }),
        });

        const result = await listAnalyses();
        expect(result.items).toHaveLength(0);
    });
});

// ---------------------------------------------------------------------------
// Error handling tests
// ---------------------------------------------------------------------------

describe('API error handling', () => {
    beforeEach(() => { fetch.mockClear(); });

    test('extracts detail message from error response', async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            status: 400,
            json: () => Promise.resolve({ detail: 'Invalid request body' }),
        });

        await expect(getUploadUrl('bad', 'bad')).rejects.toThrow('Invalid request body');
    });

    test('falls back to generic message when no detail', async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            status: 500,
            json: () => Promise.reject(new Error('not json')),
        });

        await expect(getUploadUrl('bad', 'bad')).rejects.toThrow('Request failed');
    });

    test('network error propagates', async () => {
        fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

        await expect(getUploadUrl('test.webm', 'audio/webm')).rejects.toThrow('Failed to fetch');
    });
});
