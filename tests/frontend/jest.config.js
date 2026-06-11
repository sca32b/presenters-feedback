module.exports = {
    testEnvironment: 'jsdom',
    testMatch: ['**/*.test.js'],
    collectCoverage: true,
    coverageDirectory: '../coverage/frontend',
    coverageReporters: ['text', 'text-summary', 'lcov', 'html'],
    verbose: true,
};
