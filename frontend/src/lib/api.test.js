import { backendOrigin } from "./api";

const ORIGINAL_ENV = process.env.REACT_APP_BACKEND_URL;
const ORIGINAL_LOCATION = window.location;

function mockLocation(hostname, protocol = "http:") {
  const origin = hostname.includes(":") ? `${protocol}//[${hostname}]` : `${protocol}//${hostname}`;
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { hostname, protocol, origin, href: `${origin}/` },
  });
}

afterEach(() => {
  process.env.REACT_APP_BACKEND_URL = ORIGINAL_ENV;
  Object.defineProperty(window, "location", {
    configurable: true,
    value: ORIGINAL_LOCATION,
  });
});

test("LAN phones call the PC host on port 8000, not localhost", () => {
  process.env.REACT_APP_BACKEND_URL = "http://localhost:8000";
  mockLocation("192.168.1.50");
  expect(backendOrigin()).toBe("http://192.168.1.50:8000");
});

test("PC localhost keeps the configured backend URL", () => {
  process.env.REACT_APP_BACKEND_URL = "http://localhost:8000";
  mockLocation("localhost");
  expect(backendOrigin()).toBe("http://localhost:8000");
});

test("production backend URL is not rewritten to :8000", () => {
  process.env.REACT_APP_BACKEND_URL = "https://api.snpcamps.example";
  mockLocation("app.snpcamps.example", "https:");
  expect(backendOrigin()).toBe("https://api.snpcamps.example");
});

test("IPv6 page host keeps brackets when rewriting to port 8000", () => {
  process.env.REACT_APP_BACKEND_URL = "http://localhost:8000";
  mockLocation("fd12::1");
  expect(backendOrigin()).toBe("http://[fd12::1]:8000");
});
