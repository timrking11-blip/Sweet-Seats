export default function NotFound() {
  return <main className="detail-shell" aria-labelledby="not-found-title">
    <p className="eyebrow">404 · PAGE NOT FOUND</p>
    <h1 id="not-found-title">Page not found</h1>
    <p>This address does not match a Sweet Seats discovery page.</p>
    <a className="primary button-link" href="/">Return to discovery home</a>
  </main>;
}
