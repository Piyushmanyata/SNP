import logger from "./logger";

describe("logger utility", () => {
  let warnSpy;
  let logSpy;
  let errorSpy;
  let debugSpy;

  beforeEach(() => {
    warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    debugSpy = jest.spyOn(console, "debug").mockImplementation(() => {});
  });

  afterEach(() => {
    warnSpy.mockRestore();
    logSpy.mockRestore();
    errorSpy.mockRestore();
    debugSpy.mockRestore();
  });

  test("logger methods log appropriately in test environment", () => {
    logger.warn("test-warn");
    expect(warnSpy).toHaveBeenCalledWith("test-warn");

    logger.log("test-log");
    expect(logSpy).toHaveBeenCalledWith("test-log");

    logger.error("test-error");
    expect(errorSpy).toHaveBeenCalledWith("test-error");

    const debugFn = logger.debug;
    debugFn("test-debug");
    expect(debugSpy).toHaveBeenCalledWith("test-debug");
  });
});
