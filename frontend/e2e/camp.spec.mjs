import { test, expect } from "@playwright/test";

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

async function login(page, name, pin) {
  await page.goto("/");
  await page.getByTestId("login-name-input").fill(name);
  await page.getByTestId("login-pin-input").fill(pin);
  await page.getByTestId("login-submit-button").click();
}

test("admin sets a pin and opens a camp", async ({ page }) => {
  await login(page, "admin", "864200");
  await page.getByTestId("current-pin-input").fill("864200");
  await page.getByTestId("new-pin-input").fill("135790");
  await page.getByTestId("confirm-pin-input").fill("135790");
  await page.getByTestId("pin-change-submit-button").click();
  await page.getByRole("tab", { name: "Camps & Days" }).click();
  await page.getByTestId("create-camp-button").click();
  await page.getByTestId("camp-name-input").fill("E2E Camp");
  await page.getByTestId("camp-venue-input").fill("Sikar hall");
  await page.getByTestId("camp-date-input").fill(new Date().toISOString().slice(0, 10));
  await page.getByTestId("camp-number-input").fill("1");
  await page.getByTestId("camp-create-submit").click();
  await expect(page.getByText("E2E Camp")).toBeVisible();
});
