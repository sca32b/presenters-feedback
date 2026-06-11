/**
 * Results display component. Polls for analysis completion and renders feedback.
 */

import { getAnalysis } from '../api.js';

const POLL_INTERVAL_MS = 3000;

export function initResults() {
    window.addEventListener('analysis-started', (e) => {
        const { analysisId } = e.detail;
        pollForResults(analysisId);
    });
}

async function pollForResults(analysisId) {
    const container = document.getElementById('results-container');
    const section = document.getElementById('results-section');
    section.classList.remove('hidden');
    container.innerHTML = '<p>Analyzing your presentation... This may take a minute.</p>';

    const poll = async () => {
        try {
            const data = await getAnalysis(analysisId);
            if (data.status === 'completed') {
                renderResults(container, data.results);
            } else if (data.status === 'failed') {
                container.innerHTML = '<p class="error">Analysis failed. Please try again.</p>';
            } else {
                setTimeout(poll, POLL_INTERVAL_MS);
            }
        } catch (err) {
            container.innerHTML = `<p class="error">Error: ${err.message}</p>`;
        }
    };

    poll();
}

function renderResults(container, results) {
    container.innerHTML = `
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

function renderScoreCard(title, data) {
    return `
        <div class="score-card">
            <h3>${title}</h3>
            <div class="score">${data.score}/100</div>
            <p>${data.summary}</p>
        </div>
    `;
}
