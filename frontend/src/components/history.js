/**
 * History component. Displays past analyses.
 */

import { listAnalyses } from '../api.js';

export function initHistory() {
    loadHistory();
}

async function loadHistory() {
    const container = document.getElementById('history-container');
    try {
        const data = await listAnalyses();
        if (data.items.length === 0) {
            container.innerHTML = '<p>No past analyses yet. Record your first presentation above.</p>';
            return;
        }
        container.innerHTML = `
            <table class="history-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Overall Score</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.items.map(item => `
                        <tr>
                            <td>${new Date(item.created_at).toLocaleDateString()}</td>
                            <td>${item.results ? item.results.overall_score + '/100' : '-'}</td>
                            <td>${item.status}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch {
        container.innerHTML = '<p>Could not load history.</p>';
    }
}
