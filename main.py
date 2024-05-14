#!/usr/bin/env python3
"""
This script can be called by using a command line like e.g.

/path/to/main.py 100 3cxPassword 012345678
"""

import sys
import ssl
from os import environ

import requests
from requests.sessions import RequestsCookieJar
from websocket import create_connection

EXTENSION = sys.argv[1]
PASSWORD = sys.argv[2]
NUMBER_DIRTY = sys.argv[3].strip().replace("+", "00")
NUMBER = "".join([s for s in list(NUMBER_DIRTY) if s.isdigit()])

VERIFY_SSL = True

PBX_URL = environ.get("PBX_URL", "my3cxinstallation.my3cx.de")


def do_login(username: str, password: str) -> (str, str, dict, str):
    # Get login cookie
    request = requests.post(
        f"https://{PBX_URL}/webclient/api/Login/GetAccessToken",
        verify=VERIFY_SSL,
        json={"Password": password, "Username": username},
    )
    if not request.status_code == 200:
        raise ValueError(f"Failed to login. {request.status_code}")
    cookies = request.cookies
    # connect token
    request = requests.post(
        f"https://{PBX_URL}/connect/token",
        cookies=request.cookies,
        verify=VERIFY_SSL,
        data={"client_id": "Webclient", "grant_type": "refresh_token"},
    )
    bearer_token = request.json()["access_token"]

    if not request.status_code == 200:
        raise ValueError(f"Failed to login. {request.status_code}")
    request = requests.post(
        f"https://{PBX_URL}/webclient/api/MyPhone/session",
        headers={"Authorization": f"Bearer {bearer_token}"},
        cookies=cookies,
        verify=VERIFY_SSL,
        json={"name": "Webclient", "version": "nope", "isHuman": True},
    )
    if not request.status_code == 200:
        raise ValueError(f"Failed to get phone session {request.status_code}")
    session_key = request.json()["sessionKey"]
    pass_val = request.json()["pass"]

    return session_key, bearer_token, cookies, pass_val


def get_phone_config(ws_pass: str, current_session_key: str, cookies: RequestsCookieJar) -> str:
    """
    This function opens a websocket to the 3cx server and queries the current
    phone configuration to get the phones ip, port and the line identifier
    """

    websocket = create_connection(
        f"wss://{PBX_URL}/ws/webclient?sessionId={current_session_key}&pass={ws_pass}",
        sslopt={"cert_reqs": ssl.CERT_NONE},
    )

    result = websocket.recv()
    if not result == "START":
        raise ValueError(f"Did not receive expected START from ws: {result}")

    # These are some magic byte sequences that query "stuff" including the
    # current phone config (port, line, etc.)
    magic_byte_set = [
        b"\x08z\xd2\x07\x00",
        b"\x08f\xb2\x06\x00",
        b"\x08\x83\x01\x9a\x08\x00",
        b"\x08\xf4\x03\xa2\x1f\x00",
        b"\x08h\xc2\x06\x0e\x10\x00\x18\x01 \x00@\x00H\x00P\x00X ",
        b"\x08\x80\x01\x82\x08\x02\x08\x04",
        b"\x08\xa5\x01\xaa\n\x00",
    ]

    # Send all byte sequences to the server via POST...
    for magic_bytes in magic_byte_set:
        post_request = requests.post(
            f"https://{PBX_URL}/MyPhone/MPWebService.asmx",
            data=magic_bytes,
            verify=VERIFY_SSL,
            cookies=cookies,
            headers={
                "content-type": "application/octet-stream",
                "myphonesession": current_session_key,
            },
        )
        if not post_request.status_code == 200:
            raise ValueError("Failed to send byte sequence")

    # ... and receive the result via the websocket
    while True:
        result = websocket.recv()
        # Sometimes the result is a string, sometimes it isn't...
        if isinstance(result, str):
            continue
        # Obviously, this is the identifier for announcing the phone
        # configuration
        if result.startswith(b"\x08\xc9\x01\xca\x0c"):
            sip_bytes = result
            break
    websocket.close()
    phone_config_local = None
    for part in sip_bytes.split(b"\x1a"):
        if part.startswith(b"(sip:"):
            phone_config_local = part.split(b'"')[0]
    if not phone_config_local:
        raise ValueError("Failed to get phone config")
    return phone_config_local.decode()


#########################################################################
# Querying the config part
#########################################################################


# Get phone session id
# Actually, this json can be empty...
session_key, bearer_token, cookies, pass_val = do_login(EXTENSION, PASSWORD)

# Initiate the connection to query phone configuration
phone_config = get_phone_config(pass_val, session_key, cookies)

#########################################################################
# Call part
#########################################################################

# No idea why we need to log in a second time
session_key, bearer_token, cookies, pass_val = do_login(EXTENSION, PASSWORD)

# This second part of the body contains the actual number and phone information
# The first byte of this sequence must be \n, the second byte is the length of
# the phone number. After that, there is the number followed by 0x1a,
# indicating the end of the number. Then, there is the definition of the actual
# phone location and line number
body_part_two = "\n" + bytes([len(NUMBER)]).decode() + f"{NUMBER}\x1a{phone_config}"

# The first part seems to be a header, starting with 0x08 0x77 0xba 0x07. After
# that, there is a byte representing the length of the following body_part_two.
# Actually, b'\x08w\xba\x07' also works...
body_part_one = b"\x08\x77\xba\x07" + bytes([len(body_part_two)])

request = requests.post(
    f"https://{PBX_URL}/MyPhone/MPWebService.asmx",
    data=(body_part_one + body_part_two.encode()),
    headers={
        "content-type": "application/octet-stream",
        "myphonesession": session_key,
        "Authorization": f"Bearer {bearer_token}",
    },
    verify=VERIFY_SSL,
    cookies=cookies,
)
if not request.status_code == 200:
    raise ValueError(f"Failed to call number {request.status_code}")
