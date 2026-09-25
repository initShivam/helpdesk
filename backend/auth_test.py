import sys, json
import requests

BASE = 'http://localhost:8000'
session = requests.Session()

def print_result(step, resp):
    print(f'--- {step} ---')
    print('Status:', resp.status_code)
    try:
        print('JSON:', resp.json())
    except Exception:
        print('Text:', resp.text)
    # cookies
    print('Cookies:', session.cookies.get_dict())
    print()

# 1. Unauthenticated GET /api/auth/me/
resp = session.get(f'{BASE}/api/auth/me/', timeout=5)
print_result('Unauthenticated GET /api/auth/me/', resp)

# extract CSRF token (may be set in cookie 'csrftoken')
csrf = session.cookies.get('csrftoken', '')
print('CSRF token after GET:', csrf)

# 2. Valid login
login_payload = {'username': 'testuser', 'password': 'testpass'}
headers = {'X-CSRFToken': csrf, 'Content-Type': 'application/json'}
resp = session.post(f'{BASE}/api/auth/login/', json=login_payload, headers=headers, timeout=5)
print_result('Login POST', resp)

# 3. Check session cookie exists (sessionid)
print('SessionID cookie after login:', session.cookies.get('sessionid'))

# 4. Refresh: GET /api/auth/me/ again
resp = session.get(f'{BASE}/api/auth/me/', timeout=5)
print_result('Authenticated GET /api/auth/me/', resp)

# 5. Invalid login attempt
invalid_payload = {'username': 'testuser', 'password': 'wrongpass'}
# get fresh CSRF token (maybe same)
csrf = session.cookies.get('csrftoken', '')
headers = {'X-CSRFToken': csrf, 'Content-Type': 'application/json'}
resp = session.post(f'{BASE}/api/auth/login/', json=invalid_payload, headers=headers, timeout=5)
print_result('Invalid login POST', resp)

# 6. Logout
csrf = session.cookies.get('csrftoken', '')
headers = {'X-CSRFToken': csrf}
resp = session.post(f'{BASE}/api/auth/logout/', headers=headers, timeout=5)
print_result('Logout POST', resp)

# 7. Verify session cleared: GET /api/auth/me/
resp = session.get(f'{BASE}/api/auth/me/', timeout=5)
print_result('GET /api/auth/me/ after logout', resp)

sys.exit(0)
