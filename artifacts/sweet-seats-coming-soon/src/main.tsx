import { createRoot } from 'react-dom/client';

import App from './App';
import { ErrorBoundary } from '@/components/error-boundary';
import { applyBrandFoundation } from '../../../lib/sweet-seats-brand/foundation';
import '../../../lib/sweet-seats-brand/tokens.css';
import '../../../lib/sweet-seats-brand/controls.css';

import './styles.css';

applyBrandFoundation(document.documentElement);
createRoot(document.getElementById('root')!, {
  // Keeps caught errors off reportError(), which would raise the dev overlay.
  onCaughtError: (error, errorInfo) => {
    console.error(error, errorInfo.componentStack);
  },
}).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
