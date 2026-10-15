"""
WSGI to AWS Lambda / Netlify Functions adapter.
Translates API Gateway / Netlify Serverless events into standard WSGI environ
and translates WSGI responses back to serverless function responses.
Zero external dependencies.
"""
import base64
import io
import sys
import urllib.parse

BINARY_CONTENT_PREFIXES = (
    "image/",
    "application/zip",
    "application/octet-stream",
    "application/pdf",
    "application/vnd.",
    "audio/",
    "video/",
    "font/",
)


def is_binary(content_type: str) -> bool:
    if not content_type:
        return False
    ct = content_type.lower()
    return any(ct.startswith(prefix) for prefix in BINARY_CONTENT_PREFIXES)


def extract_method(event: dict) -> str:
    if "httpMethod" in event:
        return event["httpMethod"].upper()
    rc = event.get("requestContext", {})
    if "http" in rc and "method" in rc["http"]:
        return rc["http"]["method"].upper()
    return "GET"


def extract_path(event: dict) -> str:
    path = event.get("path") or event.get("rawPath") or "/"
    for prefix in ("/.netlify/functions/app", "/.netlify/functions/api"):
        if path.startswith(prefix):
            path = path[len(prefix):] or "/"
            break
    return path


def extract_query_string(event: dict) -> str:
    if event.get("rawQueryString"):
        return event["rawQueryString"]
    if event.get("multiValueQueryStringParameters"):
        pairs = []
        for k, vals in event["multiValueQueryStringParameters"].items():
            for v in (vals or []):
                pairs.append((k, v))
        return urllib.parse.urlencode(pairs)
    if event.get("queryStringParameters"):
        return urllib.parse.urlencode(
            [(k, v) for k, v in event["queryStringParameters"].items() if v is not None]
        )
    return ""


def handle_lambda(app, event: dict, context=None) -> dict:
    """Execute WSGI app for an incoming Lambda/Netlify event."""
    method = extract_method(event)
    path = extract_path(event)
    qs = extract_query_string(event)

    # Process body
    body_bytes = b""
    raw_body = event.get("body")
    if raw_body:
        if event.get("isBase64Encoded", False):
            body_bytes = base64.b64decode(raw_body)
        elif isinstance(raw_body, str):
            body_bytes = raw_body.encode("utf-8")
        elif isinstance(raw_body, (bytes, bytearray)):
            body_bytes = bytes(raw_body)

    # Headers
    raw_headers = event.get("headers") or {}
    server_name = raw_headers.get("host", raw_headers.get("Host", "localhost")).split(":")[0]
    proto = raw_headers.get("x-forwarded-proto", raw_headers.get("X-Forwarded-Proto", "https")).lower()
    port = raw_headers.get("x-forwarded-port", "443" if proto == "https" else "80")

    environ = {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": path,
        "QUERY_STRING": qs,
        "SERVER_NAME": server_name,
        "SERVER_PORT": str(port),
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": proto,
        "wsgi.input": io.BytesIO(body_bytes),
        "wsgi.errors": sys.stderr,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "CONTENT_LENGTH": str(len(body_bytes)),
    }

    # Add HTTP headers
    for k, v in raw_headers.items():
        if not v:
            continue
        k_upper = k.upper().replace("-", "_")
        if k_upper == "CONTENT_TYPE":
            environ["CONTENT_TYPE"] = v
        elif k_upper == "CONTENT_LENGTH":
            environ["CONTENT_LENGTH"] = v
        else:
            environ[f"HTTP_{k_upper}"] = v

    # Payload 2.0 cookies
    if "cookies" in event and "HTTP_COOKIE" not in environ:
        environ["HTTP_COOKIE"] = "; ".join(event["cookies"])

    # Response capture
    status_code = [200]
    response_headers = []

    def start_response(status, headers, exc_info=None):
        try:
            status_code[0] = int(status.split()[0])
        except Exception:
            status_code[0] = 200
        response_headers.extend(headers)

    response_iter = app(environ, start_response)
    chunks = []
    try:
        for chunk in response_iter:
            chunks.append(chunk)
    finally:
        if hasattr(response_iter, "close"):
            response_iter.close()

    resp_body_bytes = b"".join(chunks)

    # Format headers and detect content type
    out_headers = {}
    multi_headers = {}
    content_type = ""
    cookies = []

    for name, val in response_headers:
        n_low = name.lower()
        if n_low == "content-type":
            content_type = val
        if n_low == "set-cookie":
            cookies.append(val)
        multi_headers.setdefault(name, []).append(val)
        out_headers[name] = val

    # Determine if response body is binary
    binary = is_binary(content_type)
    if not binary:
        try:
            body_text = resp_body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            binary = True

    if binary:
        body_out = base64.b64encode(resp_body_bytes).decode("ascii")
        is_b64 = True
    else:
        body_out = resp_body_bytes.decode("utf-8", errors="replace")
        is_b64 = False

    result = {
        "statusCode": status_code[0],
        "headers": out_headers,
        "multiValueHeaders": multi_headers,
        "body": body_out,
        "isBase64Encoded": is_b64,
    }
    if cookies:
        result["cookies"] = cookies

    return result
