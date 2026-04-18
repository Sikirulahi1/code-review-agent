import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.middleware.signature import verify_webhook_signature
from api.routes import health_router, reviews_router, webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Code Review Agent")


@app.middleware("http")
async def github_signature_middleware(request: Request, call_next):
	logger.info(f"Received {request.method} {request.url.path}")
	if request.method.upper() == "POST" and request.url.path == "/webhook":
		payload = await request.body()
		is_valid, status_code, detail = verify_webhook_signature(
			payload,
			request.headers.get("X-Hub-Signature-256"),
		)
		if not is_valid:
			logger.warning(f"Webhook signature failed: {detail}")
			return JSONResponse(status_code=status_code, content={"detail": detail})

	return await call_next(request)

app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(reviews_router)
