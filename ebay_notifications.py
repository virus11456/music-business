"""eBay Marketplace Account Deletion notifications, required before an eBay production keyset is enabled.

This service stores no eBay user data (only listing titles, prices and links), so a deletion notice needs no
action beyond acknowledging it. The endpoint only answers eBay's ownership challenge and acknowledges notices."""
import hashlib
import json
import os
import re

def configured():
    """(verification token, registered endpoint URL) or None when the endpoint is not set up."""
    token = os.getenv('EBAY_VERIFICATION_TOKEN', '').strip()
    endpoint = os.getenv('EBAY_DELETION_ENDPOINT', '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,80}', token) or not endpoint.startswith('https://'):
        return None
    return token, endpoint

def challenge_response(challenge_code, token, endpoint):
    # eBay's order: challenge code, then verification token, then the endpoint URL exactly as registered.
    return json.dumps({'challengeResponse': hashlib.sha256((challenge_code + token + endpoint).encode()).hexdigest()})
