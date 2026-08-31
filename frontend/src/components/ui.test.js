import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { Button } from "./ui";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("sm buttons meet 44px minimum touch target", () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = ReactDOM.createRoot(container);
  act(() => {
    root.render(<Button size="sm">Seen</Button>);
  });
  expect(container.querySelector("button").className).toMatch(/min-h-\[44px\]/);
  act(() => {
    root.unmount();
  });
  container.remove();
});
