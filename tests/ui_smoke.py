from playwright.sync_api import sync_playwright, expect
import os
import shutil
import sys
import traceback


def report_failure(kind, value, stack):
    text = ''.join(traceback.format_exception(kind, value, stack))
    if os.environ.get('GITHUB_ACTIONS'):
        escaped = text.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error title=Falha na interface::{escaped}', flush=True)
    sys.__excepthook__(kind, value, stack)


sys.excepthook = report_failure
with sync_playwright() as p:
    executable = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium')
    launch = {'executable_path': executable} if executable else ({'channel': 'msedge'} if sys.platform == 'win32' else {})
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'], **launch)
    page = browser.new_page(viewport={'width':1080,'height':1000})
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/api/info', lambda route: route.fulfill(json={'title':'Vídeo de teste','uploader':'Kupotube','duration':93,'qualities':[2160,1080,720]}))
    page.add_init_script('''window.pywebview = {api: {
      start_download: async (url, quality, format, title, start, end) => { window.lastRange = [start,end]; window.polls = 0; window.lastFormat = format; return {started: true}; },
      check_update: async () => {
        await new Promise(resolve => setTimeout(resolve,100));
        if (window.updateMode === 'error') return {error:'Sem conexão de teste',current:'0.3.8'};
        return {available:window.updateMode !== 'latest',current:'0.3.8',version:'99.0.0'};
      },
      install_update: async () => ({started:true}),
      get_update_progress: async () => ({state:'error',error:'Falha de atualização simulada'}),
      get_preferences: async () => ({sound:true}),
      set_sound_enabled: async () => ({saved:true}),
      reveal_download: async () => { window.revealed = true; return {opened:true}; },
      get_progress: async () => {
        window.polls++;
        if(window.polls < 5) return {state:'downloading', percent:42, track:'Vídeo', speed:2097152, eta:8, folder:'C:/Users/Test/Downloads/Pasta de vídeos'};
        if(window.polls < 7) return {state:'processing', percent:null};
        return {state:'complete', percent:100, filename:window.lastFormat === 'mp3' ? 'Meu áudio.mp3' : 'Meu vídeo.mp4'};
      }
    }};''')
    page.goto(os.environ.get('KUPOTUBE_TEST_URL', 'http://127.0.0.1:8010/'))
    page.wait_for_selector('#update-banner',state='visible')
    if sys.platform != 'win32':
        page.locator('#update-banner').evaluate('e => e.hidden = true')
        page.screenshot(path='/tmp/kupotube-ui-preview-home.png', full_page=True)
        page.locator('#update-banner').evaluate('e => e.hidden = false')
    page.evaluate('document.fonts.ready')
    assert page.evaluate("document.fonts.check('16px DM Sans')")
    assert page.locator('body').evaluate('e => getComputedStyle(e).fontFamily').startswith('\"DM Sans\"')
    assert page.locator('.maker-credit').inner_text() == 'Made by romllr <3'
    assert page.locator('.maker-credit').evaluate("e => getComputedStyle(e).color") == 'rgb(245, 189, 230)'
    assert page.locator('html').evaluate("e => getComputedStyle(e).scrollbarColor") == 'rgb(91, 96, 120) rgb(20, 21, 31)'
    assert page.locator('h1').inner_text() == 'Cole o link.\nBaixe o vídeo.'
    assert 'qualidade e o formato' in page.locator('.intro').inner_text()
    assert page.locator('.eyebrow').inner_text() == 'DOWNLOAD DIRETO · NO SEU COMPUTADOR'
    assert 'DM Sans' in page.locator('.eyebrow').evaluate('e => getComputedStyle(e).fontFamily')
    assert 'DM Sans' in page.locator('.intro').evaluate('e => getComputedStyle(e).fontFamily')
    assert float(page.locator('h1').evaluate('e => parseFloat(getComputedStyle(e).fontSize)')) >= 60
    assert page.locator('body').evaluate('e => getComputedStyle(e).backgroundColor') == 'rgb(24, 25, 38)'
    assert 'YouTube' in page.locator('.session-options summary').inner_text()
    assert page.locator('.header-note').count() == 0
    assert page.locator('.platforms>span').inner_text() == 'Compatível com:'
    assert float(page.locator('.intro').evaluate('e => parseFloat(getComputedStyle(e).fontSize)')) >= 13
    page.click('#release-news')
    expect(page.locator('#releases-dialog')).to_be_visible()
    assert page.locator('#release-picker option').count() == 8
    expect(page.locator('#release-content')).to_contain_text('UI preview 05')
    first_height = page.locator('#releases-dialog').bounding_box()['height']
    page.select_option('#release-picker','7')
    expect(page.locator('#release-content')).to_contain_text('v0.3.2')
    assert page.locator('#release-older').is_disabled()
    page.click('#release-newer')
    expect(page.locator('#release-content')).to_contain_text('v0.3.3')
    page.select_option('#release-picker','2')
    expect(page.locator('#release-content')).to_contain_text('recorte local')
    assert page.locator('#releases-dialog').bounding_box()['height'] < 650
    page.keyboard.press('Escape')
    expect(page.locator('#release-news')).to_be_focused()
    assert page.locator('#cookies-help').evaluate('e => getComputedStyle(e).color') == 'rgb(245, 189, 230)'
    button = page.locator('#analyze')
    original_box = button.bounding_box()
    original_background = button.evaluate('e => getComputedStyle(e).backgroundImage')
    button.hover()
    page.wait_for_timeout(200)
    hover_box = button.bounding_box()
    assert abs(original_box['y'] - hover_box['y']) < .1
    assert button.evaluate('e => getComputedStyle(e).backgroundImage') == original_background
    page.locator('.session-options summary').click()
    page.click('#cookies-help')
    expect(page.locator('#cookies-dialog')).to_be_visible()
    assert page.locator('#cookies-dialog').evaluate('e => getComputedStyle(e).animationName') == 'kupo-dialog-in'
    assert page.locator('.cookies-steps li').count() == 4
    assert 'Netscape cookies.txt' in page.locator('#cookies-dialog').inner_text()
    assert 'todos os sites' in page.locator('#cookies-dialog').inner_text()
    assert 'Remover sessão' in page.locator('#cookies-dialog').inner_text()
    page.screenshot(path='/tmp/kupotube-cookies.png') if sys.platform != 'win32' else None
    page.keyboard.press('Escape')
    expect(page.locator('#cookies-dialog')).not_to_be_visible()
    expect(page.locator('#cookies-help')).to_be_focused()
    page.locator('.session-options summary').click()
    page.wait_for_function("!document.querySelector('.session-options').open")
    page.locator('.session-options summary').evaluate('e => e.click()')
    assert page.locator('.session-options').evaluate('e => e.getAnimations().length') > 0
    page.locator('.session-options summary').evaluate('e => e.click()')
    page.wait_for_function("!document.querySelector('.session-options').open")
    assert not page.locator('#update-dialog').is_visible()
    assert page.locator('#check-update').bounding_box()['y'] < 150
    page.fill('#url','https://youtu.be/example')
    page.locator('#url').evaluate("e => {const data = new DataTransfer(); data.setData('text','https://youtu.be/example'); e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true}));}")
    expect(page.locator('#selection-dialog')).to_be_visible()
    assert page.locator('#clip-start').input_value() == ''
    assert page.locator('#clip-end').input_value() == ''
    page.keyboard.press('Escape')
    page.click('#analyze')
    expect(page.locator('#selection-dialog')).to_be_visible()
    page.check('input[name="selection-mode"][value="clip"]')
    assert page.locator('#clip-format option').count() == 4
    page.select_option('#clip-format','mkv')
    page.fill('#clip-start','00:07')
    page.fill('#clip-end','00:03')
    page.locator('#selection-form button[type="submit"]').click()
    expect(page.locator('#selection-error')).to_contain_text('maior')
    page.fill('#clip-end','00:19')
    page.locator('#selection-form button[type="submit"]').click()
    page.wait_for_selector('#result',state='visible')
    assert page.locator('#selection-label').inner_text() == 'Trecho · 0:07 → 0:19'
    assert page.locator('#container').input_value() == 'mkv'
    page.click('#edit-selection')
    page.fill('#clip-end','02:00')
    page.locator('#selection-form button[type="submit"]').click()
    expect(page.locator('#selection-error')).to_contain_text('duração')
    page.fill('#clip-end','00:19')
    page.locator('#selection-form button[type="submit"]').click()
    assert page.locator('#quality option').count()==3
    assert page.locator('#update-banner').is_visible()
    assert page.locator('#container').evaluate("e => getComputedStyle(e).appearance") == 'none'
    page.select_option('#container','mkv')
    page.locator('#download').hover()
    page.wait_for_timeout(230)
    assert page.locator('#download').evaluate('e => getComputedStyle(e).boxShadow') != 'none'
    page.click('#download')
    page.wait_for_function("document.querySelector('#progress-value').textContent === '42%'")
    assert page.locator('#download').is_disabled()
    expect(page.locator('#download-destination')).to_contain_text('C:/Users/Test/Downloads/Pasta de vídeos')
    expect(page.locator('#clear-result')).to_be_hidden()
    assert page.evaluate('window.lastRange') == [7,19]
    assert page.locator('#progress-bar').evaluate("e => getComputedStyle(e).backgroundColor") == 'rgb(166, 218, 149)'
    page.wait_for_selector('#toast',state='visible')
    assert page.locator('#progress-value').inner_text()=='100%'
    assert page.locator('#toast-text').inner_text()=='Meu vídeo.mp4'
    expect(page.locator('#clear-result')).to_be_visible()
    page.click('#reveal-download')
    assert page.evaluate('window.revealed') is True
    assert page.locator('#download-destination').is_visible()
    assert page.locator('#download').is_enabled()
    page.click('#toast-close')
    expect(page.locator('#toast')).to_be_hidden()
    page.click('#edit-selection')
    page.check('input[name="selection-mode"][value="full"]')
    page.locator('#selection-form button[type="submit"]').click()
    assert page.locator('#selection-label').inner_text() == 'Vídeo inteiro'
    page.select_option('#container','mp3')
    assert page.locator('#quality-field').is_hidden()
    assert page.locator('#download-label').inner_text() == 'Baixar MP3'
    page.click('#download')
    page.wait_for_function("document.querySelector('#toast-text').textContent === 'Meu áudio.mp3'")
    assert page.evaluate('window.lastFormat') == 'mp3'
    assert page.evaluate('window.lastRange') == [None,None]
    page.click('#install-update')
    page.wait_for_function("document.querySelector('#status').textContent === 'Falha de atualização simulada'")
    assert page.locator('#download').is_enabled()
    page.evaluate("window.updateMode = 'latest'")
    page.click('#check-update')
    page.wait_for_selector('#update-dialog[open]')
    assert page.locator('#update-dialog-title').inner_text() == 'O Kupo já está atualizado!'
    assert page.locator('#update-dialog-version').inner_text() == 'VERSÃO 0.3.8'
    expect(page.locator('#update-dialog-confirm')).to_be_focused()
    assert page.locator('#update-banner').is_hidden()
    page.screenshot(path=os.environ.get('KUPOTUBE_MODAL_SCREENSHOT','/tmp/kupotube-update-modal.png')) if sys.platform != 'win32' else None
    page.keyboard.press('Escape')
    assert not page.locator('#update-dialog').is_visible()
    # Native dialog close events are queued; Edge may return from Escape first.
    expect(page.locator('#check-update')).to_be_focused()
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
    page.locator('.session-options summary').click()
    page.click('#cookies-help')
    expect(page.locator('#cookies-dialog')).to_be_visible()
    assert page.locator('#cookies-dialog').bounding_box()['height'] <= 750 - 47
    page.locator('#cookies-dialog .dialog-confirm').click()
    expect(page.locator('#cookies-dialog')).not_to_be_visible()
    for width, height in [(360, 650), (580, 650), (800, 700), (1280, 900), (1920, 1080)]:
        page.set_viewport_size({'width':width,'height':height})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        box = page.locator('main').bounding_box()
        assert abs(box['x'] + box['width'] / 2 - page.evaluate('document.documentElement.clientWidth') / 2) < 1
        assert box['width'] <= 1120
        page.click('#edit-selection')
        expect(page.locator('#selection-dialog')).to_be_visible()
        assert page.locator('#selection-dialog').bounding_box()['height'] <= height - 39
        page.keyboard.press('Escape')
        page.click('#release-news')
        dialog = page.locator('#releases-dialog')
        expect(dialog).to_be_visible()
        box = dialog.bounding_box()
        assert box['x'] >= 0 and box['y'] >= 0 and box['height'] <= height - 39, (width, box)
        assert dialog.evaluate('e => e.scrollWidth <= e.clientWidth'), width
        page.keyboard.press('Escape')
        expect(page.locator('#release-news')).to_be_focused()
    page.set_viewport_size({'width':1280,'height':900})
    page.evaluate('window.scrollTo(0,0)')
    if sys.platform != 'win32': page.screenshot(path='/tmp/kupotube-034.png', full_page=True)
    assert page.locator('img').evaluate_all('(images) => images.every(i => i.complete && i.naturalWidth > 0)')
    # A previous MP3 choice must not silently carry over to a new video.
    page.click('#clear-result')
    expect(page.locator('#result')).to_be_hidden()
    expect(page.locator('#progress')).to_be_hidden()
    expect(page.locator('#reveal-download')).to_be_hidden()
    expect(page.locator('#url')).to_have_value('')
    expect(page.locator('#url')).to_be_focused()
    assert page.locator('#status').inner_text() == ''
    page.fill('#url','https://youtu.be/another')
    assert page.locator('#container').input_value() == 'mp4'
    page.fill('#url','')
    page.locator('.intro').click()
    page.wait_for_function("document.querySelector('#url').placeholder !== 'Cole o link do vídeo aqui…'")
    page.locator('#url').focus()
    expect(page.locator('#url')).to_have_attribute('placeholder','Cole o link do vídeo aqui…')
    page.emulate_media(reduced_motion='reduce')
    page.locator('.session-options summary').click()
    assert not page.locator('.session-options').evaluate('e => e.open')
    page.locator('.session-options summary').click()
    assert page.locator('.session-options').evaluate('e => e.open')
    page.click('#release-news')
    assert page.locator('#releases-dialog').evaluate('e => getComputedStyle(e).animationName') == 'none'
    page.keyboard.press('Escape')
    page.locator('.intro').click()
    page.wait_for_timeout(2400)
    expect(page.locator('#url')).to_have_attribute('placeholder','Cole o link do vídeo aqui…')
    assert not errors, errors
    print('UI passed: cookie tutorial, focus/Escape, Macchiato scrollbar/footer, stable hover, responsive modal and download/update regressions')
    browser.close()
