import { lazy, Suspense } from "react";
import { Route, Switch, Router as WouterRouter } from "wouter";

import Home from "./app/page";
import EventPage from "./app/events/event-page";
import NotFound from "./pages/not-found";

const StyleGuide = import.meta.env.DEV ? lazy(() => import("./pages/style-guide")) : null;

export function AppRoutes() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/events/:eventId" component={EventPage} />
      {StyleGuide && <Route path="/style-guide">
        <Suspense fallback={<main className="style-guide-loading" role="status">Loading the development guide…</main>}>
          <StyleGuide />
        </Suspense>
      </Route>}
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
    <AppRoutes />
  </WouterRouter>;
}

export default App;
