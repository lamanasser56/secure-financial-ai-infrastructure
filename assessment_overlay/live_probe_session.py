"""R01: real synthetic Financial session, CSRF, Host, and row isolation."""
import json
from pathlib import Path
import re

from live_probe_kube import one_pod, python_probe


R01 = r'''
import http.cookiejar, json, urllib.error, urllib.request
USERS = __USERS__
RUN = '__RUN__'
BASE = 'http://127.0.0.1:8081'
MONTH = '2026-10'
def send(opener, method, path, body=None, *, origin=BASE, csrf=None, host=None, cookie=None):
    headers = {'Host':host or '127.0.0.1:8081'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
        if origin is not None:
            headers['Origin'] = origin
    if csrf is not None:
        headers['X-CSRF'] = csrf
    if cookie is not None:
        headers['Cookie'] = cookie
    request = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                     headers=headers, method=method)
    try:
        with opener.open(request, timeout=8) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None
checks = {}
plain = urllib.request.build_opener()
checks['unauthenticated_denied'] = send(plain, 'GET', '/api/me')[0] == 401
checks['forged_host_denied'] = send(plain, 'GET', '/api/me', host='forged.invalid')[0] == 403
checks['wrong_password_denied'] = send(plain, 'POST', '/api/login',
    {'username':'assessment_unknown','password':'wrong'})[0] == 401
markers, sessions = {}, {}
for username in ('lama','sara'):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    sessions[username] = opener
    code, identity = send(opener, 'POST', '/api/login',
                          {'username':username, 'password':USERS[username]})
    checks[username + '_login'] = code == 200 and isinstance(identity.get('csrf'), str)
    csrf = identity['csrf']
    cookie = next(item.value for item in jar if item.name == 'fa_session')
    if username == 'lama':
        changed = cookie[:-1] + ('a' if cookie[-1] != 'a' else 'b')
        checks['tampered_cookie_denied'] = send(plain, 'GET', '/api/me',
                                                cookie='fa_session=' + changed)[0] == 401
    marker = 'Assessment-' + RUN + '-' + username
    markers[username] = marker
    expense = {'spent_on':'2026-10-26', 'merchant':marker, 'category':'food',
               'amount':'1.00', 'note':'synthetic assessment'}
    checks[username + '_missing_csrf_denied'] = send(opener, 'POST', '/api/expenses', expense)[0] == 403
    checks[username + '_bad_origin_denied'] = send(opener, 'POST', '/api/expenses', expense,
                                                    origin='http://forged.invalid', csrf=csrf)[0] == 403
    checks[username + '_create'] = send(opener, 'POST', '/api/expenses', expense, csrf=csrf)[0] == 201
    code, value = send(opener, 'GET', '/api/expenses?month=' + MONTH)
    checks[username + '_list'] = code == 200 and isinstance(value.get('expenses'), list)
    merchants = [row['merchant'] for row in value['expenses']]
    checks[username + '_own_seen'] = marker in merchants
    checks[username + '_other_absent'] = ('Assessment-' + RUN + '-'
                                          + ('sara' if username == 'lama' else 'lama')) not in merchants
for username in ('lama','sara'):
    code, value = send(sessions[username], 'GET', '/api/expenses?month=' + MONTH)
    merchants = [row['merchant'] for row in value['expenses']] if code == 200 else []
    other = 'sara' if username == 'lama' else 'lama'
    checks[username + '_cross_user_isolation'] = markers[username] in merchants and markers[other] not in merchants
print(json.dumps(checks))
'''


def probe_r01(kubeconfig, run_dir, run_id, *, executable='kubectl', pod=one_pod,
              execute=python_probe):
    if not re.fullmatch(r'assess-[0-9a-f]{16}', run_id):
        raise ValueError('assessment:invalid_run_id')
    users = json.loads((Path(run_dir) / 'financial-users.json').read_text())
    if (set(users) != {'lama', 'sara', 'omar'}
            or any(type(value) is not str or not 8 <= len(value) <= 128 for value in users.values())):
        raise ValueError('assessment:synthetic_user_credentials_invalid')
    name = pod(kubeconfig, 'apps', 'app.kubernetes.io/name=financial-frontdoor', executable=executable)
    script = R01.replace('__USERS__', repr(users)).replace('__RUN__', run_id)
    return execute(kubeconfig, 'apps', name, script, executable=executable)
