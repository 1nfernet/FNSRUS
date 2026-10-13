import asyncio
import json
import logging
import os
import tempfile
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict, Field


BASE_DIR = Path(__file__).resolve().parent
MCP_VERSION = "0.1.12"
CALL_TIMEOUT = 50
MAX_CALLS_PER_MINUTE = 10
TOOL_NAMES = frozenset({
    "check_contractor", "check_inn", "check_ogrn", "get_legal_status",
    "get_okveds", "get_directors_history", "check_for_red_flags",
})
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("fnsrus")
call_lock = asyncio.Lock()
recent_calls = deque()


class APIError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(strict=True, pattern=r"^(?:[0-9]{10}|[0-9]{12}|[0-9]{13}|[0-9]{15})$")


def decode_result(result):
    payload = result.structured_content
    if payload is None:
        text = next((block.text for block in result.content if block.type == "text"), None)
        if text is None:
            raise APIError(502, "invalid_response", "Источник вернул ответ без данных.")
        try:
            payload = json.loads(text)
        except (ValueError, TypeError) as error:
            raise APIError(502, "invalid_response", "Источник вернул некорректный JSON.") from error
    if not isinstance(payload, dict):
        raise APIError(502, "invalid_response", "Источник вернул данные в неизвестном формате.")
    if result.is_error or payload.get("error"):
        code = str(payload.get("error", "source_error"))
        message = str(payload.get("message_ru") or "Не удалось получить сведения из источника.")
        status = {
            "invalid_input": 400,
            "not_found": 404,
            "contractor_not_found": 404,
            "source_unavailable": 503,
            "rate_limit_exceeded": 429,
            "rate_limit": 429,
        }.get(code, 502)
        if code == "invalid_input" and "ЕГРЮЛ вернул запись без валидного ИНН" in message:
            code = "invalid_source_data"
            status = 503
            message = "По этому ИНН или ОГРН не получена достоверная карточка ЕГРЮЛ. Проверьте номер; если он верный, повторите запрос позже или проверьте выписку ФНС."
        if status == 429:
            message = "Превышен лимит, попробуйте через минуту."
        raise APIError(status, code, message, payload.get("details"))
    return payload


async def invoke_mcp(name, arguments):
    with tempfile.TemporaryDirectory(prefix="fnsrus-") as cache_directory:
        parameters = StdioServerParameters(
            command=os.environ.get("UVX_PATH", "/home/deploy/.local/bin/uvx"),
            args=["--offline", "--from", f"atomno-mcp-fns-check=={MCP_VERSION}", "atomno-mcp-fns-check"],
            env=dict(
                os.environ,
                MCP_FNS_HTTP_TIMEOUT="10",
                MCP_FNS_CACHE_DB=str(Path(cache_directory) / "cache.sqlite"),
                MCP_FNS_REGISTRIES_DB=os.environ.get("MCP_FNS_REGISTRIES_DB", str(BASE_DIR / "data" / "registries.sqlite")),
                MCP_FNS_CACHE_TTL_HOURS="0",
                MCP_FNS_LOG_LEVEL="WARNING",
                FASTMCP_CHECK_FOR_UPDATES="off",
                FASTMCP_SHOW_SERVER_BANNER="false",
            ),
        )
        async with asyncio.timeout(CALL_TIMEOUT):
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    tool = next((item for item in listing.tools if item.name == name), None)
                    if tool is None:
                        raise APIError(502, "tool_unavailable", "Инструмент отсутствует в установленном MCP-сервере.")
                    if not Draft202012Validator(tool.input_schema).is_valid(arguments):
                        raise APIError(422, "invalid_parameters", "Параметры инструмента не соответствуют его схеме. Проверьте названия и типы полей.")
                    return decode_result(await session.call_tool(name, arguments))


def find_api_error(error):
    if isinstance(error, APIError):
        return error
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            found = find_api_error(nested)
            if found is not None:
                return found
    return None


async def call_tool(name, arguments):
    if name not in TOOL_NAMES:
        raise APIError(404, "unknown_tool", "Неизвестный инструмент проверки.")
    if call_lock.locked():
        raise APIError(409, "busy", "Уже выполняется проверка. Дождитесь её завершения.")
    async with call_lock:
        current_time = time.monotonic()
        while recent_calls and current_time - recent_calls[0] >= 60:
            recent_calls.popleft()
        if len(recent_calls) >= MAX_CALLS_PER_MINUTE:
            raise APIError(429, "rate_limit", "Превышен лимит, попробуйте через минуту.")
        recent_calls.append(current_time)
        try:
            return await invoke_mcp(name, arguments)
        except TimeoutError as error:
            raise APIError(504, "timeout", "Источники не ответили за 50 секунд. Попробуйте позже.") from error
        except Exception as error:
            api_error = find_api_error(error)
            if api_error is not None:
                raise api_error from error
            logger.exception("MCP call failed: %s", name)
            raise APIError(502, "mcp_failure", "Сервис данных временно недоступен. Попробуйте позже.") from error


app = FastAPI(title="ФНС РУС", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static", check_dir=False), name="static")


@app.exception_handler(APIError)
async def api_error_handler(request, error):
    payload = {"error": error.code, "message": error.message}
    if error.details is not None:
        payload["details"] = error.details
    headers = {"Retry-After": "60"} if error.status == 429 else {}
    return JSONResponse(payload, status_code=error.status, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, error):
    return JSONResponse(
        {"error": "invalid_parameters", "message": "Введите ИНН из 10 или 12 цифр либо ОГРН из 13 или 15 цифр. Передавайте параметры JSON-объектом."},
        status_code=422,
    )


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if (origin and origin != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"error": "forbidden", "message": "Запрос с другого сайта запрещён."}, status_code=403)
        if len(await request.body()) > 1024 * 1024:
            return JSONResponse({"error": "body_too_large", "message": "Размер запроса превышает 1 МБ."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(BASE_DIR / "templates" / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/explorer/", include_in_schema=False)
async def old_explorer():
    return RedirectResponse("/")


@app.get("/healthz", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.post("/api/check")
async def check_contractor(body: CheckRequest):
    return await call_tool("check_contractor", {"identifier": body.identifier})


@app.post("/api/tools/{tool_name}")
async def run_tool(tool_name: str, arguments: dict):
    return await call_tool(tool_name, arguments)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )