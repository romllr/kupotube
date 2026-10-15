from playwright.sync_api import sync_playwright
import os
import shutil
import sys
with sync_playwright() as p:
    executable = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium')
    launch = {'executable_path': executable} if executable else ({'channel': 'msedge'} if sys.platform == 'win32' else {})
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'], **launch)
    page = browser.new_page(viewport={'width':1080,'height':1000})
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/api/info', lambda route: route.fulfill(json={'title':'Vídeo de teste','uploader':'Kupotube','duration':93,'qualities':[2160,1080,720]}))
    page.add_init_script('''window.pywebview = {api: {
      start_download: async () => { window.polls = 0; return {started: true}; },
      get_progress: async () => {
        window.polls++;
        if(window.polls < 5) return {state:'downloading', percent:42, track:'Vídeo', speed:2097152, eta:8};
        if(window.polls < 7) return {state:'processing', percent:null};
        return {state:'complete', percent:100, filename:'Meu vídeo.mp4'};
      }
    }};''')
    page.goto(os.environ.get('KUPOTUBE_TEST_URL', 'http://127.0.0.1:8010/'))
    page.fill('#url','https://youtu.be/example')
    page.click('#analyze')
    page.wait_for_selector('#result',state='visible')
    assert page.locator('#quality option').count()==3
    page.select_option('#container','mkv')
    page.click('#download')
    page.wait_for_function("document.querySelector('#progress-value').textContent === '42%'")
    assert page.locator('#download').is_disabled()
    page.wait_for_selector('#toast',state='visible')
    assert page.locator('#progress-value').inner_text()=='100%'
    assert page.locator('#toast-text').inner_text()=='Meu vídeo.mp4'
    assert page.locator('#download').is_enabled()
    page.click('#toast-close')
    assert page.locator('#toast').is_hidden()
    page.click('#sound')
    assert page.locator('#sound').get_attribute('aria-pressed')=='false'
    page.set_viewport_size({'width':580,'height':750})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('img').evaluate_all('(images) => images.every(i => i.complete && i.naturalWidth > 0)')
    assert not errors, errors
    print('UI passed: quality/format selection, responsive layout, progress, busy state, toast, sound toggle, all icon assets loaded, no JS errors')
    browser.close()
