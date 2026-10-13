import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import server


class APITests(unittest.TestCase):
    def setUp(self):
        server.recent_calls.clear()
        server.call_lock = asyncio.Lock()
        self.client = TestClient(server.app)

    def test_full_json_is_not_truncated(self):
        payload = {"inn": "7707083893", "card": {"custom_field": {"value": 123}}, "risks": {"errors": ["источник недоступен"]}}

        async def fake_call(name, arguments):
            self.assertEqual(name, "check_contractor")
            self.assertEqual(arguments, {"identifier": "7707083893"})
            return payload

        with patch.object(server, "invoke_mcp", fake_call):
            response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_seven_tools_allowed(self):
        async def fake_call(name, arguments):
            return {"tool": name, "arguments": arguments}

        with patch.object(server, "invoke_mcp", fake_call):
            for name in sorted(server.TOOL_NAMES):
                response = self.client.post(f"/api/tools/{name}", json={"inn": "7707083893"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["tool"], name)

    def test_invalid_format_and_json(self):
        for body in ({"identifier": "bad"}, {"identifier": 7707083893}, {"identifier": "7707083893", "extra": 1}):
            response = self.client.post("/api/check", json=body)
            self.assertEqual(response.status_code, 422)
            self.assertIn("Введите ИНН", response.json()["message"])
        self.assertEqual(self.client.post("/api/check", content="{").status_code, 422)

    def test_unknown_tool(self):
        response = self.client.post("/api/tools/not_a_tool", json={})
        self.assertEqual(response.status_code, 404)

    def test_rate_limit(self):
        server.recent_calls.extend([server.time.monotonic()] * 10)
        response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        self.assertIn("через минуту", response.json()["message"])

    def test_busy(self):
        async def exercise():
            await server.call_lock.acquire()
            try:
                with self.assertRaises(server.APIError) as caught:
                    await server.call_tool("check_inn", {"inn": "7707083893"})
                self.assertEqual(caught.exception.status, 409)
            finally:
                server.call_lock.release()

        asyncio.run(exercise())

    def test_timeout_and_failure(self):
        for error, expected_status in ((TimeoutError(), 504), (ValueError("broken transport"), 502)):
            async def failing_call(name, arguments):
                raise error

            with patch.object(server, "invoke_mcp", failing_call):
                response = self.client.post("/api/check", json={"identifier": "7707083893"})
            self.assertEqual(response.status_code, expected_status)

    def test_nested_upstream_error(self):
        async def failing_call(name, arguments):
            raise ExceptionGroup("session", [ExceptionGroup("stdio", [server.APIError(404, "not_found", "Контрагент не найден.")])])

        with patch.object(server, "invoke_mcp", failing_call):
            response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["message"], "Контрагент не найден.")

    def test_decode_errors(self):
        result = SimpleNamespace(structured_content={"error": "invalid_input", "message_ru": "Неверная контрольная цифра."}, is_error=False)
        with self.assertRaises(server.APIError) as caught:
            server.decode_result(result)
        self.assertEqual(caught.exception.status, 400)
        result = SimpleNamespace(structured_content=None, content=[SimpleNamespace(type="text", text="broken JSON")], is_error=False)
        with self.assertRaises(server.APIError) as caught:
            server.decode_result(result)
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_cross_site(self):
        response = self.client.post("/api/check", json={"identifier": "7707083893"}, headers={"origin": "http://untrusted.example"})
        self.assertEqual(response.status_code, 403)

    def test_unusable_egrul_card(self):
        result = SimpleNamespace(structured_content={"error": "invalid_input", "message_ru": "ЕГРЮЛ вернул запись без валидного ИНН — дальнейшие проверки невозможны."}, is_error=False)
        with self.assertRaises(server.APIError) as caught:
            server.decode_result(result)
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(caught.exception.code, "invalid_source_data")
        self.assertIn("не получена достоверная карточка", caught.exception.message)

    @unittest.skipUnless(os.environ.get("FNS_LIVE_TESTS") == "1", "live sources are opt-in")
    def test_live_sberbank(self):
        response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["card"]["inn"], "7707083893")
        self.assertEqual(response.json()["card"]["ogrn"], "1027700132195")
        self.assertIn("coverage", response.json()["risks"])
        self.assertEqual(response.json()["card"]["data_source_meta"]["cache_age_hours"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)