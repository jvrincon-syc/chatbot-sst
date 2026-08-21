import { useState } from "react";
import { DashboardApp } from "../dashboard/DashboardApp.js";
import { PlatformWorkspace } from "../platform/PlatformWorkspace.js";
import { OperatorAuthWorkspace } from "./components/OperatorAuthWorkspace.js";
import { OperatorSidebar } from "./components/OperatorSidebar.js";
import type { OperatorSurface } from "./operatorNavigation.js";
import { useOperatorSession } from "./useOperatorSession.js";

export function OperatorApp() {
  const [surface, setSurface] = useState<OperatorSurface>("platform");
  const operatorSession = useOperatorSession();

  if (operatorSession.state.status !== "authenticated") {
    return (
      <div className="operator-auth-shell">
        <OperatorAuthWorkspace
          state={operatorSession.state}
          onLogin={operatorSession.login}
          onRegister={operatorSession.register}
          onRetry={() => void operatorSession.refresh()}
        />
      </div>
    );
  }

  return (
    <div className="operator-shell">
      <OperatorSidebar
        activeSurface={surface}
        onSurfaceChange={setSurface}
        session={operatorSession.state.session}
        loggingOut={operatorSession.state.loggingOut}
        onLogout={() => void operatorSession.logout()}
      />
      <div className="operator-surface">
        {surface === "legacy" ? <DashboardApp /> : <PlatformWorkspace />}
      </div>
    </div>
  );
}
