import { Route, Switch, Router as WouterRouter } from "wouter";

import Home from "./app/page";
import EventPage from "./app/events/event-page";
import NotFound from "./pages/not-found";

export function AppRoutes() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/events/:eventId" component={EventPage} />
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
