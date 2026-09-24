import React from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "./ui";
import logger from "../lib/logger";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    logger.error("Unhandled application error:", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="min-h-screen flex items-center justify-center bg-white p-6">
        <div className="max-w-md text-center">
          <AlertTriangle className="w-10 h-10 mx-auto text-rose-700" />
          <h1 className="mt-3 text-xl font-bold text-slate-900">This screen could not be opened</h1>
          <p className="mt-2 text-slate-800">
            Nothing was saved or changed. Reload to try again, or use another device and carry on with the camp.
          </p>
          <Button className="mt-5" onClick={() => window.location.reload()} data-testid="app-error-reload">
            Reload the app
          </Button>
        </div>
      </div>
    );
  }
}
