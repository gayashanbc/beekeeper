import hmac
from hashlib import sha1
import json
import urllib


from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseServerError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from github3 import GitHub
from ipaddress import ip_address, ip_network

from github import hooks


@require_POST
@csrf_exempt
def webhook(request):
    # Verify if request came from GitHub
    forwarded_for = u'{}'.format(request.META.get('HTTP_X_FORWARDED_FOR'))
    client_ip_address = ip_address(forwarded_for)

    gh_session = GitHub(
            settings.GITHUB_USERNAME,
            password=settings.GITHUB_ACCESS_TOKEN
        )
    whitelist = gh_session.meta()['hooks']

    for valid_ip in whitelist:
        if client_ip_address in ip_network(valid_ip):
            break
    else:
        return HttpResponseForbidden('Permission denied.')

    # Verify the request signature
    header_signature = request.META.get('HTTP_X_HUB_SIGNATURE')
    if header_signature is None:
        return HttpResponseForbidden('Permission denied.')

    sha_name, signature = header_signature.split('=')
    if sha_name != 'sha1':
        return HttpResponseServerError('Operation not supported.', status=501)

    mac = hmac.new(
        settings.GITHUB_WEBHOOK_KEY.encode('utf-8'),
        msg=request.body,
        digestmod=sha1
    )
    if not hmac.compare_digest(mac.hexdigest().encode('utf-8'), signature.encode('utf-8')):
        return HttpResponseForbidden('Permission denied.')

    # Get the event type
    event = request.META.get('HTTP_X_GITHUB_EVENT', 'ping')

    # Decode the payload
    if request.content_type == 'application/x-www-form-urlencoded':
        # Remove the payload= prefix and URL unquote
        content = urllib.parse.unquote_plus(request.body.decode('utf-8'))
        payload = json.loads(content[8:])
    elif request.content_type == 'application/json':
        content = request.body.decode('utf-8')
        payload = json.loads(content)
    else:
        payload = None

    try:
        return HttpResponse(hooks[event](payload))
    except KeyError:
        # In case we receive an event that's not handled
        return HttpResponse(status=204)
