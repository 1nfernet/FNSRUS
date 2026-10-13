const LABELS = {
  identifier: "Идентификатор запроса", identifier_type: "Тип идентификатора", inn: "ИНН", ogrn: "ОГРН", kpp: "КПП",
  card: "Карточка", type: "Тип контрагента", status: "Статус", name: "Наименование", full: "Полное значение", short: "Сокращённое наименование",
  registration: "Регистрация", date: "Дата регистрации", registering_authority: "Регистрирующий орган", okato: "ОКАТО", oktmo: "ОКТМО",
  address: "Адрес", director: "Руководитель", full_name: "ФИО", position: "Должность", inn_masked: "ИНН физлица (маскированный)", appointed_date: "Дата назначения",
  is_disqualified: "Дисквалификация", is_mass_director: "Массовый руководитель", is_mass_address: "Массовый адрес", founders: "Учредители",
  share_percent: "Доля, %", share_rub: "Доля, руб.", share: "Доля", tax_regime: "Налоговый режим", authorized_capital_rub: "Уставный капитал, руб.",
  msp_status: "Статус МСП", extended: "Дополнительные сведения", okved_main: "Основной ОКВЭД", additional_okveds: "Дополнительные ОКВЭД", code: "Код",
  legal_status: "Юридический статус", status_label_ru: "Статус по реестру", status_changed_at: "Дата изменения статуса", bankruptcy_stage: "Стадия банкротства",
  liquidation_phase: "Стадия ликвидации", exclusion_reason: "Причина исключения", sources_checked: "Проверенные источники", warnings: "Предупреждения", checked_at: "Дата проверки",
  risks: "Риски", overall_risk_level: "Уровень риска", overall_risk_score: "Оценка риска", summary_ru: "Сводка рисков", flags: "Выявленные риски", checks_passed: "Выполненные проверки",
  checks_skipped: "Пропущенные проверки", errors: "Невыполненные проверки", error: "Причина", message_ru: "Пояснение", coverage: "Полнота проверки", total: "Всего проверок",
  answered: "Получено ответов", flagged: "С выявленным риском", clean: "Без выявленного риска", skipped: "Пропущено", failed: "Не выполнено",
  verdict_action: "Вердикт", verdict_reason_ru: "Основание вердикта", recommendations: "Рекомендации", sources: "Источники", sources_queried: "Запрошенные источники", tier: "Режим доступа",
  data_source_meta: "Актуальность карточки", egrul_extract_date: "Дата сведений ЕГРЮЛ", pb_extract_date: "Дата сведений ФНС", efrsb_check_date: "Дата проверки ЕФРСБ",
  pb_fns_check_date: "Дата проверки данных ФНС", fssp_check_date: "Дата проверки ФССП", kad_check_date: "Дата проверки КАД", registries_check_date: "Дата проверки реестров",
  cache_age_hours: "Возраст сохранённых данных, ч", fetched_at: "Дата получения", severity: "Значимость", description: "Описание", details: "Подробности", source: "Источник",
  amount_rub: "Сумма, руб.", count: "Количество", level: "Уровень", title: "Название", url: "Ссылка", reason: "Причина", directors_history: "История руководителей",
};

const VALUES = {
  legal_entity: "Юридическое лицо", individual_entrepreneur: "Индивидуальный предприниматель", ip: "Индивидуальный предприниматель", individual: "Физическое лицо",
  active: "Действующее", liquidating: "В процессе ликвидации", liquidation: "Ликвидация", liquidated: "Ликвидировано", reorganizing: "Реорганизация", bankrupt: "Банкротство",
  excluded: "Исключено из реестра", unknown: "Не определён", low: "Низкий", medium: "Средний", high: "Высокий", critical: "Критический",
  safe_to_proceed: "Можно работать", manual_review_required: "Требуется проверка", high_risk_do_not_proceed: "Высокий риск", impossible_contractor_defunct: "Контрагент прекратил деятельность",
  open: "Открытые источники", inn: "ИНН", ogrn: "ОГРН", egrul: "ЕГРЮЛ / ЕГРИП", efrsb: "ЕФРСБ", fssp: "ФССП", kad: "Картотека арбитражных дел",
  pb_fns: "Открытые данные ФНС", registries: "Локальные реестры ФНС", fns_disqualified: "Реестр дисквалифицированных лиц ФНС",
  mass_address: "Массовый адрес", mass_director: "Массовый руководитель", disqualified_director: "Дисквалификация руководителя", bankruptcy_records: "Банкротство",
  tax_debts: "Налоговая задолженность", enforcement_proceedings: "Исполнительные производства", active_lawsuits: "Арбитражные дела",
  registry_empty: "Реестр не загружен", registry_stale: "Реестр устарел", captcha_required: "Требуется код с картинки", invalid_input: "Некорректный идентификатор",
  osno: "Общая система налогообложения", usn: "Упрощённая система налогообложения", eshn: "Единый сельскохозяйственный налог", patent: "Патентная система",
};

const SECTIONS = [
  { id: "basic", title: "Основные сведения", icon: "building-2" },
  { id: "status", title: "Статус и регистрация", icon: "file-check-2" },
  { id: "leadership", title: "Руководство", icon: "user-round" },
  { id: "address", title: "Адрес", icon: "map-pin" },
  { id: "risks", title: "Риски", icon: "shield-alert" },
  { id: "verdict", title: "Вердикт", icon: "clipboard-check" },
  { id: "okved", title: "ОКВЭД", icon: "list-tree" },
  { id: "sources", title: "Источники и актуальность", icon: "database" },
];

const form = document.getElementById("check-form");
const input = document.getElementById("identifier");
const checkButton = document.getElementById("check-button");
const message = document.getElementById("form-message");
const resultElement = document.getElementById("result");
const emptyState = document.getElementById("empty-state");
let report = null;
let activeController = null;
let requestSequence = 0;
let toastTimer = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const node = element("i");
  node.dataset.lucide = name;
  node.setAttribute("aria-hidden", "true");
  return node;
}

function refreshIcons() {
  window.lucide?.createIcons();
}

export function validateIdentifier(value) {
  if (!/^(?:[0-9]{10}|[0-9]{12}|[0-9]{13}|[0-9]{15})$/.test(value)) {
    return "Введите ИНН из 10 или 12 цифр либо ОГРН из 13 или 15 цифр.";
  }
  const digits = Array.from(value, Number);
  const checksum = weights => weights.reduce((sum, weight, index) => sum + weight * digits[index], 0) % 11 % 10;
  let valid;
  if (value.length === 10) valid = checksum([2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[9];
  else if (value.length === 12) valid = checksum([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[10] && checksum([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[11];
  else valid = Number(BigInt(value.slice(0, -1)) % (value.length === 13 ? 11n : 13n) % 10n) === digits.at(-1);
  return valid ? "" : "Неверная контрольная цифра ИНН или ОГРН. Проверьте номер.";
}

export function collectLeaves(value, path = []) {
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length) return entries.flatMap(([key, nested]) => collectLeaves(nested, [...path, key]));
  }
  return [{ path, value }];
}

function sectionFor(path) {
  const [root, field] = path;
  if (root === "card") {
    if (["status", "registration"].includes(field)) return "status";
    if (["director", "directors_history"].includes(field)) return "leadership";
    if (field === "address") return "address";
    if (["okved_main", "additional_okveds"].includes(field)) return "okved";
    if (field === "data_source_meta") return "sources";
    return "basic";
  }
  if (root === "legal_status") return "status";
  if (root === "risks") return "risks";
  if (["verdict_action", "verdict_reason_ru", "recommendations"].includes(root)) return "verdict";
  return "sources";
}

function fieldLabel(path) {
  const filtered = path.filter(part => !["card", "legal_status", "risks", "data_source_meta"].includes(part));
  return filtered.map((part, index) => {
    if (/^[0-9]+$/.test(part)) return `№ ${Number(part) + 1}`;
    if (part === "full" && path.includes("name")) return "Полное наименование";
    if (part === "full" && path.includes("address")) return "Полный адрес";
    return LABELS[part] || `Дополнительное поле ${index + 1}`;
  }).join(" · ");
}

function rawCopyValue(value) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function displayValue(value) {
  if (value === null || value === "" || (typeof value === "object" && !Object.keys(value).length)) return "—";
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (typeof value === "number") return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 8 }).format(value);
  if (typeof value === "string") {
    if (VALUES[value]) return VALUES[value];
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
      const timestamp = new Date(value);
      if (!Number.isNaN(timestamp.getTime())) return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(timestamp);
    }
    return value.replace(/«([a-z_]+)»/g, (match, code) => VALUES[code] ? `«${VALUES[code]}»` : match)
      .replace(/antibot-защита/g, "защита от роботов")
      .replace(/antibot-защиты/g, "защиты от роботов")
      .replace(/antibot-защита\./g, "защита от роботов.")
      .replace(/см\. errors/g, "см. ошибки источников");
  }
  return String(value);
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

async function copyText(text) {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const previousFocus = document.activeElement;
    const textarea = element("textarea");
    textarea.value = text;
    textarea.readOnly = true;
    textarea.style.cssText = "position:fixed;left:-9999px;top:0;font-size:16px";
    textarea.setAttribute("aria-hidden", "true");
    document.body.append(textarea);
    textarea.select();
    let copied;
    try { copied = document.execCommand("copy"); }
    finally { textarea.remove(); previousFocus?.focus({ preventScroll: true }); }
    if (!copied) throw new Error("copy failed");
  }
}

async function copyWithFeedback(button, value, defaultLabel) {
  const label = button.querySelector("span");
  try {
    await copyText(value);
    clearTimeout(button.copyTimer);
    label.textContent = "Скопировано!";
    button.classList.add("copied");
    button.copyTimer = setTimeout(() => { label.textContent = defaultLabel; button.classList.remove("copied"); }, 2000);
  } catch {
    const toast = document.getElementById("copy-status");
    toast.textContent = "Не удалось скопировать. Разрешите доступ к буферу обмена в браузере.";
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 5000);
  }
}

function renderReport(data) {
  report = data;
  document.getElementById("company-name").textContent = data.card?.name?.short || data.card?.name?.full || `Контрагент ${data.inn || data.identifier || ""}`;
  const verdict = document.getElementById("verdict-summary");
  const action = data.verdict_action;
  const tone = action === "safe_to_proceed" ? "safe" : ["high_risk_do_not_proceed", "impossible_contractor_defunct"].includes(action) ? "danger" : "review";
  verdict.className = `verdict-band ${tone}`;
  const verdictText = element("div");
  verdictText.append(element("div", "verdict-title", VALUES[action] || "Требуется проверка"), element("p", "verdict-reason", data.verdict_reason_ru || "Сведения о вердикте отсутствуют."));
  verdict.replaceChildren(icon(tone === "safe" ? "shield-check" : "shield-alert"), verdictText);
  const coverageElement = document.getElementById("coverage-summary");
  coverageElement.replaceChildren();
  const coverage = data.risks?.coverage;
  if (coverage) {
    const answered = element("span");
    answered.append("Ответили источники: ", element("strong", "", `${coverage.answered ?? 0} из ${coverage.total ?? 0}`));
    const failed = element("span");
    failed.append("Не выполнено проверок: ", element("strong", "", String(coverage.failed ?? 0)));
    coverageElement.append(answered, failed);
  }
  const groups = Object.fromEntries(SECTIONS.map(section => [section.id, []]));
  for (const leaf of collectLeaves(data)) groups[sectionFor(leaf.path)].push(leaf);
  const sectionContainer = document.getElementById("sections");
  const navigation = document.getElementById("section-nav");
  sectionContainer.replaceChildren();
  navigation.replaceChildren();
  for (const section of SECTIONS) {
    const link = element("a", "", section.title);
    link.href = `#${section.id}`;
    navigation.append(link);
    const sectionElement = element("section", "data-section");
    sectionElement.id = section.id;
    const heading = element("h3", "section-heading");
    heading.append(icon(section.icon), document.createTextNode(section.title));
    sectionElement.append(heading);
    const list = element("dl", "field-list");
    for (const leaf of groups[section.id]) {
      const row = element("div", "field-row");
      row.dataset.path = JSON.stringify(leaf.path);
      const label = fieldLabel(leaf.path);
      const visibleValue = displayValue(leaf.value);
      const valueElement = element("dd", `field-value${visibleValue === "—" ? " empty" : ""}`, visibleValue);
      const copyButton = element("button", "copy-field");
      copyButton.type = "button";
      copyButton.title = `Копировать: ${label}`;
      copyButton.setAttribute("aria-label", `Копировать: ${label}`);
      copyButton.append(icon("copy"), element("span", "", "Копировать"));
      copyButton.addEventListener("click", () => copyWithFeedback(copyButton, rawCopyValue(leaf.value), "Копировать"));
      const controls = element("dd");
      controls.style.margin = "0";
      controls.append(copyButton);
      row.append(element("dt", "field-name", label), valueElement, controls);
      list.append(row);
    }
    if (groups[section.id].length) sectionElement.append(list);
    else sectionElement.append(element("p", "section-empty", "—"));
    sectionContainer.append(sectionElement);
  }
  document.getElementById("raw-json").textContent = JSON.stringify(data, null, 2);
  resultElement.hidden = false;
  emptyState.hidden = true;
  refreshIcons();
}

function setBusy(busy) {
  checkButton.disabled = busy;
  checkButton.replaceChildren(icon(busy ? "loader-circle" : "search"), element("span", "", busy ? "Проверяем…" : "Проверить"));
  if (busy) checkButton.firstChild.classList.add("loading-icon");
  form.setAttribute("aria-busy", String(busy));
  refreshIcons();
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (checkButton.disabled) return;
  const identifier = input.value.trim();
  const validationError = validateIdentifier(identifier);
  input.setAttribute("aria-invalid", String(Boolean(validationError)));
  if (validationError) { setMessage(validationError, true); input.focus(); return; }
  const sequence = ++requestSequence;
  activeController = new AbortController();
  const browserTimeout = setTimeout(() => activeController?.abort(), 65000);
  report = null;
  resultElement.hidden = true;
  emptyState.hidden = true;
  setBusy(true);
  setMessage("Получаем сведения из открытых источников…");
  try {
    const response = await fetch("/api/check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier }), signal: activeController.signal,
    });
    let data;
    try { data = await response.json(); }
    catch { throw new Error("Сервер вернул некорректный ответ. Попробуйте позже."); }
    if (!response.ok) throw new Error(data.message || data.message_ru || "Не удалось получить сведения. Попробуйте позже.");
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Сервер вернул некорректный ответ.");
    if (sequence !== requestSequence) return;
    renderReport(data);
    setMessage("Проверка завершена.");
  } catch (error) {
    if (sequence !== requestSequence) return;
    setMessage(error.name === "AbortError" ? "Проверка прервана по времени. Попробуйте позже." : error.message, true);
    emptyState.hidden = false;
  } finally {
    clearTimeout(browserTimeout);
    if (sequence === requestSequence) { activeController = null; setBusy(false); }
  }
});

input.addEventListener("input", () => { input.removeAttribute("aria-invalid"); if (message.classList.contains("error")) setMessage(""); });
document.getElementById("clear-button").addEventListener("click", () => {
  requestSequence++;
  activeController?.abort();
  activeController = null;
  report = null;
  form.reset();
  input.removeAttribute("aria-invalid");
  document.getElementById("sections").replaceChildren();
  document.getElementById("raw-json").textContent = "";
  resultElement.hidden = true;
  emptyState.hidden = false;
  setMessage("");
  setBusy(false);
  input.focus();
});
document.getElementById("copy-all").addEventListener("click", event => {
  if (report) copyWithFeedback(event.currentTarget, JSON.stringify(report, null, 2), "Копировать всё");
});
window.addEventListener("load", refreshIcons, { once: true });
refreshIcons();