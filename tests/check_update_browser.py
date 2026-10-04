"""Browser regression check; HTTP requests are intercepted, no real update runs.
Run: python tests/check_update_browser.py (requires playwright + Chromium).
"""
import json
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
from test_system_update import WebUpdateTests

WebUpdateTests.setUpClass()
case = WebUpdateTests()
case.setUp()
try:
    web = case.web
    release = dict(case.release, current='1.3.3', checked_at=1)
    with patch.object(web, '_github_release_status', return_value=release), \
         patch.object(web, '_system_update_status', return_value={'state': 'idle'}), \
         patch.object(web, '_host_action_blocked', return_value=None), \
         patch.object(web, 'active_server_info', return_value={}), \
         patch.object(web, 'available_server_versions', return_value=[]):
        html = case.client.get('/system/update').get_data(as_text=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors, posts = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def handle(route):
            path = route.request.url.split('update-test.invalid')[-1]
            if path.startswith('/api/update-check'):
                route.fulfill(json=release)
            elif path == '/system/update/start':
                posts.append(route.request.post_data)
                if len(posts) < 3:
                    route.fulfill(status=409, json={'requires_stop': True})
                else:
                    route.fulfill(status=202, json={'ok': True})
            elif path == '/api/system-update/status':
                route.fulfill(json={'state': 'working', 'percent': 10, 'phase': 'Test update',
                                    'logs': [{'time': '01:00', 'phase': 'Download'},
                                             {'time': '01:01', 'phase': 'Verify'}]})
            elif path.startswith('/system/update'):
                route.fulfill(content_type='text/html', body=html)
            else:
                route.fulfill(json={})
        page.route('**/*', handle)
        page.goto('http://update-test.invalid/system/update')
        expect(page.locator('.sidebar-update-label')).to_contain_text('1.3.5')
        # Cancel password: no POST.
        page.locator('#startWebUpdate').click()
        expect(page.locator('#jxDialogInput')).to_have_attribute('type', 'password')
        page.locator('#jxDialogCancel').click()
        assert not posts
        # Cancel Stop All: restore enabled button without a spurious error.
        page.locator('#startWebUpdate').click()
        page.locator('#jxDialogInput').fill('test-only')
        page.locator('#jxDialogConfirm').click()
        expect(page.locator('#jxDialogMessage')).to_contain_text('Stop All')
        page.locator('#jxDialogCancel').click()
        expect(page.locator('#startWebUpdate')).to_be_enabled()
        expect(page.locator('#updateError')).to_have_text('')
        # Confirm: the second POST must carry stop_server=1; progress must render.
        page.locator('#startWebUpdate').click()
        page.locator('#jxDialogInput').fill('test-only')
        page.locator('#jxDialogConfirm').click()
        expect(page.locator('#jxDialogMessage')).to_contain_text('Stop All')
        page.locator('#jxDialogConfirm').click()
        expect(page.locator('#updatePhase')).to_have_text('Test update')
        expect(page.locator('#updateLog')).to_contain_text('[01:01] Verify')
        assert 'name="stop_server"\r\n\r\n1' in posts[-1]
        assert not errors, errors
        browser.close()
        print('Browser OK: latest version, password dialog, cancel, Stop All confirmation, POST and progress; no JavaScript errors.')
finally:
    case.doCleanups()
    WebUpdateTests.tearDownClass()
