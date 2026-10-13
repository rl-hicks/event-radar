"""Inert-by-default Telegram HTTP boundary. No environment, polling or credential discovery."""

import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


@dataclass(frozen=True)
class TelegramHTTPResponse:
    status: int
    body: bytes


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


def _post(url: str, payload: dict[str, object], timeout: float) -> TelegramHTTPResponse:
    # urllib does not log request URLs. No inherited proxy, redirects, or automatic retries.
    opener = build_opener(
        ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect()
    )
    request = Request(
        url, json.dumps(payload).encode(), {"Content-Type": "application/json"}, method="POST"
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return TelegramHTTPResponse(response.status, response.read(16385))
    except HTTPError as exc:
        with exc:
            return TelegramHTTPResponse(exc.code, exc.read(16385))


class TelegramHTTPTransport:
    def __init__(
        self,
        *,
        token: str,
        authorized: bool = False,
        timeout: float = 10,
        post: Callable[[str, dict[str, object], float], TelegramHTTPResponse] = _post,
    ) -> None:
        if not 0 < timeout <= 15:
            raise ValueError("Bounded Telegram timeout required.")
        self._token, self._authorized, self._timeout, self._post = token, authorized, timeout, post

    def send(self, destination: str, message: str) -> str:
        if (
            not self._authorized
            or not self._token
            or not message
            or len(message.encode("utf-16-le")) // 2 > 3900
        ):
            return "rejected"
        try:
            response = self._post(
                "https://api.telegram.org/bot" + self._token + "/sendMessage",
                {"chat_id": destination, "text": message, "disable_web_page_preview": True},
                self._timeout,
            )
            if len(response.body) > 16384:
                return "ambiguous"
            value = json.loads(response.body)
            if not isinstance(value, dict):
                return "ambiguous"
            if response.status == 200 and value.get("ok") is True:
                result = value.get("result")
                if (
                    isinstance(result, dict)
                    and type(result.get("message_id")) is int
                    and result["message_id"] > 0
                    and isinstance(result.get("chat"), dict)
                    and str(result["chat"].get("id")) == destination
                ):
                    return "success"
                return "ambiguous"
            if (
                response.status in {400, 401, 403, 429}
                and value.get("ok") is False
                and value.get("error_code") == response.status
            ):
                return "rejected"
        except Exception:
            pass  # Never retain/log exception URLs, credentials, chat IDs or message bodies.
        return "ambiguous"
