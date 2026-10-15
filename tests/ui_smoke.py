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
      start_download: async (url, quality, format) => { window.polls = 0; window.lastFormat = format; return {started: true}; },
      check_update: async () => {
        await new Promise(resolve => setTimeout(resolve,100));
        if (window.updateMode === 'error') return {error:'Sem conexão de teste',current:'0.3.1'};
        return {available:window.updateMode !== 'latest',current:'0.3.1',version:'99.0.0'};
      },
      install_update: async () => ({started:true}),
      get_update_progress: async () => ({state:'error',error:'Falha de atualização simulada'}),
      get_preferences: async () => ({sound:true}),
      set_sound_enabled: async () => ({saved:true}),
      get_progress: async () => {
        window.polls++;
        if(window.polls < 5) return {state:'downloading', percent:42, track:'Vídeo', speed:2097152, eta:8};
        if(window.polls < 7) return {state:'processing', percent:null};
        return {state:'complete', percent:100, filename:window.lastFormat === 'mp3' ? 'Meu áudio.mp3' : 'Meu vídeo.mp4'};
      }
    }};''')
    page.goto(os.environ.get('KUPOTUBE_TEST_URL', 'http://127.0.0.1:8010/'))
    page.wait_for_selector('#update-banner',state='visible')
    assert not page.locator('#update-dialog').is_visible()
    assert page.locator('#check-update').bounding_box()['y'] < 150
    page.fill('#url','https://youtu.be/example')
    page.click('#analyze')
    page.wait_for_selector('#result',state='visible')
    assert page.locator('#quality option').count()==3
    assert page.locator('#update-banner').is_visible()
    assert page.locator('#container').evaluate("e => getComputedStyle(e).appearance") == 'none'
    page.select_option('#container','mkv')
    page.click('#download')
    page.wait_for_function("document.querySelector('#progress-value').textContent === '42%'")
    assert page.locator('#download').is_disabled()
    assert page.locator('#progress-bar').evaluate("e => getComputedStyle(e).backgroundColor") == 'rgb(166, 218, 149)'
    page.wait_for_selector('#toast',state='visible')
    assert page.locator('#progress-value').inner_text()=='100%'
    assert page.locator('#toast-text').inner_text()=='Meu vídeo.mp4'
    assert page.locator('#download').is_enabled()
    page.click('#toast-close')
    assert page.locator('#toast').is_hidden()
    page.select_option('#container','mp3')
    assert page.locator('#quality-field').is_hidden()
    assert page.locator('#download-label').inner_text() == 'Baixar MP3'
    page.click('#download')
    page.wait_for_function("document.querySelector('#toast-text').textContent === 'Meu áudio.mp3'")
    assert page.evaluate('window.lastFormat') == 'mp3'
    page.click('#install-update')
    page.wait_for_function("document.querySelector('#status').textContent === 'Falha de atualização simulada'")
    assert page.locator('#download').is_enabled()
    page.evaluate("window.updateMode = 'latest'")
    page.click('#check-update')
    page.wait_for_selector('#update-dialog[open]')
    assert page.locator('#update-dialog-title').inner_text() == 'O Kupo já está atualizado!'
    assert page.locator('#update-dialog-version').inner_text() == 'VERSÃO 0.3.1'
    assert page.locator('#update-dialog-confirm').evaluate('e => e === document.activeElement')
    assert page.locator('#update-banner').is_hidden()
    page.screenshot(path=os.environ.get('KUPOTUBE_MODAL_SCREENSHOT','/tmp/kupotube-update-modal.png')) if sys.platform != 'win32' else None
    page.keyboard.press('Escape')
    assert not page.locator('#update-dialog').is_visible()
    assert page.locator('#check-update').evaluate('e => e === document.activeElement')
    page.evaluate('checkUpdate()')
    page.wait_for_selector('#check-update:not([disabled])')
    assert not page.locator('#update-dialog').is_visible()
    page.evaluate("window.updateMode = 'error'")
    page.click('#check-update')
    page.wait_for_selector('#update-dialog[open]')
    assert page.locator('#update-dialog-title').inner_text() == 'Não foi possível verificar'
    assert 'Sem conexão' in page.locator('#update-dialog-description').inner_text()
    page.click('#update-dialog-confirm')
    assert not page.locator('#update-dialog').is_visible()
    page.evaluate("window.updateMode = 'available'")
    page.click('#check-update')
    page.wait_for_selector('#update-banner',state='visible')
    assert not page.locator('#update-dialog').is_visible()
    page.evaluate('window.scrollTo(0,600)')
    assert page.locator('#update-banner').bounding_box()['y'] >= 0
    page.click('#sound')
    assert page.locator('#sound').get_attribute('aria-pressed')=='false'
    page.set_viewport_size({'width':580,'height':750})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('img').evaluate_all('(images) => images.every(i => i.complete && i.naturalWidth > 0)')
    assert not errors, errors
    print('UI passed: header update button, sticky banner, latest/error modals, focus/Escape, silent automatic checks, MP3/download and notification regressions')
    browser.close()
