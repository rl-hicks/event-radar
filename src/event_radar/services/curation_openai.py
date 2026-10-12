"""Explicit, inert-by-default OpenAI Responses boundary. Never reads environment."""

from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from event_radar.models.token_usage import ModelTokenPricing, parse_token_usage
from event_radar.models.weekend_packet import CurationResult, CurationUsage, PersonalizedRequest
from event_radar.services.personalized_curation import PROMPT, ProviderFailure, ProviderResponse
from event_radar.shared.failures import safe_usage


class OpenAIResponsesCurationProvider:
    def __init__(
        self,
        *,
        client: Any = None,
        authorized: bool = False,
        api_key: str | None = None,
        pricing: ModelTokenPricing | None = None,
    ) -> None:
        self.client = client
        self.authorized = authorized
        self.api_key = api_key
        self.pricing = pricing

    async def curate(self, request: PersonalizedRequest) -> ProviderResponse:
        if not self.authorized or request.policy.provider != "openai":
            raise ProviderFailure("not_configured")
        client = self.client
        owned = False
        if client is None:
            if not self.api_key:
                raise ProviderFailure("not_configured")
            client = AsyncOpenAI(
                api_key=self.api_key, max_retries=0, timeout=request.policy.timeout_seconds
            )
            owned = True
        usage = CurationUsage(provider_calls=1)
        try:
            # with_options also removes retries from an explicitly injected SDK client.
            response = await client.with_options(
                max_retries=0, timeout=request.policy.timeout_seconds
            ).responses.parse(
                model=request.policy.model,
                instructions=PROMPT,
                input=request.model_dump_json(),
                text_format=CurationResult,
                max_output_tokens=request.policy.max_output_tokens,
                store=False,
                tools=[],
            )
            parsed_usage = safe_usage(
                parse_token_usage(getattr(response, "usage", None), self.pricing)
            )
            values = parsed_usage.model_dump()
            usage = CurationUsage(
                **values,
                provider_calls=1,
                usage_complete=all(
                    values[k] is not None
                    for k in (
                        "input_tokens",
                        "cached_input_tokens",
                        "output_tokens",
                        "total_tokens",
                    )
                ),
            )
            if response.status != "completed" or response.error is not None:
                raise ProviderFailure("invalid_response", usage)
            # Reject unsolicited tools as well as incomplete structured responses.
            if any(
                getattr(item, "type", None) not in {"message", "reasoning"}
                for item in response.output
            ):
                raise ProviderFailure("invalid_response", usage)
            result = CurationResult.model_validate(
                response.output_parsed.model_dump(mode="json", warnings=False)
            )
            return ProviderResponse(result, usage)
        except ProviderFailure:
            raise
        except (TimeoutError, APITimeoutError):
            raise ProviderFailure("timeout", usage) from None
        except APIStatusError as exc:
            raise ProviderFailure(
                "rate_limited" if exc.status_code == 429 else "unavailable", usage
            ) from None
        except APIConnectionError:
            raise ProviderFailure("unavailable", usage) from None
        except Exception:
            raise ProviderFailure("invalid_response", usage) from None
        finally:
            if owned:
                await client.close()
