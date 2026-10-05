# PrintBot dashboard

React 18 + Vite + TypeScript + Tailwind (black/gold theme) admin dashboard for PrintBot.

```bash
npm install
npm run dev        # http://localhost:5173, login admin / admin123 in development
npm run build      # production build (served by nginx in Docker)
```

- Pages live in `src/pages`, the Axios client in `src/services/api.ts`, the live WebSocket feed in `src/context`.
- `VITE_API_URL` and `VITE_WS_URL` point the dashboard at the backend (defaults `http://localhost:8000` and `ws://localhost:8000/ws`).
- The gold palette is defined in `tailwind.config.js`. Status colours stay emerald, amber and rose.

See the root `README.md` for the full system, and `mobile/README.md` for the operator mobile app.
