"""Capture demo frames from the running app (npm run dev) and live API via Edge DevTools.
Output: assets/video/frames/*.png. Creates ONE test report titled "FRONTEND TEST"."""
import base64, json, pathlib, subprocess, tempfile, time, urllib.request
import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUT = pathlib.Path(__file__).resolve().parents[2] / 'assets' / 'video' / 'frames'
OUT.mkdir(parents=True, exist_ok=True)
APP = 'http://localhost:5173/'
proc = subprocess.Popen([EDGE, '--headless=new', '--remote-debugging-port=9335', f'--user-data-dir={tempfile.mkdtemp()}', '--disable-gpu', '--hide-scrollbars', 'about:blank'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            ws_url = next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9335/json')) if t['type'] == 'page')['webSocketDebuggerUrl']; break
        except Exception: time.sleep(0.5)
    ws = websocket.create_connection(ws_url, timeout=90, suppress_origin=True)
    n = 0
    def send(m, **p):
        global n; n += 1; ws.send(json.dumps({'id': n, 'method': m, 'params': p}))
        while True:
            r = json.loads(ws.recv())
            if r.get('id') == n: return r.get('result', {})
    def js(e): return send('Runtime.evaluate', expression=e, awaitPromise=True, returnByValue=True).get('result', {}).get('value')
    def wait(cond, s=30):
        t = time.time()
        while time.time() - t < s:
            if js(cond): return True
            time.sleep(0.3)
        print('timeout:', cond[:60]); return False
    def shot(name): open(OUT / f'{name}.png', 'wb').write(base64.b64decode(send('Page.captureScreenshot', format='png')['data'])); print('saved', name)
    def phone(): send('Emulation.setDeviceMetricsOverride', width=390, height=844, deviceScaleFactor=2, mobile=True)
    def desk(): send('Emulation.setDeviceMetricsOverride', width=1280, height=720, deviceScaleFactor=1, mobile=False)
    def go(h):
        # Reload as well: same-screen hash changes keep component state (an open dialog would cover the frame).
        js("location.hash=%s" % json.dumps('#' + h)); time.sleep(0.3); send('Page.reload'); time.sleep(1)
        wait("location.hash===%s && document.querySelectorAll('.skeleton').length===0 && document.body.innerText.length>300" % json.dumps('#' + h)); time.sleep(1.2)
    def click(t, scope='document'):
        return js("(()=>{const b=[...%s.querySelectorAll('button,a')].find(x=>x.textContent.trim().startsWith(%s));if(!b)return false;b.click();return true})()" % (scope, json.dumps(t)))
    def type_into(sel, val, kind='HTMLInputElement'):
        js("(()=>{const i=document.querySelector(%s);const s=Object.getOwnPropertyDescriptor(%s.prototype,'value').set;s.call(i,%s);i.dispatchEvent(new Event('input',{bubbles:true}))})()" % (json.dumps(sel), kind, json.dumps(val)))
    def scroll_to(text, offset=90):
        js("(()=>{const e=[...document.querySelectorAll('h1,h2,h3,p')].find(x=>x.textContent.includes(%s));if(e)e.scrollIntoView({block:'start'});window.scrollBy(0,-%d)})()" % (json.dumps(text), offset)); time.sleep(0.8)
    D = "document.querySelector('[role=dialog]')"

    send('Page.enable'); send('Runtime.enable')
    desk(); send('Page.navigate', url=APP); time.sleep(1); js("sessionStorage.setItem('marg-splash-seen','1')")

    # Phone: citizen
    phone(); go('start')
    click('Type road or area'); type_into('input[placeholder]', 'Andheri subway ke bahar khadda wapas aa gaya, paisa kahan gaya?'); click('Ask')
    wait("document.body.innerText.includes('written by Claude')", 90); time.sleep(0.6)
    scroll_to('Find a road', 10); shot('p_answer')
    go('receipt?road=RD0220&report=1'); wait(f"!!{D}"); time.sleep(0.6)
    js("document.querySelector('input[name=kind][value=still_broken]').click()"); js("document.querySelector('input[name=issue][value=pothole]').click()"); time.sleep(0.3)
    js(f"{D}.querySelector('.overflow-y-auto').scrollTop=260"); time.sleep(0.3); shot('p_report_what')
    click('Next', D); time.sleep(0.4); click('Skip photo', D); time.sleep(0.4)
    type_into('[role=dialog] input[placeholder]', 'Opposite Kurla depot')
    type_into('[role=dialog] textarea', 'FRONTEND TEST, please ignore', 'HTMLTextAreaElement')
    click('Next', D); time.sleep(0.6); shot('p_review')
    click('Send report', D); wait("document.body.innerText.includes('received')"); time.sleep(1); shot('p_tracker')
    rid = js("(document.body.innerText.match(/Report (\\d+) received/)||[])[1]")
    go('me'); time.sleep(1); shot('p_me')
    go('admin'); click('Preview the dashboard'); time.sleep(1)
    type_into('input[inputmode=numeric]', str(rid)); click('Open'); wait(f"!!{D}"); time.sleep(0.8)
    js(f"{D}.querySelector('.overflow-y-auto').scrollTop=420"); time.sleep(0.4); shot('p_admin_report')
    go('admin'); click('Preview the dashboard'); time.sleep(0.6); click('Flags awaiting reply'); wait("document.body.innerText.includes('have no reply yet')"); time.sleep(0.8)
    scroll_to('have no reply yet', 20); shot('p_admin_flags')

    # Desktop: officer and city
    desk(); go('receipt?road=RD0220'); shot('d_receipt')
    scroll_to('Connected proof trail'); shot('d_trail')
    go('receipt?road=RD0220'); click('Draft defect notice'); wait("document.body.innerText.includes('Cites')", 120); time.sleep(0.8); shot('d_notice')
    go('city'); shot('d_city')
    scroll_to('Flagged bills'); shot('d_flagged')
    go('contractors'); scroll_to('How to read this', 20); shot('d_contractors')
    go('nextrupee'); scroll_to('Costs BMC', 140); shot('d_nextrupee')
    print('test report id', rid)
finally:
    proc.terminate()
