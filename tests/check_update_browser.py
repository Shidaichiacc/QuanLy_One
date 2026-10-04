"""Popup update regression: all HTTP mutations are intercepted, no real updater."""
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
from test_system_update import WebUpdateTests

WebUpdateTests.setUpClass()
case = WebUpdateTests()
case.setUp()
try:
    web = case.web
    release = dict(case.release, current='1.3.6', checked_at=1)
    with web.app.test_request_context('/'), \
         patch.object(web, '_host_action_blocked', return_value=None), \
         patch.object(web, 'active_server_info', return_value={}), \
         patch.object(web, 'available_server_versions', return_value=[]):
        html = web.page('<h1>Bảng điều khiển</h1>', manager_csrf='fixture-csrf')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width':1280,'height':800})
        page = context.new_page()
        errors, posts = [], []
        phase = 'idle'
        fail_start = False
        page.on('pageerror', lambda error: errors.append(str(error)))
        def handle(route):
            path = route.request.url.split('update-test.invalid')[-1]
            if path.startswith('/api/update-check'):
                route.fulfill(json=release)
            elif path == '/system/update/start':
                global phase
                posts.append(route.request.post_data)
                assert 'admin_password' not in posts[-1]
                assert 'name="stop_server"\r\n\r\n1' in posts[-1]
                assert 'fixture-csrf' in posts[-1]
                if fail_start:
                    route.fulfill(status=409,json={'error':'Một lượt backup đang chạy'})
                else:
                    phase='working'
                    route.fulfill(status=202,json={'ok':True})
            elif path == '/api/system-update/status':
                if phase == 'disconnected':
                    route.fulfill(status=502,body='Restarting')
                elif phase == 'idle':
                    # A stale success from the previously installed version must stay hidden.
                    route.fulfill(json={'state':'success','percent':100,'updated':100,'message':'Đã cài v1.3.6'})
                else:
                    route.fulfill(json={'state':phase,'percent':100 if phase=='success' else 45,'updated':200,
                                        'phase':'Đang tải gói','message':'SHA256 không khớp' if phase=='error' else 'Tiến trình kiểm thử'})
            elif path == '/system/update':
                route.fulfill(status=302,headers={'Location':'/?update=1'})
            elif path.startswith('/api/'):
                route.fulfill(json={})
            else:
                route.fulfill(content_type='text/html',body=html)
        page.route('**/*',handle)
        page.goto('http://update-test.invalid/')
        page.locator('#sidebarUpdate').click()
        expect(page.locator('#updateCenter')).to_be_enabled()
        expect(page.locator('#updatePopupProgress')).not_to_be_visible()
        assert not posts
        page.locator('#updateCenter').click()
        expect(page.locator('#updatePopupPercent')).to_have_text('45%')
        assert page.url == 'http://update-test.invalid/'
        expect(page.locator('#jxDialogInput')).not_to_be_visible()
        assert len(posts)==1
        # Hiding and reopening does not create another update request.
        page.locator('#updatePopupClose').click()
        page.locator('#sidebarUpdate').click()
        expect(page.locator('#updatePopupPercent')).to_have_text('45%')
        assert len(posts)==1
        # Reload while the Web is restarting, recover without showing stale success.
        phase='disconnected'
        page.reload()
        page.locator('#sidebarUpdate').click()
        expect(page.locator('#updatePopupPhase')).to_have_text('Đang chờ Web kết nối lại')
        phase='working'
        expect(page.locator('#updatePopupPercent')).to_have_text('45%',timeout=10000)
        phase='success'
        expect(page.locator('#updateDialogTitle')).to_have_text('Cập nhật thành công',timeout=10000)
        expect(page.locator('#updatePopupPercent')).to_have_text('100%')
        expect(page.locator('#updateCenter')).to_have_text('Hoàn tất')
        assert len(posts)==1
        # Direct old link opens only this popup and never starts an update automatically.
        phase='idle'
        page.goto('http://update-test.invalid/?update=1')
        expect(page.locator('#updateDialog')).to_be_visible()
        expect(page.locator('#updatePopupProgress')).not_to_be_visible()
        assert len(posts)==1
        # Rejection and retry are visible in the same popup, without passwords.
        fail_start=True
        page.locator('#updateCenter').click()
        expect(page.locator('#updatePopupMessage')).to_have_text('Một lượt backup đang chạy')
        expect(page.locator('#updateCenter')).to_be_enabled()
        fail_start=False
        page.locator('#updateCenter').click()
        expect(page.locator('#updatePopupPercent')).to_have_text('45%')
        phase='error'
        expect(page.locator('#updatePopupMessage')).to_have_text('SHA256 không khớp',timeout=10000)
        expect(page.locator('#updateCenter')).to_be_enabled()
        # Compact layout fits a phone viewport.
        page.set_viewport_size({'width':390,'height':844})
        box=page.locator('#updateDialog').bounding_box()
        assert box and box['width']<=390 and box['height']<=844
        assert not errors,errors
        browser.close()
        print('Browser OK: popup-only/no password, one POST, hide/reopen/reload, reconnect, no stale success, 100%, failure/retry, mobile.')
finally:
    case.doCleanups()
    WebUpdateTests.tearDownClass()
