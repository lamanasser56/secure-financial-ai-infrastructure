"""Terraform operator credential: Application Default Credentials from the Cloud Shell metadata server (w6b).

Window-5 root cause: Terraform held one static GOOGLE_OAUTH_ACCESS_TOKEN that expired mid-apply. No token is passed now:
the Google provider and the GCS backend each resolve ADC to the metadata token source and refresh it themselves during
a long apply. adc_env() returns a child environment with every static or long-lived credential variable removed, and
refuses unless ADC resolves to the metadata server, no ADC key/refresh-token file exists, and the metadata identity is
the configured gcloud operator with cloud-platform scope. No token is printed, written or put in the child environment.

CLI: token_guard.py check   -> prints only {"result": "PASS", "credential_source": "metadata-adc", ...} or REFUSED

w19 laptop mode (user_adc_env; explicit, never auto-selected): no metadata server exists on the laptop, so Terraform uses
the owner's user ADC file written by `gcloud auth application-default login`. That file holds a refresh token, so the
provider and backend refresh their own access tokens during a long apply (same window-5 property as metadata ADC).
Refused unless: no GCE_METADATA_HOST; the default ADC file is a private regular file of type authorized_user (no service
account key, external account or impersonation); its quota project is absent or the project; and a fresh ADC token is
the configured gcloud operator with cloud-platform scope. The token stays in memory for tokeninfo only.
CLI: token_guard.py check-laptop -> prints only {"result": "PASS", "credential_source": "user-adc-laptop", ...} or REFUSED
"""
import json, os, pathlib, stat, subprocess, sys, urllib.error, urllib.parse, urllib.request

TOKENINFO = 'https://oauth2.googleapis.com/tokeninfo'
CLOUD_PLATFORM = 'https://www.googleapis.com/auth/cloud-platform'
# Variables that would make the provider/backend use a static token, key file or impersonation instead of ADC.
STRIP = ('GOOGLE_OAUTH_ACCESS_TOKEN', 'GOOGLE_CREDENTIALS', 'GOOGLE_CLOUD_KEYFILE_JSON', 'GCLOUD_KEYFILE_JSON',
         'GOOGLE_APPLICATION_CREDENTIALS', 'GOOGLE_IMPERSONATE_SERVICE_ACCOUNT', 'CLOUDSDK_AUTH_ACCESS_TOKEN_FILE')


class CredentialRefused(Exception):
    pass


_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def metadata(path, environ):
    request = urllib.request.Request('http://%s/computeMetadata/v1/instance/service-accounts/default/%s'
                                     % (environ['GCE_METADATA_HOST'], path), headers={'Metadata-Flavor': 'Google'})
    return _opener.open(request, timeout=10).read().decode()


def tokeninfo(token):
    data = urllib.parse.urlencode({'access_token': token}).encode()
    try:
        return json.loads(_opener.open(urllib.request.Request(TOKENINFO, data=data, method='POST'), timeout=15).read())
    except urllib.error.HTTPError:
        return {}


def gcloud_account():
    return subprocess.run(['gcloud', 'config', 'get-value', 'account'], capture_output=True, text=True, timeout=30).stdout.strip()


def adc_env(environ=None, *, home=None, md=metadata, info=tokeninfo, account=gcloud_account):
    """Child environment that makes Terraform use refreshing metadata ADC, or refuse."""
    environ = dict(os.environ if environ is None else environ)
    if not environ.get('GCE_METADATA_HOST'):
        raise CredentialRefused('ADC_METADATA_UNAVAILABLE')
    config = pathlib.Path(environ.get('CLOUDSDK_CONFIG') or pathlib.Path(home or pathlib.Path.home()) / '.config/gcloud')
    if (config / 'application_default_credentials.json').exists():
        raise CredentialRefused('ADC_FILE_PRESENT')  # a key or refresh-token file would take precedence over metadata
    try:
        email = md('email', environ).strip()
        details = info(json.loads(md('token', environ))['access_token'])
    except Exception:
        raise CredentialRefused('ADC_METADATA_UNAVAILABLE') from None
    operator = account()
    if not operator or email != operator or details.get('email') != operator:
        raise CredentialRefused('ADC_IDENTITY_MISMATCH')
    if CLOUD_PLATFORM not in details.get('scope', '').split() or int(details.get('expires_in', 0)) <= 0:
        raise CredentialRefused('ADC_TOKEN_INVALID')
    for name in STRIP:
        environ.pop(name, None)
    return environ


PROJECT = os.environ.get('AGENT_PLATFORM_PROJECT_ID')  # set by lifecycle.py from private settings; never committed
ADC_FILE = 'application_default_credentials.json'


def user_adc_token(environ):
    """Fresh access token from the user ADC file (gcloud refreshes it); kept in memory, never printed."""
    result = subprocess.run(['gcloud', 'auth', 'application-default', 'print-access-token'], env=environ,
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not result.stdout.strip():
        raise CredentialRefused('ADC_TOKEN_UNAVAILABLE')
    return result.stdout.strip()


def user_adc_access_token(environ=None):
    """w19 laptop (R2): one fresh user ADC access token for a single API call (adc.py, c_egress, c-preflight, subject tools).
    Refused on a metadata host; static-credential variables never reach gcloud. Never printed or stored."""
    environ = dict(os.environ if environ is None else environ)
    if environ.get('GCE_METADATA_HOST'):
        raise CredentialRefused('LAPTOP_MODE_ON_METADATA_HOST')
    for name in STRIP:
        environ.pop(name, None)
    return user_adc_token(environ)


def user_adc_env(environ=None, *, home=None, info=tokeninfo, account=gcloud_account, adc_token=user_adc_token):
    """w19 laptop: child environment that makes Terraform use the refreshing user ADC file, or refuse."""
    environ = dict(os.environ if environ is None else environ)
    if environ.get('GCE_METADATA_HOST'):
        raise CredentialRefused('LAPTOP_MODE_ON_METADATA_HOST')
    for name in STRIP:  # first: GOOGLE_APPLICATION_CREDENTIALS must not redirect ADC away from the checked file
        environ.pop(name, None)
    config = pathlib.Path(environ.get('CLOUDSDK_CONFIG') or pathlib.Path(home or pathlib.Path.home()) / '.config/gcloud')
    path = config / ADC_FILE
    try:
        st = path.lstat()
    except OSError:
        raise CredentialRefused('ADC_FILE_MISSING') from None
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CredentialRefused('ADC_FILE_NOT_PRIVATE')
    try:
        adc = json.loads(path.read_text())
    except Exception:
        raise CredentialRefused('ADC_FILE_UNREADABLE') from None
    if (not isinstance(adc, dict) or adc.get('type') != 'authorized_user' or not adc.get('refresh_token')
            or any(k in adc for k in ('service_account_impersonation_url', 'source_credentials', 'credential_source', 'private_key'))):
        raise CredentialRefused('ADC_NOT_USER')
    if adc.get('quota_project_id') not in (None, PROJECT):
        raise CredentialRefused('ADC_QUOTA_PROJECT')
    try:
        details = info(adc_token(environ))
    except CredentialRefused:
        raise
    except Exception:
        raise CredentialRefused('ADC_TOKEN_UNAVAILABLE') from None
    operator = account()
    if not operator or details.get('email') != operator:
        raise CredentialRefused('ADC_IDENTITY_MISMATCH')
    if CLOUD_PLATFORM not in details.get('scope', '').split() or int(details.get('expires_in', 0)) <= 0:
        raise CredentialRefused('ADC_TOKEN_INVALID')
    return environ


if __name__ == '__main__':
    try:
        assert sys.argv[1:] in (['check'], ['check-laptop'])
        laptop = sys.argv[1:] == ['check-laptop']
        child = user_adc_env() if laptop else adc_env()
        print(json.dumps({'result': 'PASS', 'credential_source': 'user-adc-laptop' if laptop else 'metadata-adc',
                          'static_credential_variables': [n for n in STRIP if n in child]}))
    except CredentialRefused as error:
        print(json.dumps({'result': 'REFUSED', 'code': str(error)})); raise SystemExit(1)
