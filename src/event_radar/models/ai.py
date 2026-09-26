from pydantic import BaseModel


class AIStageDiagnostics(BaseModel):
    stage: str
    model: str
    success: bool
    fallback_reason: str | None = None
    input_count: int
    result_count: int
    attempts: int
    latency_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    tool_calls: int | None = None
    provider_status_code: int | None = None
    provider_error_type: str | None = None
    provider_error_code: str | None = None
    provider_error_param: str | None = None
    provider_error_message: str | None = None
