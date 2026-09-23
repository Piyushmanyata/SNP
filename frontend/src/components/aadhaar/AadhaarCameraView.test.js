import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { AadhaarCameraView } from "./AadhaarCameraView";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("a tap maps through the object-cover crop onto the video frame", () => {
  const focus = jest.fn();
  const container = document.createElement("div");
  const root = ReactDOM.createRoot(container);
  act(() => root.render(<AadhaarCameraView mode="camera" videoRef={{ current: null }} cameraState="scanning" cameras={[]} focus={focus} />));
  const video = container.querySelector("video");
  Object.defineProperty(video, "videoWidth", { value: 1280 });
  Object.defineProperty(video, "videoHeight", { value: 720 });
  const area = container.querySelector('[data-testid="aadhaar-focus-area"]');
  area.getBoundingClientRect = () => ({ left: 0, top: 0, width: 300, height: 400 });

  act(() => area.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1, clientX: 0, clientY: 200 })));

  const [x, y] = focus.mock.calls[0];
  expect(x).toBeCloseTo(0.2891, 3);
  expect(y).toBeCloseTo(0.5, 5);
  act(() => root.unmount());
});
