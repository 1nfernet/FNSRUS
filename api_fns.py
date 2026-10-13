import asyncio
import copy
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx


SETTINGS_PATH = Path(os.environ.get("FNS_SETTINGS_PATH", str(Path(__file__).resolve().parent / "data" / "api-fns-settings.json")))


def redact_provider_log(record):
    message = record.getMessage()
    if "api-fns.ru" in message:
        record.msg = re.sub(r"https?://api-fns\.ru/[^\s\"']+", lambda match: match.group().split("?", 1)[0], message)
        record.args = ()
    return True


for logger_name in ("httpx", "httpx2"):
    logging.getLogger(logger_name).addFilter(redact_provider_log)


class ProviderError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def normalize_key(value):
    key = value.strip()
    if key.casefold().startswith(("http://", "https://")):
        try:
            link = urlsplit(key)
            parameters = parse_qs(link.query, keep_blank_values=True, max_num_fields=8)
        except ValueError as error:
            raise ProviderError(422, "invalid_settings", "Проверьте ссылку API-ФНС или введите только ключ.") from error
        if link.netloc.casefold() != "api-fns.ru" or link.path.rstrip("/") != "/api/stat" or len(parameters.get("key", [])) != 1:
            raise ProviderError(422, "invalid_settings", "Нужна ссылка api-fns.ru/api/stat с одним параметром key или сам ключ.")
        key = parameters["key"][0].strip()
    if not 8 <= len(key) <= 256 or not key.isascii() or any(character.isspace() for character in key):
        raise ProviderError(422, "invalid_settings", "Проверьте формат API-ключа.")
    return key


def load_settings():
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("api_key"), str) or not isinstance(data.get("enabled"), bool):
            raise ValueError("invalid settings")
        return data
    except FileNotFoundError:
        key = os.environ.get("FNS_API_KEY", "").strip()
        return {"api_key": key, "enabled": bool(key), "verified_at": None, "methods": []}
    except (OSError, ValueError) as error:
        raise ProviderError(503, "settings_unavailable", "Не удалось прочитать настройки API на сервере.") from error


def public_settings(data):
    return {"configured": bool(data["api_key"]), "enabled": bool(data["api_key"] and data["enabled"]),
            "verified_at": data.get("verified_at"), "methods": data.get("methods", [])}


def save_settings(data):
    temporary = None
    try:
        SETTINGS_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=SETTINGS_PATH.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, SETTINGS_PATH)
    except OSError as error:
        raise ProviderError(503, "settings_unavailable", "Не удалось сохранить настройки API на сервере.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def redact(value, key):
    if isinstance(value, dict):
        result = {}
        for name, nested in value.items():
            safe_name = name.replace(key, "[скрыто]") if key else name
            secret_field = name.casefold() in {"key", "api_key", "apikey", "token", "authorization", "ключ"}
            result[safe_name] = "[скрыто]" if secret_field else redact(nested, key)
        return result
    if isinstance(value, list):
        return [redact(nested, key) for nested in value]
    if isinstance(value, str) and key:
        return value.replace(key, "[скрыто]")
    return value


async def request_api(method, key, identifier=None):
    if method not in {"stat", "egr", "check"}:
        raise ValueError("unsupported provider method")
    fields = {"key": key}
    if identifier is not None:
        fields["req"] = identifier
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False, trust_env=False) as client:
            for request_method in ("POST", "GET"):
                options = {"data": fields} if request_method == "POST" else {"params": fields}
                async with client.stream(request_method, f"https://api-fns.ru/api/{method}", **options) as response:
                    if response.status_code in {401, 403}:
                        if request_method == "POST":
                            continue
                        detail = bytearray()
                        async for chunk in response.aiter_bytes():
                            detail.extend(chunk[:512 - len(detail)])
                            if len(detail) >= 512:
                                break
                        text = detail.decode(response.encoding or "utf-8", errors="replace").lstrip("\ufeff").strip()
                        lowered = text.casefold()
                        reason = re.search(r"неверный ключ\s*\(([0-9]{1,3})\)", lowered)
                        if "неверный ключ" in lowered:
                            message = f"API-ФНС: неверный ключ (код {reason.group(1)})." if reason else "API-ФНС сообщает: неверный ключ."
                        elif "ip" in lowered and any(word in lowered for word in ("доступ", "запрещ", "огранич", "access", "denied", "blocked")):
                            message = "API-ФНС сообщает об ограничении доступа по IP. Проверьте разрешённые IP в кабинете API-ФНС."
                        elif any(word in lowered for word in ("лимит", "quota", "limit exceeded")):
                            message = "API-ФНС сообщает об ограничении числа запросов. Проверьте остаток запросов и лимит частоты."
                        elif "html" in response.headers.get("content-type", "").casefold() or lowered.startswith(("<!doctype", "<html")):
                            message = "API-ФНС вернул защитную HTML-страницу HTTP 403 вместо статистики. Это не ответ о корректности ключа."
                        else:
                            message = "API-ФНС отклонил доступ HTTP 403 без распознанной причины."
                        logging.getLogger("fnsrus").warning("API-FNS %s denied: %s", method, message)
                        raise ProviderError(403, "api_access_denied", message + " Отказ получен при HTTPS POST и GET. Проверьте ключ и ограничения доступа.")
                    if response.status_code == 429:
                        raise ProviderError(429, "api_quota", "Лимит API-ФНС исчерпан. Проверьте тариф и доступные запросы.")
                    if response.status_code != 200:
                        raise ProviderError(503, "api_unavailable", "API-ФНС временно недоступен. Попробуйте позже.")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 8 * 1024 * 1024:
                            raise ProviderError(502, "api_response_large", "Ответ API-ФНС превышает допустимый размер.")
                    break
        payload = json.loads(body)
    except httpx.TimeoutException as error:
        raise ProviderError(504, "api_timeout", "API-ФНС не ответил вовремя. Попробуйте позже.") from error
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderError(502, "api_invalid_response", "Не удалось получить корректный ответ API-ФНС.") from error
    if not isinstance(payload, dict):
        raise ProviderError(502, "api_invalid_response", "API-ФНС вернул данные в неизвестном формате.")
    if any(payload.get(name) for name in ("error", "Error", "Ошибка")):
        raise ProviderError(403, "api_access_denied", "API-ФНС отклонил запрос. Проверьте ключ, тариф и остаток запросов.")
    return redact(payload, key)


async def validate_key(key):
    payload = await request_api("stat", key)
    status = payload.get("Статус")
    methods = payload.get("Методы", {})
    if status is not None and status not in ("FREE", "VIP"):
        raise ProviderError(403, "api_access_denied", "API-ФНС не подтвердил доступ. Проверьте ключ и срок действия тарифа.")
    if not isinstance(methods, (dict, list)) or (status is None and (not methods or
            not all(isinstance(payload.get(name), str) and payload[name] for name in ("ДатаНач", "ДатаОконч")))):
        raise ProviderError(502, "api_invalid_response", "API-ФНС вернул статистику в неизвестном формате.")
    available = [name for name in ("egr", "check") if name in methods or
                 isinstance(methods, list) and any(isinstance(item, dict) and name in item for item in methods)]
    return {"verified_at": datetime.now(timezone.utc).isoformat(), "methods": available}


CHECKS = {
    "mass_address": "Массовый адрес", "mass_director": "Массовый руководитель",
    "disqualified_director": "Дисквалификация руководителя", "bankruptcy_records": "Банкротство",
    "tax_debts": "Налоговая задолженность", "enforcement_proceedings": "Исполнительные производства",
    "active_lawsuits": "Арбитражные дела",
}


def validate_identifier(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"(?:[0-9]{10}|[0-9]{12}|[0-9]{13}|[0-9]{15})", identifier):
        raise ProviderError(400, "invalid_input", "Проверьте формат ИНН или ОГРН.")
    digits = [int(character) for character in identifier]
    def checksum(weights):
        return sum(weight * digit for weight, digit in zip(weights, digits)) % 11 % 10
    if len(digits) == 10:
        valid = checksum([2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]
    elif len(digits) == 12:
        valid = checksum([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[10] and checksum([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[11]
    else:
        valid = int(identifier[:-1]) % (11 if len(digits) == 13 else 13) % 10 == digits[-1]
    if not valid:
        raise ProviderError(400, "invalid_input", "Неверная контрольная цифра ИНН или ОГРН.")


def company_from(payload, identifier):
    items = payload.get("items")
    if not isinstance(items, list):
        raise ProviderError(502, "api_invalid_response", "API-ФНС вернул ответ без списка компаний.")
    if not items:
        raise ProviderError(404, "not_found", "Компания не найдена в API-ФНС.")
    for item in items:
        if not isinstance(item, dict):
            continue
        for kind in ("ЮЛ", "ИП"):
            data = item.get(kind)
            if isinstance(data, dict) and identifier in {str(data.get(name, "")) for name in ("ИНН", "ИННФЛ", "ОГРН", "ОГРНИП")}:
                return kind, data
    raise ProviderError(502, "api_company_mismatch", "API-ФНС не вернул карточку, соответствующую запрошенному номеру.")


def make_card(kind, data):
    director = data.get("Руководитель")
    director = director if isinstance(director, dict) else {}
    capital = data.get("Капитал")
    capital = capital if isinstance(capital, dict) else {}
    return {
        "inn": data.get("ИНН") or data.get("ИННФЛ"), "ogrn": data.get("ОГРН") or data.get("ОГРНИП"),
        "kpp": data.get("КПП"), "type": "legal_entity" if kind == "ЮЛ" else "individual_entrepreneur",
        "name": {"full": data.get("НаимПолнЮЛ") or data.get("ФИОПолн"), "short": data.get("НаимСокрЮЛ") or data.get("ФИОПолн")},
        "status": data.get("Статус"), "registration": {"date": data.get("ДатаРег") or data.get("ДатаОГРН"), "registering_authority": data.get("НО")},
        "address": data.get("Адрес"), "director": {"full_name": director.get("ФИОПолн"), "position": director.get("НаимДолжн")},
        "founders": data.get("Учредители", []), "authorized_capital_rub": capital.get("СумКап"),
        "okved_main": data.get("ОснВидДеят"), "additional_okveds": data.get("ДопВидДеят", []),
        "data_source_meta": {"source": "api_fns", "fetched_at": datetime.now(timezone.utc).isoformat(), "cache_age_hours": 0},
    }


def unavailable_report(identifier):
    return {
        "identifier": identifier, "card": {}, "legal_status": {},
        "risks": {"flags": [], "checks_passed": [], "checks_skipped": [],
                  "errors": [{"code": code, "error": "source_unavailable", "message_ru": "Проверка через открытые источники не выполнена."} for code in CHECKS]},
        "sources": {"sources_queried": []}, "recommendations": [],
    }


def overlay_card(target, updates):
    for field, value in updates.items():
        if value is None or value == "" or value == {} or value == []:
            continue
        if isinstance(value, dict):
            nested = target.get(field)
            nested = copy.deepcopy(nested) if isinstance(nested, dict) else {}
            overlay_card(nested, value)
            if nested:
                target[field] = nested
        else:
            target[field] = copy.deepcopy(value)


def merge_reports(base, identifier, egr, analytics, errors):
    result = copy.deepcopy(base)
    kind, data = company_from(egr, identifier)
    card = result.setdefault("card", {})
    overlay_card(card, make_card(kind, data))
    if data.get("Статус"):
        legal_status = result.setdefault("legal_status", {})
        legal_status.update({"status": data["Статус"], "status_label_ru": data["Статус"], "status_changed_at": data.get("СтатусДата")})
    result["api_fns"] = {"egr": egr, "check": analytics, "errors": errors}
    sources = result.setdefault("sources", {})
    queried = sources.setdefault("sources_queried", [])
    if "api_fns" not in queried:
        queried.append("api_fns")
    sources["api_fns_check_date"] = datetime.now(timezone.utc).isoformat()
    risks = result.setdefault("risks", {})
    flags = risks.setdefault("flags", [])
    passed = risks.setdefault("checks_passed", [])
    failed = risks.setdefault("errors", [])
    negative = {}
    if analytics is not None:
        try:
            _, checked = company_from(analytics, identifier)
            negative = checked.get("Негатив", {})
            if not isinstance(negative, dict):
                raise ProviderError(502, "api_invalid_response", "API-ФНС вернул неизвестный формат аналитики.")
        except ProviderError as error:
            errors.append({"method": "check", "error": error.code, "message_ru": error.message})
    for code, field in (("mass_address", "РеестрМассАдрес"), ("mass_director", "РеестрМассРук"), ("tax_debts", "НедоимкаНалог")):
        value = negative.get(field)
        positive = value is True or isinstance(value, str) and re.match(r"^Да(?:\b|\s|\()", value, re.IGNORECASE)
        clean = value is False or isinstance(value, str) and value.casefold() == "нет"
        if not positive and (not clean or code == "tax_debts"):
            continue
        failed[:] = [item for item in failed if not isinstance(item, dict) or item.get("code") != code]
        risks["checks_skipped"] = [item for item in risks.get("checks_skipped", []) if item != code]
        if code not in passed:
            passed.append(code)
        if positive and not any(flag.get("code") == code for flag in flags if isinstance(flag, dict)):
            flags.append({"code": code, "severity": "medium", "source": "api_fns", "description": f"{CHECKS[code]}: {value}"})
    answered = set(passed).intersection(CHECKS)
    flagged = {flag.get("code") for flag in flags if isinstance(flag, dict)}.intersection(CHECKS)
    answered.update(flagged)
    missing = set(CHECKS).difference(answered)
    risks["coverage"] = {"total": 7, "answered": len(answered), "flagged": len(flagged), "clean": len(answered - flagged),
                         "skipped": 0, "failed": len(missing)}
    risks["overall_risk_level"] = "high" if base.get("verdict_action") == "high_risk_do_not_proceed" else "medium" if flagged else "unknown" if missing else "low"
    if any(flag.get("source") == "api_fns" for flag in flags if isinstance(flag, dict)):
        risks["overall_risk_score"] = None
    risks["summary_ru"] = f"Проверок выполнено {len(answered)} из 7. API-ФНС дополняет сведения; отсутствующие поля не считаются отрицательным ответом."
    recommendations = result["recommendations"] = [
        "Сверьте сведения с документами контрагента и оцените недоступные проверки вручную."
    ]
    if missing or flags or errors:
        result["verdict_action"] = "manual_review_required"
        result["verdict_reason_ru"] = f"Проверок выполнено {len(answered)} из 7. Требуется ручная проверка недоступных источников и выявленных факторов."
    else:
        result["verdict_action"] = "safe_to_proceed"
        result["verdict_reason_ru"] = "Все семь проверок выполнены, выявленные риски отсутствуют."
    if base.get("verdict_action") in {"high_risk_do_not_proceed", "impossible_contractor_defunct"}:
        result["verdict_action"] = base["verdict_action"]
        result["verdict_reason_ru"] = base.get("verdict_reason_ru", "Выявлен высокий риск.")
    if str(data.get("Статус", "")).casefold() in {"ликвидировано", "ликвидирован", "прекратил деятельность", "прекратило деятельность"}:
        result["verdict_action"] = "impossible_contractor_defunct"
        result["verdict_reason_ru"] = "По сведениям API-ФНС контрагент прекратил деятельность. Проверьте официальную выписку."
    if missing:
        recommendations.append("Не выполнены проверки: " + ", ".join(CHECKS[code] for code in CHECKS if code in missing) + ".")
    if errors:
        recommendations.extend(item["message_ru"] for item in errors)
    if negative:
        recommendations.append("Проверьте все факторы в разделе «Аналитика API-ФНС»: они не ограничиваются семью базовыми проверками.")
        if result["verdict_action"] == "safe_to_proceed":
            result["verdict_action"] = "manual_review_required"
            result["verdict_reason_ru"] = "API-ФНС вернул дополнительные аналитические факторы. Требуется их ручная оценка."
    return result


async def enrich_report(identifier, key, public_call):
    validate_identifier(identifier)
    async def open_sources():
        async with asyncio.timeout(42):
            return await public_call()
    egr, analytics, base = await asyncio.gather(request_api("egr", key, identifier), request_api("check", key, identifier), open_sources(), return_exceptions=True)
    errors = []
    for method, response in (("egr", egr), ("check", analytics)):
        if isinstance(response, BaseException):
            errors.append({"method": method, "error": response.code if isinstance(response, ProviderError) else "api_unavailable",
                           "message_ru": response.message if isinstance(response, ProviderError) else "API-ФНС временно недоступен."})
    if isinstance(egr, BaseException):
        if isinstance(base, BaseException):
            if isinstance(egr, ProviderError):
                raise egr
            raise ProviderError(503, "api_unavailable", "API-ФНС и открытые источники недоступны.")
        result = copy.deepcopy(base)
        result["api_fns"] = {"errors": errors}
        result.setdefault("recommendations", []).extend(item["message_ru"] for item in errors)
        if result.get("verdict_action") == "safe_to_proceed":
            result["verdict_action"] = "manual_review_required"
            result["verdict_reason_ru"] = "API-ФНС не предоставил дополнительные сведения. Проверьте ошибки источника."
        return result
    if isinstance(base, BaseException):
        base = unavailable_report(identifier)
    try:
        return merge_reports(base, identifier, egr, None if isinstance(analytics, BaseException) else analytics, errors)
    except ProviderError as error:
        if not base.get("card"):
            raise
        result = copy.deepcopy(base)
        result["api_fns"] = {"errors": [{"method": "egr", "error": error.code, "message_ru": error.message}]}
        return result