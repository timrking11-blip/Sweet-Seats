import { type ReactNode } from "react";
import { Route, Switch, useLocation, Router as WouterRouter } from "wouter";
import { ErrorBoundary } from "./components/error-boundary";
import Index from "./pages/home";
import NotFound from "./pages/not-found";

export function AppRoutes() {
  return (
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={Index} />
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
      <AppRoutes />
    </WouterRouter>
  );
}

export default App;
