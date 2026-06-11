"""
Simple development server for the Presenter Feedback frontend.

Usage:
    python serve.py
    python serve.py 3000    (to use a custom port)

Then open http://localhost:8080 in your browser.

Provides mock API endpoints matching the architecture specification:
- POST /api/uploads      -> returns presigned URL (mocked)
- POST /api/analyses     -> starts analysis, returns analysis_id
- GET  /api/analyses/{id} -> returns analysis results
- GET  /api/analyses     -> lists past analyses
- GET  /api/health       -> health check
"""

import http.server
import socketserver
import sys
import os
import json
import time
import random
import uuid

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# In-memory store for mock analyses
mock_analyses = {}


class DevHandler(http.server.SimpleHTTPRequestHandler):
    """Extended handler that serves static files and provides a mock API."""

    def do_POST(self):
        if self.path == '/api/uploads':
            self.handle_mock_upload()
        elif self.path == '/api/analyses':
            self.handle_mock_start_analysis()
        else:
            self.send_error(404, 'Not Found')

    def do_PUT(self):
        # Accept PUT to any path (simulates S3 presigned URL upload)
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            self.rfile.read(content_length)
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/health':
            self.send_json_response({"status": "healthy"})
        elif self.path.startswith('/api/analyses/'):
            analysis_id = self.path.split('/api/analyses/')[1].split('?')[0]
            self.handle_mock_get_analysis(analysis_id)
        elif self.path.startswith('/api/analyses'):
            self.handle_mock_list_analyses()
        elif self.path.startswith('/api/'):
            self.send_error(404, 'API endpoint not found')
        else:
            super().do_GET()

    def handle_mock_upload(self):
        """Return a mock presigned S3 upload URL."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        filename = body.get('filename', 'recording.webm')
        object_key = f"uploads/mock-user/{uuid.uuid4()}/{filename}"

        # The "presigned URL" just points back to this dev server
        self.send_json_response({
            "upload_url": f"http://localhost:{PORT}/mock-s3-upload",
            "object_key": object_key,
        })

    def handle_mock_start_analysis(self):
        """Start a mock analysis job."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        analysis_id = str(uuid.uuid4())[:8]
        mock_analyses[analysis_id] = {
            "created_at": time.time(),
            "object_key": body.get('object_key', ''),
            "poll_count": 0,
        }

        self.send_json_response({
            "analysis_id": analysis_id,
            "status": "processing",
        }, status=202)

    def handle_mock_get_analysis(self, analysis_id):
        """Return mock analysis results after simulated processing."""
        analysis = mock_analyses.get(analysis_id)

        if not analysis:
            # If not found, return completed results immediately (for history replays)
            self.send_json_response(generate_mock_results(analysis_id))
            return

        analysis['poll_count'] += 1

        # Simulate processing: complete after 2 polls (~6 seconds)
        if analysis['poll_count'] < 2:
            self.send_json_response({
                "analysis_id": analysis_id,
                "status": "processing",
            }, status=202)
            return

        self.send_json_response(generate_mock_results(analysis_id))

    def handle_mock_list_analyses(self):
        """Return an empty list of analyses."""
        self.send_json_response({
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 10,
        })

    def send_json_response(self, data, status=200):
        response_body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.end_headers()


def generate_mock_results(analysis_id):
    """Generate realistic mock feedback data matching the architecture schema."""
    return {
        "analysis_id": analysis_id,
        "status": "completed",
        "created_at": "2026-02-08T12:00:00Z",
        "results": {
            "voice_tone": {
                "score": random.randint(50, 95),
                "confidence_level": random.choice(["high", "moderate", "low"]),
                "warmth": random.choice(["high", "moderate"]),
                "monotone_detected": random.choice([True, False]),
                "summary": random.choice([
                    "Confident and clear with good projection.",
                    "Generally engaging tone with occasional flat sections.",
                    "Strong vocal presence that commands attention.",
                    "Warm delivery that connects well with the audience.",
                ]),
            },
            "vocabulary": {
                "score": random.randint(45, 90),
                "filler_word_count": random.randint(2, 18),
                "unique_word_ratio": round(random.uniform(0.55, 0.85), 2),
                "readability_level": random.choice(["conversational", "academic", "technical"]),
                "summary": random.choice([
                    "Rich vocabulary appropriate for the audience.",
                    "Good word diversity with room to reduce filler words.",
                    "Accessible language that maintains audience engagement.",
                    "Technical terms well-explained for general audience.",
                ]),
            },
            "pacing": {
                "score": random.randint(40, 92),
                "words_per_minute": random.randint(120, 180),
                "variation": random.choice(["high", "moderate", "low"]),
                "pause_usage": random.choice(["effective", "moderate", "insufficient"]),
                "summary": random.choice([
                    "Well-paced delivery with effective use of pauses.",
                    "Slightly fast in technical sections, good otherwise.",
                    "Consistent pace that could benefit from more variation.",
                    "Natural rhythm with good emphasis on key points.",
                ]),
            },
            "overall_score": random.randint(50, 90),
            "overall_summary": random.choice([
                "Your presentation shows strong potential. Focus on pause usage and vocal variety to reach the next level.",
                "Solid foundation with engaging delivery. Work on reducing filler words and varying your pace for emphasis.",
                "Good overall performance. Strategic pausing and stronger transitions would elevate your presentation significantly.",
                "Promising delivery with room to grow. Your vocabulary is strong - pair it with more dynamic vocal expression.",
            ]),
            "recommendations": random.sample([
                "Add 2-3 second pauses after your most important statements to let them land with the audience.",
                "Vary your speaking pace more deliberately - slow down for key points, speed up slightly for supporting details.",
                "Replace filler words ('um', 'like', 'you know') with deliberate pauses.",
                "Consider opening with a more provocative question or surprising statistic.",
                "Practice your transitions between sections for smoother flow.",
                "Increase vocal pitch variation to avoid monotone stretches.",
                "Use more concrete examples and analogies to illustrate abstract concepts.",
            ], 3),
        },
    }


with socketserver.TCPServer(("", PORT), DevHandler) as httpd:
    print(f"Presenter Feedback - Dev Server")
    print(f"Serving at http://localhost:{PORT}")
    print(f"")
    print(f"Mock API endpoints:")
    print(f"  POST /api/uploads       - Get presigned upload URL")
    print(f"  POST /api/analyses      - Start analysis")
    print(f"  GET  /api/analyses/{{id}} - Get analysis results")
    print(f"  GET  /api/analyses      - List analyses")
    print(f"  GET  /api/health        - Health check")
    print(f"")
    print(f"Press Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
