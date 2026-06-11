/**
 * Main application entry point.
 * Initializes the recorder, results display, and history components.
 */

import { initRecorder } from './components/recorder.js';
import { initResults } from './components/results.js';
import { initHistory } from './components/history.js';

function init() {
    initRecorder();
    initResults();
    initHistory();
}

document.addEventListener('DOMContentLoaded', init);
