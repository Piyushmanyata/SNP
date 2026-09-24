import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

const pins = {};
let regNo = "";

function istDay(offset = 0) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
  const [year, month, day] = parts.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + offset));
  return date.toISOString().slice(0, 10);
}

function card(name, dob, last4) {
  return execFileSync(process.platform === "win32" ? "python" : "python3", [
    "backend/tests/fixtures/aadhaar_qr.py", "--name", name, "--dob", dob, "--last4", last4,
  ], { encoding: "utf8", cwd: new URL("../..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1") }).trim();
}

async function login(page, name, pin) {
  await page.goto("/login");
  await page.getByTestId("login-name-input").fill(name);
  await page.getByTestId("login-pin-input").fill(pin);
  await page.getByTestId("login-submit-button").click();
  await page.waitForURL((url) => url.pathname !== "/login");
}

async function changePin(page, current, next) {
  await page.getByTestId("current-pin-input").fill(current);
  await page.getByTestId("new-pin-input").fill(next);
  await page.getByTestId("confirm-pin-input").fill(next);
  await page.getByTestId("pin-change-submit-button").click();
  await expect(page.getByTestId("pin-change-form")).toHaveCount(0);
}

async function readOneTimePin(page) {
  const pin = (await page.getByTestId("one-time-pin").locator("p").first().innerText()).replace(/\s/g, "");
  await page.getByTestId("one-time-pin-done").click();
  return pin;
}

async function addStaff(page, name, role) {
  await page.goto("/team");
  await page.getByTestId("staff-name-input").fill(name);
  await page.getByTestId("staff-phone-input").fill("98" + String(Math.floor(Math.random() * 1e8)).padStart(8, "0"));
  await page.getByTestId("staff-role-select").selectOption(role);
  await page.getByTestId("add-staff-button").click();
  pins[name] = await readOneTimePin(page);
}

test.beforeEach(async ({ page }) => {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.addInitScript(() => {
    window.print = () => setTimeout(() => window.dispatchEvent(new Event("afterprint")), 50);
    window.addEventListener("securitypolicyviolation", (event) => {
      console.error(`CSP ${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  page._snpErrors = errors;
});

test.afterEach(async ({ page }) => {
  expect(page._snpErrors, page._snpErrors?.join("\n")).toEqual([]);
});

test.describe.serial("a camp day on the headless desk", () => {
  test("admin sets a pin and opens the camp", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
    await login(page, "admin", "864200");
    await changePin(page, "864200", "135790");
    await page.getByRole("tab", { name: "Camps & Days" }).click();
    await page.getByTestId("create-camp-button").click();
    await page.getByTestId("camp-name-input").fill("E2E Camp");
    await page.getByTestId("camp-venue-input").fill("Sikar hall");
    await page.getByTestId("camp-date-input").fill(istDay());
    await page.getByTestId("camp-number-input").fill("162");
    await page.getByTestId("camp-create-submit").click();
    await expect(page.getByText("E2E Camp")).toBeVisible();
    await page.getByRole("button", { name: "Activate" }).click();
    await page.getByRole("button", { name: "Days" }).click();
    await page.getByTestId("new-day-date").fill(istDay());
    await page.getByTestId("new-day-seat").fill("50");
    await page.getByTestId("add-day-button").click();
    await page.getByRole("tab", { name: "OT & Specs" }).click();
    await page.getByTestId("ot-date-input").fill(istDay(1));
    await page.getByTestId("ot-seat-input").fill("10");
    await page.getByTestId("ot-venue-input").fill("Sikar hospital");
    await page.getByTestId("add-ot-day-button").click();
    await page.getByTestId("specs-date-input").fill(istDay(1));
    await page.getByTestId("specs-venue-input").fill("Sikar collection");
    await page.getByTestId("add-specs-day-button").click();
    await page.getByRole("tab", { name: "Camp supplies" }).click();
    await page.getByTestId("medicine-name-input").fill("E2E drop");
    await page.getByTestId("add-medicine-button").click();
    await page.getByTestId("power-value-input").fill("1.00");
    await page.getByTestId("add-power-button").click();
    await addStaff(page, "E2E Volunteer", "volunteer");
    await addStaff(page, "E2E Clinical", "clinical_desk_operator");
    await addStaff(page, "E2E Lead", "team_lead");
    await page.getByTestId("logout-button").click();
  });

  test("the door scans a card through to paper", async ({ page }) => {
    await login(page, "E2E Volunteer", pins["E2E Volunteer"]);
    await changePin(page, pins["E2E Volunteer"], "2468");
    pins["E2E Volunteer"] = "2468";
    const usb = page.getByTestId("aadhaar-qr-input");
    await usb.fill(card("Asha Devi", "1980-01-15", "1111"));
    await usb.press("Enter");
    const phone = page.getByTestId("door-phone-input");
    await expect(phone).toBeFocused();
    await phone.fill("9812345678");
    await phone.press("Enter");
    const print = page.getByTestId("scan-print-button");
    await print.focus();
    await page.keyboard.press("Enter");
    const paper = page.getByTestId("paper-check");
    await expect(paper).toBeVisible();
    regNo = ((await paper.innerText()).match(/#(\d+)/) || [])[1];
    await page.getByTestId("paper-check-confirm").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("paper-check")).toHaveCount(0);
    await expect(usb).toBeFocused();
    await usb.fill(card("Bina Devi", "1982-04-02", "2222"));
    await usb.press("Enter");
    await expect(page.getByTestId("door-phone-input")).toHaveValue("");
    await page.getByTestId("logout-button").click();
  });

  test("clinical finishes the prescription from the keyboard", async ({ page }) => {
    await login(page, "E2E Clinical", pins["E2E Clinical"]);
    await changePin(page, pins["E2E Clinical"], "1357");
    await page.getByTestId("pick-line-doctor_rx").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("clinical-lookup-input").fill(regNo);
    await page.getByTestId("clinical-lookup-input").press("Enter");
    await page.getByTestId("diagnosis-opt-cataract").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("wizard-next").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("prescribed-medicine").focus();
    await page.keyboard.press("Space");
    await page.getByTestId("prescribed-ot").focus();
    await page.keyboard.press("Space");
    await page.getByTestId("wizard-next").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("medicine-picker").locator("button").first().focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("wizard-next").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("ot-outcome-iol_surgery").focus();
    await page.keyboard.press("Space");
    await page.getByTestId("ot-eye-select").selectOption("R");
    await page.getByTestId("bp-input").fill("120/80");
    await page.getByTestId("wizard-next").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("full-transcription-confirmed").focus();
    await page.keyboard.press("Space");
    await page.getByTestId("complete-prescription-button").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("line-change-button")).toBeEnabled();
    await page.getByTestId("line-change-button").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("pick-line-medicine").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("clinical-lookup-input").fill(regNo);
    await page.getByTestId("clinical-lookup-input").press("Enter");
    await page.getByTestId("station-medicine-paper-review").focus();
    await page.keyboard.press("Space");
    await page.getByTestId("station-medicine-save").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("line-change-button")).toBeEnabled();
    await page.getByTestId("line-change-button").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("pick-line-ot").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("clinical-lookup-input").fill(regNo);
    await page.getByTestId("clinical-lookup-input").press("Enter");
    await page.getByTestId("ot_schedule_day_id-select").selectOption({ index: 1 });
    await page.getByTestId("station-ot-paper-review").focus();
    await page.keyboard.press("Space");
    await page.getByTestId("station-ot-save").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("alert")).toContainText("IOL surgery scheduled");
    await page.getByTestId("clinical-lookup-input").fill(regNo);
    await page.getByTestId("clinical-lookup-input").press("Enter");
    await expect(page.getByTestId("station-ot-recorded")).toBeVisible();
    await page.getByTestId("logout-button").click();
  });

  test("the lead board and the camp export include the patient", async ({ page }) => {
    await login(page, "E2E Lead", pins["E2E Lead"]);
    await changePin(page, pins["E2E Lead"], "246810");
    await page.goto("/analytics");
    await expect(page.getByTestId("board-arrived")).toContainText("1");
    await expect(page.getByTestId("board-backlog")).toContainText("0");
    await expect(page.getByTestId("board-sms-failures")).toContainText("0");
    await page.getByTestId("logout-button").click();
    await login(page, "admin", "135790");
    await page.goto("/admin");
    await page.getByRole("tab", { name: "Exports" }).click();
    const download = page.waitForEvent("download");
    await page.getByTestId("export-camp-records-button").click();
    const file = await download;
    const text = readFileSync(await file.path(), "utf8");
    expect(text.split("\n")[0]).toContain("reg_no");
    expect(text).toContain("Asha Devi");
  });

  test("self-register shows a receipt", async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 851 });
    await page.goto("/self-register");
    await page.getByTestId("aadhaar-manual-toggle").click();
    const usb = page.getByTestId("aadhaar-qr-input");
    await usb.fill(card("Champa Devi", "1978-07-07", "3333"));
    await usb.press("Enter");
    await expect(page.getByTestId("self-scanned-preview")).toContainText("Champa Devi");
    await page.getByTestId("self-phone-input").fill("9898989898");
    await page.getByTestId("self-register-submit").click();
    await expect(page.getByTestId("self-receipt")).toBeVisible();
    await expect(page.getByTestId("self-receipt-regno")).toContainText("#");
  });
});
