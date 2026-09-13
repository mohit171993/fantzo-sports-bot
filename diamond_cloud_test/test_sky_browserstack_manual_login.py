# Sky Live Pro BrowserStack real-device Chrome playback PoC
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By

PORT=int(os.getenv('PORT','8080'))
BS_USER=os.getenv('BROWSERSTACK_USERNAME','').strip()
BS_KEY=os.getenv('BROWSERSTACK_ACCESS_KEY','').strip()
STATE={'status':'starting','steps':[]}
LOCK=threading.Lock()

def set_state(**kw):
    with LOCK: STATE.update(kw)

def step(name,ok=True,detail=None):
    x={'name':name,'ok':bool(ok)}
    if detail is not None: x['detail']=str(detail)[:400]
    with LOCK: STATE['steps'].append(x)

def safe(e):
    s=str(e)
    for v in (BS_USER,BS_KEY):
        if v: s=s.replace(v,'[REDACTED]')
    return s[:800]

def choose_device():
    r=requests.get('https://api-cloud.browserstack.com/app-automate/devices.json',auth=(BS_USER,BS_KEY),timeout=60)
    r.raise_for_status()
    items=[d for d in r.json() if str(d.get('os','')).lower()=='android']
    if not items: raise RuntimeError('No Android real device available in BrowserStack App Automate')
    pref=['Samsung Galaxy S24','Samsung Galaxy S23','Google Pixel 8','Google Pixel 7']
    for name in pref:
        for d in items:
            if d.get('device')==name: return d
    return items[0]

def vids(driver):
    return driver.execute_script("return Array.from(document.querySelectorAll('video')).map((v,i)=>({i,currentTime:Number(v.currentTime||0),readyState:Number(v.readyState||0),w:Number(v.videoWidth||0),h:Number(v.videoHeight||0),paused:!!v.paused}));")

def session_browser_url(session_id):
    try:
        r=requests.get(f'https://api.browserstack.com/automate/sessions/{session_id}.json',auth=(BS_USER,BS_KEY),timeout=20)
        if r.ok:
            data=r.json().get('automation_session',{})
            return data.get('browser_url') or data.get('public_url')
    except Exception:
        pass
    return None

def worker():
    if not BS_USER or not BS_KEY:
        set_state(status='waiting_for_browserstack_variables'); return
    driver=None
    try:
        d=choose_device(); dev=d.get('device'); osv=str(d.get('os_version'))
        step('select_real_android_device',True,f'{dev} / Android {osv}')
        opt=UiAutomator2Options()
        opt.set_capability('platformName','Android')
        opt.set_capability('browserName','Chrome')
        opt.set_capability('appium:deviceName',dev)
        opt.set_capability('appium:platformVersion',osv)
        opt.set_capability('appium:automationName','UiAutomator2')
        opt.set_capability('appium:newCommandTimeout',360)
        opt.set_capability('bstack:options',{'userName':BS_USER,'accessKey':BS_KEY,'projectName':'Fantzo Sky Web PoC','buildName':f'sky-{int(time.time())}','sessionName':'Sky manual-login playback test','debug':True,'video':True,'networkLogs':False})
        driver=webdriver.Remote('https://hub-cloud.browserstack.com/wd/hub',options=opt)
        sid=driver.session_id
        set_state(status='waiting_for_manual_login',session_id=sid,device=dev,android_version=osv)
        burl=session_browser_url(sid)
        if burl: set_state(browserstack_session_url=burl)
        driver.get('https://skylivepro.com')
        step('open_sky_login',True)
        deadline=time.time()+300
        while time.time()<deadline:
            if driver.find_elements(By.ID,'button-container'):
                break
            time.sleep(3)
        if not driver.find_elements(By.ID,'button-container'):
            raise RuntimeError('Login was not completed within 5 minutes')
        step('login_detected',True)
        deadline=time.time()+60
        buttons=[]
        while time.time()<deadline:
            buttons=[b for b in driver.find_elements(By.CSS_SELECTOR,'#button-container button') if b.is_displayed()]
            if buttons: break
            time.sleep(2)
        if not buttons: raise RuntimeError('No visible channel buttons after login')
        set_state(visible_channel_button_count=len(buttons))
        step('channel_buttons_loaded',True,len(buttons))
        buttons[0].click(); step('open_first_available_channel',True)
        deadline=time.time()+60
        while time.time()<deadline and not driver.find_elements(By.TAG_NAME,'video'):
            time.sleep(2)
        if not driver.find_elements(By.TAG_NAME,'video'):
            raise RuntimeError('No video element appeared')
        a=vids(driver); time.sleep(10); b=vids(driver)
        playing=False; checks=[]
        for x,y in zip(a,b):
            advanced=y['currentTime']>x['currentTime']+1
            frames=y['readyState']>=2 and y['w']>0 and y['h']>0
            if advanced and frames: playing=True
            checks.append({'index':y['i'],'time_advanced':advanced,'ready_state':y['readyState'],'video_width':y['w'],'video_height':y['h'],'paused':y['paused']})
        set_state(status='playback_confirmed' if playing else 'player_open_but_playback_not_confirmed',playback_confirmed=playing,video_checks=checks)
        step('browser_video_playback',playing)
    except Exception as e:
        step('failure',False,safe(e)); set_state(status='failed',error=safe(e))
    finally:
        if driver:
            try: driver.quit()
            except: pass

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/health'): body=b'ok'; ct='text/plain'
        else:
            with LOCK: body=json.dumps(STATE,indent=2).encode()
            ct='application/json'
        self.send_response(200); self.send_header('Content-Type',ct); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def log_message(self,*a): pass

threading.Thread(target=worker,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
