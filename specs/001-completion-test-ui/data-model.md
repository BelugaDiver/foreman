# Data Model: Completion Test UI

**Phase**: 1 (Design)  
**Date**: 2026-05-13  
**Target Audience**: Developers implementing components in `foreman/ui/`

## Client-Side State Management

### Module: `state.js`

Centralized state container managing all runtime data. Accessed via getter/setter functions; triggers listeners on mutation.

```javascript
// Global state shape
state = {
  // User/Auth
  user: {
    id: string | null,           // x-user-id header value (from user creation or manual entry)
    email: string | null,
    fullName: string | null,
    createdAt: ISO8601 | null
  },

  // Settings
  settings: {
    apiBaseUrl: string,          // default: "http://localhost:8000"
    pollingIntervalMs: number,   // default: 3000 (3 seconds)
    autoDiscoveryEnabled: boolean // default: true
  },

  // API Discovery
  apiStatus: {
    isDiscovered: boolean,       // true if foreman API endpoint confirmed
    lastChecked: ISO8601 | null,
    discoveryError: string | null
  },

  // Projects (cached list)
  projects: {
    items: Project[],            // sorted by created_at DESC
    isLoading: boolean,
    error: string | null,
    currentProjectId: string | null  // selected project context
  },

  // Generations (cached list for current project)
  generations: {
    items: Generation[],         // sorted by created_at DESC
    isLoading: boolean,
    error: string | null,
    currentGenerationId: string | null  // selected job detail view
  },

  // Styles (cached list)
  styles: {
    items: Style[],
    isLoading: boolean,
    error: string | null
  },

  // UI Navigation
  ui: {
    currentView: 'settings' | 'auth' | 'projects' | 'job-form' | 'job-list' | 'job-detail',
    navHistory: string[],        // breadcrumb trail
    notificationQueue: Notification[]  // toast messages
  },

  // Polling
  polling: {
    activeJobId: string | null,  // if job-detail view is active, poll this job
    pollingTimer: number | null,
    isPolling: boolean
  }
}
```

### Entity Structures

#### User
```javascript
{
  id: "550e8400-e29b-41d4-a716-446655440000",  // UUID from API
  email: "dev@example.com",
  fullName: "Developer Name",
  isActive: true,
  createdAt: "2026-05-13T10:30:00Z"
}
```

#### Project
```javascript
{
  id: "550e8400-e29b-41d4-a716-446655440001",
  userId: "550e8400-e29b-41d4-a716-446655440000",
  name: "My Test Project",
  originalImageUrl: "https://example.com/image.jpg" | null,
  roomAnalysis: { /* arbitrary JSON */ } | null,
  createdAt: "2026-05-13T10:30:00Z",
  updatedAt: "2026-05-13T10:35:00Z"
}
```

#### Generation (Job)
```javascript
{
  id: "550e8400-e29b-41d4-a716-446655440002",
  projectId: "550e8400-e29b-41d4-a716-446655440001",
  parentId: "550e8400-e29b-41d4-a716-446655440003" | null,
  status: "pending" | "processing" | "completed" | "failed" | "cancelled",
  prompt: "Modern minimalist interior design",
  styleId: "550e8400-e29b-41d4-a716-446655440004" | null,
  modelUsed: "stable-diffusion-v3" | null,
  inputImageUrl: "https://storage.example.com/input-abc123.jpg",
  outputImageUrl: "https://storage.example.com/output-xyz789.jpg" | null,
  errorMessage: "Model timeout after 30s" | null,
  processingTimeMs: 25000 | null,
  attempt: 1,
  metadata: { /* arbitrary JSON */ } | null,
  createdAt: "2026-05-13T10:30:00Z",
  updatedAt: "2026-05-13T10:35:00Z"
}
```

#### Style
```javascript
{
  id: "550e8400-e29b-41d4-a716-446655440004",
  name: "Modern Minimalist",
  description: "Clean lines, neutral colors, minimal ornamentation",
  exampleImageUrl: "https://example.com/style-modern.jpg" | null,
  createdAt: "2026-05-13T10:00:00Z",
  updatedAt: "2026-05-13T10:00:00Z"
}
```

#### Notification (UI-only)
```javascript
{
  id: "unique-string",
  type: "success" | "error" | "info" | "warning",
  message: "Generation job created successfully",
  duration: 5000  // auto-dismiss after 5 seconds
}
```

## State Management API

### Getters
```javascript
getUser()                        // returns state.user
getApiUrl()                      // returns state.settings.apiBaseUrl
getIsAuthenticated()            // returns state.user.id !== null
getCurrentProject()             // returns state.projects.currentProject
getCurrentGeneration()          // returns state.generations.currentGeneration
getGenerationsForProject(id)    // filters state.generations.items by projectId
getProjectById(id)              // finds project in state
getGenerationById(id)           // finds generation in state
getStyles()                     // returns state.styles.items
isPollingActive()               // returns state.polling.isPolling
```

### Setters (trigger listeners)
```javascript
setUser(user)                   // updates state.user; persists to localStorage
setApiUrl(url)                  // updates state.settings.apiBaseUrl; persists
setPollingInterval(ms)          // updates state.settings.pollingIntervalMs
setCurrentProject(projectId)    // updates state.projects.currentProjectId
setCurrentGeneration(genId)     // updates state.generations.currentGenerationId; starts polling if detail view
setProjects(projects)           // replaces state.projects.items
setGenerations(generations)     // replaces state.generations.items for current project
setStyles(styles)               // replaces state.styles.items
addNotification(type, message)  // adds to notification queue
startPolling(generationId)      // sets up interval to fetch generation status
stopPolling()                   // clears polling timer
switchView(viewName)            // updates state.ui.currentView; history tracking
```

### Event Listeners
```javascript
onStateChange(key, callback)    // listener fires when key changes
onProjectsChange(callback)
onGenerationsChange(callback)
onUserChange(callback)
onViewChange(callback)
// Usage: state.onStateChange('user', (newUser) => { /* update UI */ })
```

## Persistence Strategy

### localStorage Keys
```
"foremanUI::userId"             // x-user-id header
"foremanUI::apiBaseUrl"         // API endpoint
"foremanUI::pollingInterval"    // polling interval setting
"foremanUI::lastKnownUser"      // cached user data (for offline reference)
```

### Data Refresh Triggers
- **Projects list**: Fetch on project view entry; refresh button available
- **Generations list**: Fetch when project selected; auto-refresh every 10 seconds in list view
- **Current generation**: Fetch every N seconds (pollingInterval) while viewing detail
- **Styles list**: Fetch once on app load; cache in state
- **User**: Fetch after user creation; verify x-user-id valid on app init

## Component State Isolation

Each component (`projects.js`, `generation-form.js`, etc.) should:
1. Call state getter functions to read current data
2. Register listeners via `state.onStateChange()` for reactive updates
3. Call `api.js` functions for mutations (which then call state setters)
4. Avoid storing duplicate data; derive UI state from global state

**Bad**: Component stores local copy of projects list
**Good**: Component reads from state, re-renders when state changes (via listener)

## Error State Model

Every async operation has three states: loading, success, error

```javascript
// Projects view
{
  isLoading: true,    // fetching from API
  items: [],
  error: null
}

// After successful fetch
{
  isLoading: false,
  items: [{ id: "...", name: "..." }, ...],
  error: null
}

// After failed fetch
{
  isLoading: false,
  items: [],  // or [] if first load; or previous data if refetch
  error: "Failed to fetch projects: 500 Internal Server Error"
}
```

All error messages must be user-friendly; parse API error responses and surface them.
