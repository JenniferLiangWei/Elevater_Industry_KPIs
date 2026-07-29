#!/usr/bin/env python3
"""
Elevator KPI Dashboard — Cloud/Local Server
Set ANTHROPIC_API_KEY environment variable to share one key with all users.
"""
import http.server, json, urllib.request, os

DASHBOARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'elevator_kpi_dashboard_v7.html')
PORT = int(os.environ.get('PORT', 8080))
HOST = '0.0.0.0'
# Shared API key — set via Railway environment variable
SHARED_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Per-IP daily rate limit for /api/chat (protects shared API credits)
from collections import defaultdict
import time
RATE_LIMIT_PER_DAY = int(os.environ.get('RATE_LIMIT_PER_DAY', '50'))
_ip_counts = defaultdict(int)
_ip_day = [time.strftime('%Y-%m-%d')]

def _rate_ok(ip):
    today = time.strftime('%Y-%m-%d')
    if today != _ip_day[0]:
        _ip_day[0] = today
        _ip_counts.clear()
    _ip_counts[ip] += 1
    return _ip_counts[ip] <= RATE_LIMIT_PER_DAY

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'POST')
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/elevator_kpi_dashboard_v7.html', '/index.html'):
            try:
                with open(DASHBOARD, 'rb') as f:
                    data = f.read()
                # Inject only a boolean flag — never the actual key (key stays server-side)
                if SHARED_KEY:
                    inject = b'<script>window.SHARED_KEY_AVAILABLE=true;</script>'
                    data = data.replace(b'</head>', inject + b'</head>', 1)
                # Serve timestamp for "last deployed" indicator
                import time as _t
                ts = _t.strftime('%Y-%m-%d %H:%M UTC', _t.gmtime(os.path.getmtime(DASHBOARD)))
                data = data.replace(b'</head>', f'<script>window.DEPLOYED_AT="{ts}";</script></head>'.encode(), 1)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except FileNotFoundError:
                self.send_error(404, 'Dashboard file not found.')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api/chat':
            ip = self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[0].strip()
            if not _rate_ok(ip):
                self.send_response(429)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"Daily AI request limit reached for this connection. Try again tomorrow."}}')
                return
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            payload = json.loads(body)
            # Use shared key if set, otherwise use key from request
            api_key = SHARED_KEY or payload.pop('api_key', '')
            payload.pop('api_key', None)

            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=json.dumps(payload).encode(),
                headers={
                    'Content-Type': 'application/json',
                    'anthropic-version': '2023-06-01',
                    'x-api-key': api_key
                },
                method='POST'
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(result)
            except urllib.error.HTTPError as e:
                err = e.read().decode()
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err.encode())
        else:
            self.send_error(404)

if SHARED_KEY:
    print(f"✓ Shared API key configured (key ending ...{SHARED_KEY[-4:]})")
else:
    print("⚠ No shared API key — users must enter their own key")
print(f"Starting server on port {PORT}...")
server = http.server.HTTPServer((HOST, PORT), Handler)
server.serve_forever()
