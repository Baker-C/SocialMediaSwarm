# Frontend Setup Guide - React + TypeScript + Recharts

## Project Structure

```
frontend/
├── public/
│   ├── index.html
│   └── favicon.ico
│
├── src/
│   ├── index.tsx                         # Entry point
│   ├── App.tsx                           # Main app component
│   ├── App.css
│   │
│   ├── components/
│   │   ├── Dashboard/
│   │   │   ├── Dashboard.tsx             # Main dashboard
│   │   │   ├── Dashboard.module.css
│   │   │   └── components/
│   │   │       ├── AccountCard.tsx       # Account summary card
│   │   │       ├── MetricsCard.tsx       # Metrics card
│   │   │       └── StatCard.tsx          # Single stat card
│   │   │
│   │   ├── PostBrowser/
│   │   │   ├── PostBrowser.tsx           # Browse all posts
│   │   │   ├── PostBrowser.module.css
│   │   │   └── components/
│   │   │       ├── PostCard.tsx          # Individual post
│   │   │       ├── PostFilter.tsx        # Filter posts
│   │   │       └── PostList.tsx          # List of posts
│   │   │
│   │   ├── AccountComparison/
│   │   │   ├── AccountComparison.tsx     # Compare accounts
│   │   │   ├── AccountComparison.module.css
│   │   │   └── components/
│   │   │       └── ComparisonTable.tsx   # Side-by-side table
│   │   │
│   │   ├── PatternAnalysis/
│   │   │   ├── PatternAnalysis.tsx       # Pattern performance
│   │   │   ├── PatternAnalysis.module.css
│   │   │   └── components/
│   │   │       ├── PatternCard.tsx       # Pattern summary
│   │   │       └── PatternDetails.tsx    # Pattern details
│   │   │
│   │   ├── Charts/
│   │   │   ├── EngagementChart.tsx       # Line chart for engagement
│   │   │   ├── EngagementChart.module.css
│   │   │   ├── FollowerChart.tsx         # Follower growth chart
│   │   │   ├── FollowerChart.module.css
│   │   │   ├── NicheComparison.tsx       # Compare niches
│   │   │   └── NicheComparison.module.css
│   │   │
│   │   ├── Navigation/
│   │   │   ├── Navbar.tsx                # Top navigation
│   │   │   └── Navbar.module.css
│   │   │
│   │   └── Common/
│   │       ├── LoadingSpinner.tsx        # Loading indicator
│   │       ├── ErrorMessage.tsx          # Error display
│   │       └── Modal.tsx                 # Modal popup
│   │
│   ├── services/
│   │   ├── api.ts                        # API client setup (Axios)
│   │   ├── accountService.ts             # Account API calls
│   │   ├── postService.ts                # Post API calls
│   │   ├── patternService.ts             # Pattern API calls
│   │   ├── metricsService.ts             # Metrics API calls
│   │   └── dashboardService.ts           # Dashboard API calls
│   │
│   ├── types/
│   │   ├── index.ts                      # All TypeScript types
│   │   ├── account.ts                    # Account types
│   │   ├── post.ts                       # Post types
│   │   ├── pattern.ts                    # Pattern types
│   │   └── metrics.ts                    # Metrics types
│   │
│   ├── hooks/
│   │   ├── useFetch.ts                   # Custom fetch hook
│   │   ├── useAccounts.ts                # Account data hook
│   │   └── usePolling.ts                 # Auto-polling hook
│   │
│   ├── utils/
│   │   ├── constants.ts                  # App constants
│   │   ├── formatters.ts                 # Date/number formatting
│   │   └── helpers.ts                    # Utility functions
│   │
│   ├── pages/
│   │   ├── Dashboard.page.tsx            # Dashboard page
│   │   ├── Posts.page.tsx                # Posts page
│   │   ├── Accounts.page.tsx             # Accounts page
│   │   ├── Patterns.page.tsx             # Patterns page
│   │   └── NotFound.page.tsx             # 404 page
│   │
│   └── styles/
│       ├── globals.css                   # Global styles
│       ├── variables.css                 # CSS variables
│       └── theme.css                     # Theme colors
│
├── public/
│   └── index.html
│
├── tests/
│   ├── __setup__.ts                      # Jest setup
│   ├── components/
│   │   └── Dashboard.test.tsx            # Component tests
│   ├── services/
│   │   └── api.test.ts                   # API tests
│   └── utils/
│       └── formatters.test.ts            # Utility tests
│
├── Dockerfile
├── package.json
├── tsconfig.json
├── .env.example
├── .gitignore
└── README.md
```

---

## Installation & Setup

### Prerequisites
- Node.js 18+ (latest LTS)
- npm or yarn
- Backend running at `http://localhost:8000`

### Step 1: Create React App

```bash
npx create-react-app frontend --template typescript
cd frontend
```

### Step 2: Install Dependencies

```bash
npm install
# Or: yarn install
```

### Step 3: Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

Example `.env`:
```
REACT_APP_API_URL=http://localhost:8000
REACT_APP_POLLING_INTERVAL=5000
```

### Step 4: Run Development Server

```bash
npm start
# Runs at http://localhost:3000
```

---

## Docker Setup

### Build Docker Image

```bash
docker build -t social-media-frontend:latest .
```

### Run with Docker Compose

```bash
docker-compose up frontend
```

---

## Key Concepts

### API Client (Axios)

Configured in `src/services/api.ts`:

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000'
});

export default api;
```

### Custom Hooks

Reusable data fetching logic:

```typescript
// useAccounts.ts
function useAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAccounts();
  }, []);

  return { accounts, loading };
}
```

### Types

Strong typing for all data:

```typescript
// types/account.ts
export interface Account {
  id: string;
  accountId: string;
  niche: string;
  followers: number;
  avgEngagementRate: number;
  healthScore: number;
}
```

### Charts with Recharts

```typescript
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts';

export function EngagementChart({ data }) {
  return (
    <LineChart width={600} height={300} data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="name" />
      <YAxis />
      <Line type="monotone" dataKey="engagement" stroke="#8884d8" />
    </LineChart>
  );
}
```

---

## Component Structure

### Page Components

Located in `src/pages/`:
- Dashboard.page.tsx: Main dashboard
- Posts.page.tsx: Post browser
- Accounts.page.tsx: Account list
- Patterns.page.tsx: Pattern analysis

### Feature Components

Located in `src/components/`:
- Dashboard: Main dashboard view
- PostBrowser: Browse/filter posts
- AccountComparison: Compare accounts
- PatternAnalysis: Pattern metrics
- Charts: All chart components

### Common Components

Located in `src/components/Common/`:
- LoadingSpinner: Loading state
- ErrorMessage: Error display
- Modal: Popup dialogs

---

## Data Flow

```
User Action
    ↓
Component (e.g., Dashboard.tsx)
    ↓
Hook (e.g., useAccounts.ts)
    ↓
Service (e.g., accountService.ts)
    ↓
API Client (api.ts)
    ↓
Backend (FastAPI)
    ↓
RavenDB
    ↓
Response back to Component
    ↓
Update UI
```

---

## Polling for Real-time Data

Frontend polls backend every 5 seconds for updates:

```typescript
// usePolling.ts
function usePolling(fetchFn, interval = 5000) {
  useEffect(() => {
    const timer = setInterval(fetchFn, interval);
    return () => clearInterval(timer);
  }, [fetchFn, interval]);
}

// Usage:
function Dashboard() {
  const { accounts, fetchAccounts } = useAccounts();
  usePolling(fetchAccounts, 5000); // Poll every 5 seconds
  
  return <div>{/* render accounts */}</div>;
}
```

---

## Development Workflow

### Creating a New Feature

1. Create types in `src/types/`
2. Create service in `src/services/`
3. Create custom hook in `src/hooks/`
4. Create components in `src/components/`
5. Create page in `src/pages/`
6. Add route to navigation
7. Write tests in `tests/`

### Running Tests

```bash
# Run all tests
npm test

# Run specific test file
npm test Dashboard.test.tsx

# Run with coverage
npm test -- --coverage
```

### Building for Production

```bash
npm run build
# Creates optimized build in `build/` directory
```

---

## Styling

Uses CSS Modules for component-scoped styles:

```typescript
// Dashboard.module.css
.container {
  padding: 20px;
  background-color: var(--bg-primary);
}

// Dashboard.tsx
import styles from './Dashboard.module.css';

export function Dashboard() {
  return <div className={styles.container}>...</div>;
}
```

Global variables in `src/styles/variables.css`:

```css
:root {
  --bg-primary: #ffffff;
  --text-primary: #333333;
  --accent-color: #0066cc;
  --chart-color: #8884d8;
}
```

---

## API Endpoints

Frontend calls these backend endpoints:

```
GET /api/accounts                  # Get all accounts
GET /api/accounts/{id}            # Get account details
GET /api/posts                     # Get posts (with filters)
GET /api/posts/{id}               # Get post details
GET /api/patterns                  # Get patterns
GET /api/metrics/{account_id}      # Get account metrics
GET /api/dashboard                 # Get dashboard data
GET /api/health                    # Health check
```

---

## Environment Variables

```
REACT_APP_API_URL=http://localhost:8000
REACT_APP_POLLING_INTERVAL=5000
REACT_APP_CHART_COLORS=["#8884d8", "#82ca9d", "#ffc658"]
```

---

## Common Issues & Solutions

### CORS Error
```
Backend needs CORS headers configured
Check FastAPI middleware in app/main.py
```

### API Calls Not Working
```
Check:
- Backend is running on port 8000
- REACT_APP_API_URL in .env is correct
- Network tab in browser dev tools
```

### Charts Not Displaying
```
Check:
- Recharts is installed: npm install recharts
- Data is in correct format
- Chart dimensions are set
```

### Build Fails
```bash
# Clear cache
rm -rf node_modules package-lock.json
npm install
npm run build
```

---

## Performance Tips

1. Use `React.memo()` for expensive components
2. Use `useCallback()` for event handlers
3. Use `useMemo()` for expensive calculations
4. Lazy load pages with `React.lazy()`
5. Minimize chart data points (aggregate if needed)

---

## Accessibility

- Use semantic HTML (`<button>`, `<nav>`, etc.)
- Add `aria-labels` to interactive elements
- Ensure color contrast meets WCAG standards
- Test with keyboard navigation

---

## Next Steps

1. Run `docker-compose up` from root directory
2. Access frontend at `http://localhost:3000`
3. Start building dashboard components
4. Connect to backend endpoints
5. Add charts for Stage 1 data
