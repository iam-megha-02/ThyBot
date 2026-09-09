"""Optional browser check: install Playwright, then run this file (uses local Edge).

Starts an isolated Streamlit instance and fake HTTP backend; never calls the LLM.
Screenshots go to the OS temporary directory. Both servers stop on exit.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(tempfile.gettempdir()) / 'thybot-ui-review'
OUTPUT.mkdir(exist_ok=True)
CALLS = []


class MockBackend(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_POST(self):
        question = json.loads(self.rfile.read(int(self.headers['Content-Length'])))['question']
        CALLS.append(question)
        time.sleep(1)
        answer = ('## Understanding TSH\n\nTSH is a signal made by the **pituitary gland**. '
                  'It helps regulate thyroid hormone production.\n\n'
                  '- A clear explanation, grounded in the documents.\n'
                  '- Talk to your clinician about your own results.\n\n'
                  '```python\nresult = {"test": "TSH", "explanation": "' + 'long example ' * 18 +
                  '"}\nprint(result)\n```\n\n| Term | Meaning |\n| --- | --- |\n'
                  '| TSH | Thyroid stimulating hormone |\n\n'
                  '[Reference information](https://www.thyroid.org)')
        data = dict(answer=answer, sources=['thyroid_function_tests_faq.pdf'],
                    disclaimer='Educational information, not personal medical advice.', guardrail=None)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 8766), MockBackend)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, THYBOT_BACKEND_URL='http://127.0.0.1:8766')
    process = subprocess.Popen(
        [sys.executable, '-m', 'streamlit', 'run', 'frontend/app.py', '--server.port=8503',
         '--server.headless=true', '--browser.gatherUsageStats=false'], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            for _ in range(30):
                try:
                    page.goto('http://127.0.0.1:8503')
                    break
                except Exception:
                    time.sleep(.5)
            page.get_by_role('button', name='What is a goiter?', exact=False).wait_for()
            # Dark is now the app's only theme, applied on load — no toggle to click.
            page.locator('.theme-marker[data-theme="dark"]').wait_for(state='attached')
            page.wait_for_function('''getComputedStyle(document.querySelector('.stApp')).backgroundColor === 'rgb(28, 29, 26)' ''')
            assert page.locator('[data-testid="stChatInput"] > div').evaluate(
                'el => getComputedStyle(el).backgroundColor') == 'rgba(0, 0, 0, 0)'
            page.screenshot(path=str(OUTPUT / 'desktop.png'), full_page=True)
            page.get_by_role('button', name='What is a goiter?', exact=False).click()
            page.locator('.thinking').wait_for()
            assert page.get_by_placeholder('What would you like to understand?').is_disabled()
            page.locator('.st-key-assistant_message_1').wait_for()
            page.get_by_text('Explore a question', exact=True).click()
            page.get_by_role('button', name='What is a goiter?', exact=False).click()
            page.locator('.st-key-assistant_message_3').wait_for()
            assert len(CALLS) == 2, CALLS
            print('SCROLL', page.locator('[data-testid="stMain"]').count())
            page.screenshot(path=str(OUTPUT / 'conversation.png'), full_page=True)
            for width in [390, 768]:
                page.set_viewport_size({'width': width, 'height': 844})
                page.screenshot(path=str(OUTPUT / f'conversation-{width}.png'), full_page=True)
                assert page.evaluate('document.body.scrollWidth <= innerWidth'), 'Horizontal overflow'
            print('Passed: repeat HTTP requests, disabled pending input, mobile/tablet overflow.')
            print('Screenshots:', OUTPUT)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
