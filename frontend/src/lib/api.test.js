import { AxiosError } from "axios";
import api, { backendOrigin } from "./api";

const ORIGINAL_ENV = process.env.REACT_APP_BACKEND_URL;

function mockLocation(hostname, protocol = "http:") {
  const origin = hostname.includes(":") ? `${protocol}//[${hostname}]` : `${protocol}//${hostname}`;
  return { hostname, protocol, origin, href: `${origin}/` };
}

afterEach(() => {
  if (ORIGINAL_ENV === undefined) delete process.env.REACT_APP_BACKEND_URL;
  else process.env.REACT_APP_BACKEND_URL = ORIGINAL_ENV;
});

test("LAN phones use the page origin when a stale loopback API is configured", () => {
  process.env.REACT_APP_BACKEND_URL = "http://localhost:8000";
  expect(backendOrigin(mockLocation("192.168.1.50"))).toBe("http://192.168.1.50");
});

test("PC localhost keeps the configured backend URL", () => {
  process.env.REACT_APP_BACKEND_URL = "http://localhost:8000";
  expect(backendOrigin(mockLocation("localhost"))).toBe("http://localhost:8000");
});

test("production backend URL is not rewritten to :8000", () => {
  process.env.REACT_APP_BACKEND_URL = "https://api.snpcamps.example";
  expect(backendOrigin(mockLocation("app.snpcamps.example", "https:"))).toBe("https://api.snpcamps.example");
});

test("IPv6 page uses its same origin", () => {
  process.env.REACT_APP_BACKEND_URL = "http://localhost:8000";
  expect(backendOrigin(mockLocation("fd12::1"))).toBe("http://[fd12::1]");
});

test("a production build without a configured API uses HTTPS on the page origin", () => {
  delete process.env.REACT_APP_BACKEND_URL;
  expect(backendOrigin(mockLocation("camps.example.org", "https:"))).toBe("https://camps.example.org");
});

test("a 401 outside sign-in announces that the session ended", async () => {
  const reject401 = (config) => Promise.reject(
    new AxiosError("Unauthorized", "ERR_BAD_REQUEST", config, null, { status: 401, data: {}, headers: {}, config }),
  );
  const listener = jest.fn();
  window.addEventListener("snp:unauthorized", listener);
  try {
    await expect(api.post("/auth/login", {}, { adapter: reject401 })).rejects.toMatchObject({ response: { status: 401 } });
    expect(listener).not.toHaveBeenCalled();
    await expect(api.get("/kpis", { adapter: reject401 })).rejects.toMatchObject({ response: { status: 401 } });
    expect(listener).toHaveBeenCalledTimes(1);
  } finally {
    window.removeEventListener("snp:unauthorized", listener);
  }
});
