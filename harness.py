from os import getenv
from time import sleep

from requests import Session
from requests.exceptions import ConnectionError, Timeout


class ApiError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body if isinstance(body, str) else str(body)
        super().__init__(f"HTTP {status}: {self.body[:2000]}")


_RETRY_STATUSES = {429, 502, 503, 504}
_DEFAULT_TIMEOUT = 120
_MAX_RETRIES = 3


class HarnessClient:
    def __init__(
        self,
        account: str = None,
        host: str = None,
        api_key: str = None,
        timeout: int = _DEFAULT_TIMEOUT,
        session: Session = None,
    ):
        self.account_id = account or getenv("HARNESS_ACCOUNT_ID")
        self.host = _normalize_host(host or getenv("HARNESS_URL"))
        self.api_key = api_key or getenv("HARNESS_PLATFORM_API_KEY")
        self.timeout = timeout
        self.session = session or Session()
        if not self.account_id:
            raise SystemExit("HARNESS_ACCOUNT_ID is not set")
        if not self.host:
            raise SystemExit("HARNESS_URL is not set")
        if not self.api_key:
            raise SystemExit("HARNESS_PLATFORM_API_KEY is not set")

    def url(self, path: str, via_gateway: bool = True) -> str:
        cleaned = path.lstrip("/")
        if cleaned.startswith(("https://", "http://")):
            return cleaned
        if not via_gateway:
            return f"https://{self.host}/{cleaned}"
        if cleaned.startswith("gateway/"):
            return f"https://{self.host}/{cleaned}"
        if cleaned.startswith("ccm/api/"):
            return f"https://{self.host}/gateway/{cleaned}"
        return f"https://{self.host}/gateway/ccm/api/{cleaned}"

    def request(
        self,
        method: str,
        path: str,
        params: dict = None,
        json: dict = None,
        retries: int = _MAX_RETRIES,
        via_gateway: bool = True,
    ) -> dict:
        query = {
            "routingId": self.account_id,
            "accountIdentifier": self.account_id,
        }
        if params:
            query.update(params)
        headers = {"x-api-key": self.api_key}
        attempt = 0
        while True:
            try:
                response = self.session.request(
                    method,
                    self.url(path, via_gateway=via_gateway),
                    headers=headers,
                    params=query,
                    json=json,
                    timeout=self.timeout,
                )
            except (ConnectionError, Timeout) as exc:
                if attempt >= retries:
                    raise ApiError(None, str(exc)) from exc
                sleep(_backoff(attempt))
                attempt += 1
                continue
            if response.status_code in _RETRY_STATUSES and attempt < retries:
                sleep(_backoff(attempt))
                attempt += 1
                continue
            if not response.ok:
                raise ApiError(response.status_code, response.text)
            if not response.content:
                return {}
            return response.json()


_CLIENT = None


def client() -> HarnessClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = HarnessClient()
    return _CLIENT


def reset_client() -> None:
    global _CLIENT
    _CLIENT = None


def account_id() -> str:
    return client().account_id


def gateway_url(path: str) -> str:
    return client().url(path)


def request(
    method: str,
    path: str,
    params: dict = None,
    json: dict = None,
    via_gateway: bool = True,
) -> dict:
    return client().request(
        method, path, params=params, json=json, via_gateway=via_gateway
    )


def entity_id(body) -> str:
    if isinstance(body, str):
        text = body.strip()
        return text or None
    if not isinstance(body, dict):
        return None
    for key in ("uuid", "id"):
        value = body.get(key)
        found = entity_id(value) if isinstance(value, str) else value
        if found:
            return found
    for key in ("data", "resource"):
        found = entity_id(body.get(key))
        if found:
            return found
    return None


def as_list(body) -> list:
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    data = body.get("data", body)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "views", "budgets", "items", "businessMappings"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def index_by_name(items: list) -> dict:
    found = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name and name not in found:
            copied = dict(item)
            if not copied.get("uuid") and copied.get("id"):
                copied["uuid"] = copied["id"]
            found[name] = copied
    return found


def _normalize_host(value: str) -> str:
    if not value:
        return value
    host = value.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.strip("/").split("/")[0]


def _backoff(attempt: int) -> float:
    return min(2 ** attempt, 8)
