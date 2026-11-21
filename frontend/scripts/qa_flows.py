"""End-to-end flow check against the running app (npm run dev) and live API, via Edge DevTools.

Usage: python frontend/scripts/qa_flows.py            (creates ONE test report titled "FRONTEND TEST")
Screenshots: assets/qa/*.png. Exit code 1 if any check fails.
"""
import base64, json, os, pathlib, subprocess, sys, tempfile, threading, time, urllib.request
import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
APP = os.environ.get('QA_APP', 'http://localhost:5173/')  # QA_DEMO=1 adds the demo-only checks (set QA_APP to the demo server)
DEMO = os.environ.get('QA_DEMO') == '1'
OUT = pathlib.Path(__file__).resolve().parents[2] / 'assets' / 'qa'; OUT.mkdir(parents=True, exist_ok=True)
results, errors = [], []

proc = subprocess.Popen([EDGE, '--headless=new', '--remote-debugging-port=9336', f'--user-data-dir={tempfile.mkdtemp()}', '--disable-gpu', '--hide-scrollbars', 'about:blank'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            ws_url = next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9336/json')) if t['type'] == 'page')['webSocketDebuggerUrl']; break
        except Exception: time.sleep(0.5)
    ws = websocket.create_connection(ws_url, timeout=40, suppress_origin=True)
    n = 0; pending = {}
    lock = threading.Lock()
    def reader():
        while True:
            try: m = json.loads(ws.recv())
            except Exception: return
            if 'id' in m:
                with lock: pending[m['id']] = m
            elif m.get('method') == 'Runtime.exceptionThrown':
                errors.append(m['params']['exceptionDetails'].get('exception', {}).get('description', m['params']['exceptionDetails'].get('text'))[:200])
            elif m.get('method') == 'Runtime.consoleAPICalled' and m['params']['type'] == 'error':
                errors.append(' '.join(str(a.get('value', a.get('description', ''))) for a in m['params']['args'])[:200])
    threading.Thread(target=reader, daemon=True).start()
    def send(method, **p):
        global n; n += 1; i = n; ws.send(json.dumps({'id': i, 'method': method, 'params': p}))
        for _ in range(400):
            with lock:
                if i in pending: return pending.pop(i).get('result', {})
            time.sleep(0.05)
        return {}
    js = lambda e: send('Runtime.evaluate', expression=e, awaitPromise=True, returnByValue=True).get('result', {}).get('value')
    def wait(cond, s=25):
        t = time.time()
        while time.time() - t < s:
            if js(cond): return True
            time.sleep(0.3)
        return False
    def check(name, ok): results.append((name, bool(ok))); print(('PASS ' if ok else 'FAIL ') + name)
    def shot(name): open(OUT / f'{name}.png', 'wb').write(base64.b64decode(send('Page.captureScreenshot', format='png').get('data', ''))) if True else None
    def go(h):
        send('Page.navigate', url=APP + '#' + h); send('Page.reload')
        wait("document.querySelectorAll('.skeleton').length===0 && document.body.innerText.length>200"); time.sleep(1)
    def click(t, scope='document'):
        return js("(()=>{const b=[...%s.querySelectorAll('button,a')].find(x=>x.textContent.trim().startsWith(%s));if(!b)return false;b.click();return true})()" % (scope, json.dumps(t)))
    def type_into(sel, val, kind='HTMLInputElement'):
        js("(()=>{const i=document.querySelector(%s);const s=Object.getOwnPropertyDescriptor(%s.prototype,'value').set;s.call(i,%s);i.dispatchEvent(new Event('input',{bubbles:true}))})()" % (json.dumps(sel), kind, json.dumps(val)))
    no_overflow = "document.documentElement.scrollWidth <= window.innerWidth"
    D = "document.querySelector('[role=dialog]')"

    send('Page.enable'); send('Runtime.enable')
    for view, (w, h, mobile) in {'phone': (390, 844, True), 'desktop': (1280, 800, False)}.items():
        send('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=1, mobile=mobile)
        send('Page.navigate', url=APP + '#start')
        check(f'{view}: boot splash closes and app renders', wait("!document.querySelector('[aria-label=\"Loading MARG\"]') && !!document.querySelector('header')", 15))
        nav = "nav.fixed" if mobile else "header nav"
        check(f'{view}: navigation visible', js("(()=>{const n=document.querySelector(%s);return !!n&&getComputedStyle(n).display!=='none'})()" % json.dumps(nav)))
        for screen in ['start', 'city', 'contractors', 'nextrupee', 'receipt?road=RD0220', 'me', 'admin']:
            go(screen); check(f'{view}: {screen} loads without overflow', js(no_overflow) and not js("!!document.querySelector('[role=alert]')")); shot(f'{view}-{screen.split("?")[0]}')

        if view == 'phone':
            # Lookup -> receipt
            go('start'); click('Type road or area'); type_into('input[placeholder]', 'Andheri subway ke bahar khadda wapas aa gaya, paisa kahan gaya?'); click('Ask')
            check('citizen question matches a road', wait("document.body.innerText.includes('Open road receipt')", 60))
            check('Claude plain-language answer shown', js("document.body.innerText.includes('written by Claude')")); shot('phone-answer')
            click('Open road receipt'); check('open receipt from lookup', wait("location.hash.startsWith('#receipt') && document.body.innerText.includes('Connected proof trail')"))
            # Report workflow
            go('receipt?road=RD0220&report=1'); check('report form opens', wait(f"!!{D}"))
            js("document.querySelector('input[name=kind][value=still_broken]').click()"); js("document.querySelector('input[name=issue][value=pothole]').click()")
            click('Next', D); time.sleep(0.4); click('Skip photo', D); time.sleep(0.4)
            type_into('[role=dialog] textarea', 'FRONTEND TEST, please ignore', 'HTMLTextAreaElement'); click('Next', D); time.sleep(0.4)
            check('review step shows choices', js("document.querySelector('[role=dialog]').innerText.includes('Pothole')"))
            click('Send report', D); check('report sent and tracker shown', wait("document.body.innerText.includes('received')")); shot('phone-report-done')
            rid = js("(document.body.innerText.match(/Report (\\d+) received/)||[])[1]")
            # My reports
            go('me'); check('report appears in My reports', wait("document.body.innerText.includes('Report %s')" % rid)); shot('phone-me')
            click('Report %s' % rid); check('my report opens with tracker', wait(f"!!{D}")); shot('phone-me-detail')
            # Admin preview: open the same report, flags tab
            go('admin'); click('Preview the dashboard'); time.sleep(1)
            type_into('input[inputmode=numeric]', str(rid)); click('Open'); check('ward office opens the report by number', wait(f"!!{D} && {D}.innerText.includes('Report {rid}')")); shot('phone-admin-report')
            go('admin'); click('Preview the dashboard'); time.sleep(0.5); click('Flags awaiting reply'); check('flags awaiting reply listed', wait("document.body.innerText.includes('have no reply yet')")); shot('phone-admin-flags')
        else:
            go('receipt?road=RD0220'); click('Draft defect notice')
            check('defect notice drafted by Claude with citations', wait("document.body.innerText.includes('Cites')", 90)); shot('desktop-notice')
            go('city'); before = js("document.body.innerText.length")
            js("(()=>{const p=document.querySelector('path[aria-label=\"Ward K/W\"]');p&&p.dispatchEvent(new MouseEvent('click',{bubbles:true}))})()")
            check('ward map filters flagged bills', wait("document.body.innerText.includes('Flagged bills in ward K/W')"))
            go('nextrupee'); s1 = js("document.body.innerText.match(/Funded by this budget\\s+([^\\n]+)/)?.[1]")
            js("(()=>{const r=document.querySelector('input[type=range]');const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(r,String(Number(r.max)));r.dispatchEvent(new Event('input',{bubbles:true}))})()")
            time.sleep(3); s2 = js("document.body.innerText.match(/Funded by this budget\\s+([^\\n]+)/)?.[1]")
            check('budget slider re-solves on the server', s1 and s2 and s1 != s2)
            click('हिं'); check('language toggle changes the nav', wait("document.querySelector('header nav').innerText.includes('सड़क')")); click('EN')
    if DEMO:
        # Demo loop: a visitor's report is moved forward by the ward office and the citizen sees it. Everything stays in the browser.
        send('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=1, mobile=True)
        check('demo banner shown', js("document.body.innerText.includes('Demo version')"))
        go('admin'); type_into('input[type=email]', 'officer@demo.in'); type_into('input[type=password]', 'anything'); click('Sign in')
        check('demo officer signs in', wait("document.body.innerText.includes('Signed in as')"))
        rid2 = js("JSON.parse(localStorage.getItem('marg-my-reports')||'[]').slice(-1)[0]")
        type_into('input[inputmode=numeric]', str(rid2)); click('Open'); check('officer opens the visitor report', wait(f"!!{D}"))
        click('Mark: Contractor notified', D); check('officer marks the contractor notified', wait("document.body.innerText.includes('Saved. The citizen sees this')")); shot('demo-admin-moved')
        go('me'); click('Report %s' % rid2); check('citizen sees the officer step on the tracker', wait("[...document.querySelectorAll('[role=dialog] span')].some(e=>e.textContent==='Contractor notified')")); shot('demo-citizen-sees')
        go('receipt?road=RD0001'); check('road outside the demo set shows a friendly note', wait("document.body.innerText.includes('Connected proof trail') || document.body.innerText.includes('not part of the demo data')"))
    check('no console errors', not errors)
    for e in errors[:8]: print('  console:', e)
finally:
    proc.terminate()
failed = [r for r in results if not r[1]]
print(f'\n{len(results) - len(failed)}/{len(results)} checks passed. Screenshots: {OUT}')
sys.exit(1 if failed else 0)
