# hl_helper Web UI (C5)

Blueprint Ops control surface for self-hosted fleet management.

## Setup

```bash
npm install
npm run dev
```

Server runs on `http://localhost:3000` and proxies `/api/*` to FastAPI on `:8000`.

## Project Structure

- `app/` — Next.js App Router pages + layouts
- `components/` — Reusable React components (shell, primitives, domain-specific)
- `lib/` — Utilities (API client, WS adapter, auth, RBAC, hotkeys, theme, CSP)
- `tests/` — Unit (vitest) + E2E (Playwright)

## Development

### Running the app

```bash
npm run dev
```

### Linting and formatting

```bash
npm run lint      # Check with Biome
npm run format    # Fix with Biome
npm run typecheck # TypeScript check
```

### Testing

```bash
npm run test:unit  # Vitest
npm run test:e2e   # Playwright
```

### Building

```bash
npm run build
npm start
```

## Key Patterns

### Adding a new page

1. Create folder under `app/(shell)/` with route name
2. Add `page.tsx` with default export
3. Use `useAuth()` for session access, `useCan(action, scope)` for RBAC gates

### Using the API client

```typescript
import { apiFetch } from '@/lib/api-client';

const hosts = await apiFetch('/v1/hosts?limit=50');
```

### WebSocket cache mutations

The WS client auto-patches TanStack Query cache on `update`, `create`, `delete` events.

Subscribe:

```typescript
const wsClient = getWSClient(queryClient);
wsClient.subscribe('hosts.status');
```

### Hotkey registration

Per `lib/hotkeys.ts`, hotkeys follow g-prefix navigation pattern:

```
g h  → /hosts
g t  → /tasks
g d  → /docs
```

## Accessibility

- All interactive elements keyboard-reachable
- Focus visible rings consistent
- Color contrast AA minimum
- axe-core baseline in CI

## Building for production

```bash
npm run build
# Output: .next/standalone
```

Next.js standalone output is deployment-ready and includes all assets.

## Environment

- `FLEET_BASE_PATH` — sub-path deployment (default `/`)
- `FLEET_THEME_ACCENT` — color override (cyan|green|orange|oxblood|violet)

## Contributing

Keep files <500 LOC; use TypeScript strict; compose Radix/shadcn primitives; CSS variables for all colors.
