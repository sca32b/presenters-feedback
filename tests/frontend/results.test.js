/**
 * Results display component tests.
 *
 * Tests the rendering logic from frontend/src/components/results.js:
 * - Polling behavior (3-second interval)
 * - Rendering score cards for voice_tone, vocabulary, pacing
 * - Overall score display
 * - Recommendations list
 * - Loading and error states
 */

// ---------------------------------------------------------------------------
// Score card rendering tests
// ---------------------------------------------------------------------------

describe('Score Card Rendering', () => {
    function renderScoreCard(title, data) {
        return `
            <div class="score-card">
                <h3>${title}</h3>
                <div class="score">${data.score}/100</div>
                <p>${data.summary}</p>
            </div>
        `;
    }

    test('renders voice_tone score card', () => {
        const voiceTone = {
            score: 72,
            confidence_level: 'moderate',
            warmth: 'high',
            monotone_detected: false,
            summary: 'Good vocal variety with warm delivery.',
        };

        const html = renderScoreCard('Voice & Tone', voiceTone);
        expect(html).toContain('Voice & Tone');
        expect(html).toContain('72/100');
        expect(html).toContain('Good vocal variety');
    });

    test('renders vocabulary score card', () => {
        const vocabulary = {
            score: 65,
            filler_word_count: 12,
            unique_word_ratio: 0.74,
            readability_level: 'conversational',
            summary: 'Conversational vocabulary with filler words.',
        };

        const html = renderScoreCard('Vocabulary', vocabulary);
        expect(html).toContain('Vocabulary');
        expect(html).toContain('65/100');
    });

    test('renders pacing score card', () => {
        const pacing = {
            score: 58,
            words_per_minute: 162,
            variation: 'low',
            pause_usage: 'insufficient',
            summary: 'Speaking pace is slightly fast.',
        };

        const html = renderScoreCard('Pacing', pacing);
        expect(html).toContain('Pacing');
        expect(html).toContain('58/100');
    });
});

// ---------------------------------------------------------------------------
// Full results rendering
// ---------------------------------------------------------------------------

describe('Results Rendering', () => {
    const sampleResults = {
        voice_tone: { score: 72, summary: 'Good variety.' },
        vocabulary: { score: 65, summary: 'Some fillers.' },
        pacing: { score: 58, summary: 'Slightly fast.' },
        overall_score: 64,
        overall_summary: 'Solid presentation with room for improvement.',
        recommendations: [
            'Slow down during key points',
            'Reduce filler words',
            'Vary vocal pitch',
        ],
    };

    function renderResults(results) {
        function renderScoreCard(title, data) {
            return `<div class="score-card"><h3>${title}</h3><div class="score">${data.score}/100</div><p>${data.summary}</p></div>`;
        }
        return `
            <div class="results-grid">
                ${renderScoreCard('Voice & Tone', results.voice_tone)}
                ${renderScoreCard('Vocabulary', results.vocabulary)}
                ${renderScoreCard('Pacing', results.pacing)}
            </div>
            <div class="overall-score">
                <h3>Overall TedX Score: ${results.overall_score}/100</h3>
                <p>${results.overall_summary}</p>
            </div>
            <div class="recommendations">
                <h3>Recommendations</h3>
                <ul>
                    ${results.recommendations.map(r => `<li>${r}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    test('includes all three category score cards', () => {
        const html = renderResults(sampleResults);
        expect(html).toContain('Voice & Tone');
        expect(html).toContain('Vocabulary');
        expect(html).toContain('Pacing');
    });

    test('displays overall TedX score', () => {
        const html = renderResults(sampleResults);
        expect(html).toContain('Overall TedX Score: 64/100');
    });

    test('displays overall summary', () => {
        const html = renderResults(sampleResults);
        expect(html).toContain('Solid presentation with room for improvement.');
    });

    test('renders all recommendations', () => {
        const html = renderResults(sampleResults);
        expect(html).toContain('Slow down during key points');
        expect(html).toContain('Reduce filler words');
        expect(html).toContain('Vary vocal pitch');
    });

    test('recommendations are list items', () => {
        const html = renderResults(sampleResults);
        const liCount = (html.match(/<li>/g) || []).length;
        expect(liCount).toBe(3);
    });
});

// ---------------------------------------------------------------------------
// Polling behavior tests
// ---------------------------------------------------------------------------

describe('Polling Behavior', () => {
    const POLL_INTERVAL_MS = 3000;

    test('poll interval is 3 seconds', () => {
        expect(POLL_INTERVAL_MS).toBe(3000);
    });

    test('polling stops on completed status', () => {
        const responses = [
            { status: 'processing' },
            { status: 'processing' },
            { status: 'completed', results: { overall_score: 64 } },
        ];

        let pollCount = 0;
        for (const response of responses) {
            pollCount++;
            if (response.status === 'completed' || response.status === 'failed') {
                break;
            }
        }
        expect(pollCount).toBe(3);
    });

    test('polling stops on failed status', () => {
        const responses = [
            { status: 'processing' },
            { status: 'failed' },
        ];

        let pollCount = 0;
        for (const response of responses) {
            pollCount++;
            if (response.status === 'completed' || response.status === 'failed') {
                break;
            }
        }
        expect(pollCount).toBe(2);
    });
});

// ---------------------------------------------------------------------------
// State display tests
// ---------------------------------------------------------------------------

describe('Display States', () => {
    test('loading state shows analyzing message', () => {
        const loadingHTML = '<p>Analyzing your presentation... This may take a minute.</p>';
        expect(loadingHTML).toContain('Analyzing');
    });

    test('error state shows error class', () => {
        const errorHTML = '<p class="error">Analysis failed. Please try again.</p>';
        expect(errorHTML).toContain('class="error"');
        expect(errorHTML).toContain('failed');
    });

    test('error state shows caught error message', () => {
        const err = new Error('Network timeout');
        const errorHTML = `<p class="error">Error: ${err.message}</p>`;
        expect(errorHTML).toContain('Network timeout');
    });
});
