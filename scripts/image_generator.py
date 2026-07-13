import base64
import json
import os
import tempfile
import time
import hashlib
import hmac
import uuid
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qsl, urlsplit

import requests


DOUBAO_PROVIDER_MODELS = {
    "doubao_seedream_5_lite": "doubao-seedream-5-0-260128",
    "doubao_seedream_4_5": "doubao-seedream-4-5-251128",
    "doubao_seedream_4_0": "doubao-seedream-4-0-250828",
}


def is_image_generation_enabled():
    return os.getenv("IMAGE_GEN_ENABLED", "false").strip().lower() in ["1", "true", "yes"]


def _get_ext_from_url(url):
    try:
        path = urlparse(url).path or ""
        ext = os.path.splitext(path)[1].lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            return ext
    except Exception:
        pass
    return ".png"


def _write_bytes_file(data, ext):
    os.makedirs("temp/generated_images", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join("temp/generated_images", f"img_{ts}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def _cache_dir_for(prompt, n, size, req_key, base_url):
    h = hashlib.sha256()
    h.update(str(req_key or "").encode("utf-8"))
    h.update(b"\n")
    h.update(str(size or "").encode("utf-8"))
    h.update(b"\n")
    h.update(str(base_url or "").encode("utf-8"))
    h.update(b"\n")
    h.update(str(prompt or "").encode("utf-8"))
    key = h.hexdigest()[:32]
    return os.path.join("temp", "jimeng_cache", key), key


def _read_cache(prompt, n, size, req_key, base_url):
    cache_root, _ = _cache_dir_for(prompt, n, size, req_key, base_url)
    if not os.path.isdir(cache_root):
        return None
    paths = []
    for i in range(1, n + 1):
        p = os.path.join(cache_root, f"img_{i}.png")
        if os.path.exists(p):
            paths.append(p)
    if len(paths) >= n:
        return paths[:n]
    return None


def _write_cache(prompt, n, size, req_key, base_url, paths):
    cache_root, _ = _cache_dir_for(prompt, n, size, req_key, base_url)
    os.makedirs(cache_root, exist_ok=True)
    out = []
    for i, p in enumerate(paths[:n], start=1):
        target = os.path.join(cache_root, f"img_{i}.png")
        try:
            if os.path.exists(target):
                out.append(target)
                continue
            with open(p, "rb") as fsrc:
                data = fsrc.read()
            with open(target, "wb") as fdst:
                fdst.write(data)
            out.append(target)
        except Exception:
            continue
    return out


def _download_image(url, timeout=60):
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return _write_bytes_file(resp.content, _get_ext_from_url(url))


def _build_headers(api_key):
    headers = {"Content-Type": "application/json"}
    custom_name = os.getenv("JIMENG_AUTH_HEADER_NAME", "").strip()
    custom_value = os.getenv("JIMENG_AUTH_HEADER_VALUE", "").strip()
    if custom_name and custom_value:
        headers[custom_name] = custom_value
        return headers

    use_bearer = os.getenv("JIMENG_USE_BEARER", "true").strip().lower() in ["1", "true", "yes"]
    if use_bearer:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["X-Api-Key"] = api_key
    return headers


def _hmac_sha256(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(s):
    if isinstance(s, bytes):
        data = s
    else:
        data = str(s).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _build_canonical_query(url):
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    pairs.sort(key=lambda x: (x[0], x[1]))
    return "&".join(
        f"{quote(str(k), safe='-_.~')}={quote(str(v), safe='-_.~')}" for k, v in pairs
    )


def _sign_headers_v4(method, url, body, ak, sk, use_volc_prefix=True, include_content_type=True):
    service = os.getenv("JIMENG_SIGN_SERVICE", "cv").strip()
    region = os.getenv("JIMENG_SIGN_REGION", "cn-north-1").strip()
    now = datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    parsed = urlsplit(url)
    host = parsed.netloc
    canonical_uri = parsed.path or "/"
    canonical_query = _build_canonical_query(url)
    payload_hash = _sha256_hex(body)

    headers_lower = {"host": host, "x-date": amz_date, "x-content-sha256": payload_hash}
    if include_content_type:
        headers_lower["content-type"] = "application/json"
    if os.getenv("JIMENG_SESSION_TOKEN", "").strip():
        headers_lower["x-security-token"] = os.getenv("JIMENG_SESSION_TOKEN", "").strip()

    signed_headers = ";".join(sorted(headers_lower.keys()))
    canonical_headers = "".join(f"{k}:{headers_lower[k]}\n" for k in sorted(headers_lower.keys()))

    canonical_request = "\n".join(
        [method.upper(), canonical_uri, canonical_query, canonical_headers, signed_headers, payload_hash]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/request"
    string_to_sign = "\n".join(
        ["HMAC-SHA256", amz_date, credential_scope, _sha256_hex(canonical_request)]
    )

    seed = ("VOLC" + sk) if use_volc_prefix else sk
    k_date = _hmac_sha256(seed.encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"request", hashlib.sha256).digest()
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth = (
        "HMAC-SHA256 "
        f"Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    out = {
        "Authorization": auth,
        "X-Date": amz_date,
        "X-Content-Sha256": payload_hash,
        "Host": host,
        "Content-Type": "application/json",
    }
    if "x-security-token" in headers_lower:
        out["X-Security-Token"] = headers_lower["x-security-token"]
    return out


def _extract_images_from_payload(data):
    items = data.get("data", [])
    if isinstance(items, list) and items:
        return items

    parsed = []
    d = data.get("data", {})
    if isinstance(d, dict):
        if isinstance(d.get("image_urls"), list):
            parsed = [{"url": u} for u in d.get("image_urls", [])]
        elif isinstance(d.get("binary_data_base64"), list):
            parsed = [{"b64_json": b} for b in d.get("binary_data_base64", [])]
    if not parsed and isinstance(data.get("result"), dict):
        r = data.get("result", {})
        if isinstance(r.get("image_urls"), list):
            parsed = [{"url": u} for u in r.get("image_urls", [])]
        elif isinstance(r.get("binary_data_base64"), list):
            parsed = [{"b64_json": b} for b in r.get("binary_data_base64", [])]
    return parsed


def _extract_task_id(data):
    for path in [
        ("data", "task_id"),
        ("data", "id"),
        ("result", "task_id"),
        ("result", "id"),
        ("task_id",),
        ("id",),
    ]:
        cur = data
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur[k]
        if ok and cur:
            return str(cur)
    return None


def _generate_openai_images(url, api_key, model, prompt, n, size, cache_key_prefix="sf"):
    """Standard OpenAI-compatible /v1/images/generations (SiliconFlow, etc.)"""
    cache_enabled = os.getenv("IMAGE_CACHE_ENABLED", "true").strip().lower() in ["1", "true", "yes"]
    if cache_enabled:
        h = hashlib.sha256()
        h.update(cache_key_prefix.encode())
        h.update(b"\n")
        h.update(prompt.encode("utf-8"))
        h.update(b"\n")
        h.update(str(n).encode())
        h.update(b"\n")
        h.update(size.encode())
        key = h.hexdigest()[:32]
        cache_path = os.path.join("temp", "jimeng_cache", key)
        if os.path.exists(cache_path):
            paths = [os.path.join(cache_path, f"img_{i}.png") for i in range(1, n + 1)
                     if os.path.exists(os.path.join(cache_path, f"img_{i}.png"))]
            if len(paths) == n:
                return paths

    payload = {"model": model, "prompt": prompt, "n": n, "size": size}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    try:
        data = resp.json()
    except Exception:
        data = {"error": resp.text}
    if resp.status_code >= 400:
        raise RuntimeError(f"image generation http error: status={resp.status_code}, body={json.dumps(data, ensure_ascii=False)[:500]}")

    paths = []
    items = data.get("data", [])
    for item in items:
        img_url = item.get("url", "")
        b64 = item.get("b64_json", "")
        if img_url:
            paths.append(_download_image(img_url))
        elif b64:
            paths.append(_write_bytes_file(base64.b64decode(b64), ".png"))
    if not paths:
        raise RuntimeError(f"no image in response: {json.dumps(data, ensure_ascii=False)[:300]}")

    if cache_enabled and paths:
        try:
            os.makedirs(cache_path, exist_ok=True)
            for i, p in enumerate(paths, 1):
                dst = os.path.join(cache_path, f"img_{i}.png")
                if not os.path.exists(dst):
                    import shutil
                    shutil.copy2(p, dst)
        except Exception:
            pass

    return paths


def _liblib_signed_url(base_url, path, access_key, secret_key):
    timestamp = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    content = "&".join((path, timestamp, nonce))
    digest = hmac.new(secret_key.encode("utf-8"), content.encode("utf-8"), hashlib.sha1).digest()
    signature = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")
    sep = "&" if "?" in path else "?"
    signed_path = (
        f"{path}{sep}AccessKey={quote(access_key)}"
        f"&Signature={quote(signature)}"
        f"&Timestamp={quote(timestamp)}"
        f"&SignatureNonce={quote(nonce)}"
    )
    return f"{base_url.rstrip('/')}{signed_path}"


def _parse_size(size, default=(768, 1024)):
    try:
        w, h = str(size or "").lower().split("x", 1)
        return int(w), int(h)
    except Exception:
        return default


def _generate_liblib_images(base_url, access_key, secret_key, prompt, n, size):
    """LiblibAI x 星流 OpenAPI text2img/ultra."""
    cache_enabled = os.getenv("IMAGE_CACHE_ENABLED", "true").strip().lower() in ["1", "true", "yes"]
    req_key = os.getenv("LIBLIB_TEMPLATE_UUID", "5d7e67009b344550bc1aa6ccbfa1d7f4").strip()
    if cache_enabled:
        cached = _read_cache(prompt, n, size, f"liblib:{req_key}", base_url)
        if cached:
            return cached

    width, height = _parse_size(size)
    submit_path = os.getenv("LIBLIB_TEXT2IMG_PATH", "/api/generate/webui/text2img/ultra").strip()
    status_path = os.getenv("LIBLIB_STATUS_PATH", "/api/generate/webui/status").strip()
    steps = int(os.getenv("LIBLIB_STEPS", "30"))
    img_count = max(1, min(int(n or 1), 4))
    payload = {
        "templateUuid": req_key,
        "generateParams": {
            "prompt": prompt,
            "imageSize": {"width": width, "height": height},
            "imgCount": img_count,
            "steps": steps,
        },
    }
    if os.getenv("LIBLIB_PROMPT_MAGIC", "").strip():
        payload["generateParams"]["promptMagic"] = int(os.getenv("LIBLIB_PROMPT_MAGIC", "1"))

    submit_url = _liblib_signed_url(base_url, submit_path, access_key, secret_key)
    resp = requests.post(submit_url, headers={"Content-Type": "application/json"}, json=payload, timeout=120)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    if resp.status_code >= 400 or data.get("code") not in (None, 0):
        raise RuntimeError(f"liblib submit error: status={resp.status_code}, body={json.dumps(data, ensure_ascii=False)[:500]}")

    task_id = ((data.get("data") or {}).get("generateUuid")
               or data.get("generateUuid")
               or _extract_task_id(data))
    if not task_id:
        raise RuntimeError(f"liblib submit missing generateUuid: {json.dumps(data, ensure_ascii=False)[:500]}")

    poll_times = int(os.getenv("LIBLIB_POLL_TIMES", "40"))
    poll_interval = float(os.getenv("LIBLIB_POLL_INTERVAL_SEC", "3"))
    last_payload = None
    paths = []
    for _ in range(poll_times):
        status_url = _liblib_signed_url(base_url, status_path, access_key, secret_key)
        rr = requests.post(
            status_url,
            headers={"Content-Type": "application/json"},
            json={"generateUuid": task_id},
            timeout=60,
        )
        try:
            dd = rr.json()
        except Exception:
            dd = {"raw": rr.text}
        last_payload = dd
        if rr.status_code >= 400 or dd.get("code") not in (None, 0):
            raise RuntimeError(f"liblib poll error: status={rr.status_code}, body={json.dumps(dd, ensure_ascii=False)[:500]}")

        info = dd.get("data") if isinstance(dd.get("data"), dict) else dd
        status = info.get("generateStatus")
        images = info.get("images") if isinstance(info, dict) else []
        if images:
            for item in images[:img_count]:
                img_url = item.get("imageUrl") or item.get("url")
                if img_url:
                    paths.append(_download_image(img_url))
            if paths:
                break
        if status in [6, 7, -1, "failed", "error"]:
            raise RuntimeError(f"liblib generation failed: {json.dumps(dd, ensure_ascii=False)[:500]}")
        time.sleep(poll_interval)

    if not paths:
        raise RuntimeError(f"liblib generation timeout or empty response: {json.dumps(last_payload, ensure_ascii=False)[:500]}")

    if cache_enabled:
        cached_paths = _write_cache(prompt, img_count, size, f"liblib:{req_key}", base_url, paths)
        if len(cached_paths) >= img_count:
            return cached_paths[:img_count]
    return paths[:img_count]


def generate_images_from_prompt(prompt, n=2):
    """
    Generic OpenAI-compatible image generation.
    Supports SiliconFlow, Jimeng, and any /v1/images/generations endpoint.

    Environment:
      - IMAGE_API_KEY or JIMENG_API_KEY
      - IMAGE_BASE_URL or JIMENG_BASE_URL
      - IMAGE_MODEL or JIMENG_MODEL  (default depends on provider)
      - IMAGE_SIZE or JIMENG_IMAGE_SIZE (default: 768x1024)
      - IMAGE_PROVIDER: siliconflow | jimeng | liblib | doubao_* (default: jimeng)
    Returns local file paths.
    """
    provider = os.getenv("IMAGE_PROVIDER", "jimeng").strip().lower()

    if provider == "liblib":
        access_key = os.getenv("LIBLIB_ACCESS_KEY", "").strip()
        secret_key = os.getenv("LIBLIB_SECRET_KEY", "").strip()
        if not access_key or not secret_key:
            raise RuntimeError("LIBLIB_ACCESS_KEY / LIBLIB_SECRET_KEY 未设置")
        base = os.getenv("LIBLIB_BASE_URL", "https://openapi.liblibai.cloud").strip().rstrip("/")
        size = os.getenv("IMAGE_SIZE", "").strip() or os.getenv("LIBLIB_IMAGE_SIZE", "768x1024").strip()
        return _generate_liblib_images(base, access_key, secret_key, prompt, n, size)

    if provider == "doubao" or provider in DOUBAO_PROVIDER_MODELS:
        api_key = (
            os.getenv("DOUBAO_API_KEY", "").strip()
            or os.getenv("ARK_API_KEY", "").strip()
            or os.getenv("IMAGE_API_KEY", "").strip()
        )
        if not api_key:
            raise RuntimeError("DOUBAO_API_KEY / ARK_API_KEY 未设置")
        base_url = (
            os.getenv("DOUBAO_BASE_URL", "").strip()
            or os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()
        ).rstrip("/")
        endpoint = os.getenv("DOUBAO_IMAGES_ENDPOINT", "/images/generations").strip()
        url = f"{base_url}{endpoint}" if not endpoint.startswith("http") else endpoint
        model = (
            os.getenv("DOUBAO_IMAGE_MODEL", "").strip()
            or os.getenv("ARK_IMAGE_MODEL", "").strip()
            or DOUBAO_PROVIDER_MODELS.get(provider, DOUBAO_PROVIDER_MODELS["doubao_seedream_5_lite"])
        )
        size = (
            os.getenv("DOUBAO_IMAGE_SIZE", "").strip()
            or os.getenv("ARK_IMAGE_SIZE", "").strip()
            or os.getenv("IMAGE_SIZE", "").strip()
            or "1440x2560"
        )
        return _generate_openai_images(url, api_key, model, prompt, n, size, cache_key_prefix=f"doubao:{model}")

    api_key = os.getenv("IMAGE_API_KEY", "").strip() or os.getenv("JIMENG_API_KEY", "").strip()
    base_url = (os.getenv("IMAGE_BASE_URL", "").strip()
                or os.getenv("JIMENG_BASE_URL", "https://api.jimeng.example/v1").strip()
                ).rstrip("/")
    model = (os.getenv("IMAGE_MODEL", "").strip()
             or os.getenv("JIMENG_MODEL", "jimeng-v1").strip())
    size = os.getenv("IMAGE_SIZE", "").strip() or os.getenv("JIMENG_IMAGE_SIZE", "768x1024").strip()
    endpoint = os.getenv("JIMENG_IMAGES_ENDPOINT", "/images/generations").strip()
    url = f"{base_url}{endpoint}" if not endpoint.startswith("http") else endpoint

    # SiliconFlow / standard OpenAI format: simple Bearer auth + JSON payload
    if provider == "siliconflow":
        return _generate_openai_images(url, api_key, model, prompt, n, size, cache_key_prefix="sf")

    # Legacy Jimeng / Volcengine mode
    ak = os.getenv("JIMENG_ACCESS_KEY_ID", "").strip()
    sk = os.getenv("JIMENG_SECRET_ACCESS_KEY", "").strip()
    if not api_key and not (ak and sk):
        raise RuntimeError("API Key 未设置")

    req_key = os.getenv("JIMENG_REQ_KEY", "jimeng_t2i_v10").strip()
    cache_enabled = os.getenv("IMAGE_CACHE_ENABLED", "true").strip().lower() in ["1","true","yes"] or \
                    os.getenv("JIMENG_CACHE_ENABLED", "true").strip().lower() in ["1","true","yes"]
    if cache_enabled:
        cached = _read_cache(prompt, n, size, req_key, base_url)
        if cached:
            return cached

    headers = _build_headers(api_key)
    payload = {"model": model, "prompt": prompt, "n": n, "size": size}

    # Volcengine visual API mode (non-OpenAI format)
    action = os.getenv("JIMENG_ACTION", "").strip()
    version = os.getenv("JIMENG_VERSION", "").strip() or "2022-08-31"
    if action:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}Action={action}&Version={version}"
        width, height = 768, 1024
        try:
            w, h = size.lower().split("x", 1)
            width, height = int(w), int(h)
        except Exception:
            pass
        payload = {
            "req_key": req_key,
            "prompt": prompt,
            "seed": int(os.getenv("JIMENG_SEED", "0")),
            "scale": float(os.getenv("JIMENG_SCALE", "3.5")),
            "ddim_steps": int(os.getenv("JIMENG_STEPS", "25")),
            "width": width,
            "height": height,
            "use_pre_llm": True,
            "return_url": True,
            "sample_num": n,
        }
        extra = os.getenv("JIMENG_EXTRA_PAYLOAD_JSON", "").strip()
        if extra:
            try:
                payload.update(json.loads(extra))
            except Exception:
                pass
        # Keep auth headers configurable; do not force overwrite here.

    body_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    sign_use_volc_prefix = True
    sign_include_content_type = True
    if ak and sk:
        # Try common V4 variants for compatibility.
        last_err = None
        for use_volc_prefix in [True, False]:
            for include_content_type in [True, False]:
                signed_headers = _sign_headers_v4(
                    "POST",
                    url,
                    body_text,
                    ak,
                    sk,
                    use_volc_prefix=use_volc_prefix,
                    include_content_type=include_content_type,
                )
                resp = requests.post(url, headers=signed_headers, data=body_text.encode("utf-8"), timeout=120)
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text}
                if resp.status_code < 400:
                    headers = signed_headers
                    sign_use_volc_prefix = use_volc_prefix
                    sign_include_content_type = include_content_type
                    break
                last_err = (resp.status_code, data)
            else:
                continue
            break
        else:
            raise RuntimeError(f"image generation http error: status={last_err[0]}, body={last_err[1]}")
    else:
        resp = requests.post(url, headers=headers, data=body_text.encode("utf-8"), timeout=120)
    if not ak or not sk:
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"image generation http error: status={resp.status_code}, body={data}")

    parsed_items = _extract_images_from_payload(data)

    # Async mode for CVSync2AsyncSubmitTask
    if not parsed_items and action.lower() == "cvsync2asyncsubmittask":
        task_id = _extract_task_id(data)
        if not task_id:
            raise RuntimeError(f"image generation async submit missing task_id: {data}")
        poll_action = os.getenv("JIMENG_POLL_ACTION", "CVSync2AsyncGetResult").strip()
        poll_times = int(os.getenv("JIMENG_POLL_TIMES", "20"))
        poll_interval = float(os.getenv("JIMENG_POLL_INTERVAL_SEC", "2"))
        poll_url = f"{base_url}?Action={poll_action}&Version={version}"
        for _ in range(poll_times):
            poll_payload = {"task_id": task_id}
            if os.getenv("JIMENG_REQ_KEY", "").strip():
                poll_payload["req_key"] = os.getenv("JIMENG_REQ_KEY", "").strip()
            poll_body = json.dumps(poll_payload, ensure_ascii=False, separators=(",", ":"))
            poll_headers = headers
            if ak and sk:
                poll_headers = _sign_headers_v4(
                    "POST",
                    poll_url,
                    poll_body,
                    ak,
                    sk,
                    use_volc_prefix=sign_use_volc_prefix,
                    include_content_type=sign_include_content_type,
                )
            rr = requests.post(poll_url, headers=poll_headers, data=poll_body.encode("utf-8"), timeout=60)
            try:
                dd = rr.json()
            except Exception:
                dd = {"raw": rr.text}
            if rr.status_code >= 400:
                raise RuntimeError(f"image poll http error: status={rr.status_code}, body={dd}")
            parsed_items = _extract_images_from_payload(dd)
            if parsed_items:
                break
            task_status = str((dd.get("data", {}) or {}).get("task_status", "")).lower()
            if task_status in ["failed", "error"]:
                raise RuntimeError(f"image poll failed: {dd}")
            time.sleep(poll_interval)

    if not parsed_items:
        raise RuntimeError(f"image generation invalid response: {data}")

    paths = []
    for item in parsed_items[:n]:
        if isinstance(item, dict) and item.get("url"):
            paths.append(_download_image(item["url"]))
            continue
        if isinstance(item, dict) and item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
            paths.append(_write_bytes_file(raw, ".png"))
            continue
        raise RuntimeError(f"image generation item unsupported: {item}")
    if cache_enabled:
        cached_paths = _write_cache(prompt, n, size, req_key, base_url, paths)
        if len(cached_paths) >= n:
            return cached_paths[:n]
    return paths
