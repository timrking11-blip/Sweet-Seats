import { Route, Switch, Router as WouterRouter } from "wouter";

import Home from "./app/page";
import EventPage from "./app/events/event-page";

function App() {
  return <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
    <Switch>
      <Route path="/events/:eventId" component={EventPage} />
      <Route component={Home} />
    </Switch>
  </WouterRouter>;
}

export default App;
