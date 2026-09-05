import { backendOrigin } from "./api";

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
