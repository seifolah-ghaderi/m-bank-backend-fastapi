import secrets

import httpx


class SmsDeliveryError(Exception):
    pass


class SmsAdapter:
    def __init__(self, settings):
        self.settings = settings

    def generate_code(self):
        return "123" if self.settings.sms_mode == "fixed" else f"{secrets.randbelow(1000000):06}"

    async def send(self, mobile: str, code: str):
        if self.settings.environment == "dev" and self.settings.sms_mode == "fixed":
            return
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.sms_timeout_seconds, trust_env=False
            ) as client:
                response = await client.post(
                    self.settings.sms_url,
                    headers={
                        "Authorization": "Bearer " + self.settings.sms_api_key.get_secret_value()
                    },
                    json={"to": mobile, "code": code, "sender": self.settings.sms_sender},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("accepted") is not True:
                    raise SmsDeliveryError()
        except (httpx.HTTPError, ValueError):
            raise SmsDeliveryError() from None
