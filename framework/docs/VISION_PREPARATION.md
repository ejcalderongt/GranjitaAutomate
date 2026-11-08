# Vision preparation (offline validation)

VisionRequest, VisionResponse, VisionError and VisionAgent are exported by
core.ai_agent without changing the existing textual analysis contracts.
The service observes captcha, softblock and logged-out indicators only;
unknown observations remain null. It performs no device capture or actions.
Each image request requires upload_authorized=True, with a PNG data URI.
No API key produces missing_key before any network operation.
RateGate spaces all starts, including the one allowed response-parse retry.
The semaphore limits in-flight API calls to the requested concurrency (1..5).
The SDK retries are disabled for owned clients; timeout is 25 seconds per call.
Injected clients remain caller-owned. Cancellation propagates unchanged.

The system prompt is core/prompts/vision_system.txt. Invalid, truncated or
schema-invalid model output gets one retry, then a typed error. API errors
produce a sanitized error without retaining prompts, images or exception text.
No device images, paid API calls or protected database writes were used here.
This prepares E-4; it does not close the live E-4 acceptance criteria.

Image input shape follows official OpenAI documentation:
https://developers.openai.com/api/docs/guides/images-vision
Tests use injected clients and synthetic data only.
