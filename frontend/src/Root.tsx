import App from './App'
import { VisionDebug } from './components/VisionDebug'

export function Root() {
  return window.location.pathname === '/debug' ? <VisionDebug /> : <App />
}
