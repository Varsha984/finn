"""One command: python run.py [--live] -> installs nothing, builds index.html, serves it on :8000."""
import http.server, os, subprocess, sys, socketserver
if "--live" in sys.argv:
    os.environ["FINN_LIVE"] = "1"
subprocess.run([sys.executable, "build.py"], check=True)
print("Open http://localhost:8000/index.html  (phone on same Wi-Fi: use your laptop's IP)")
with socketserver.TCPServer(("", 8000), http.server.SimpleHTTPRequestHandler) as s:
    s.serve_forever()
