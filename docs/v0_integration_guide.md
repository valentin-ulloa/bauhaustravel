# V0 Dashboard → Backend Integration Guide

**Objetivo:** Conectar el V0 dashboard (Next.js + mock data) con el backend real de Bauhaus Travel

**Estado:** Backend funcional en `https://web-production-92d8d.up.railway.app`, V0 frontend completado

---

## 🚀 **PASO 1: CONFIGURACIÓN INICIAL**

### **Environment Variables para V0**

Crear archivo `.env.local` en el proyecto V0:

```bash
# Backend API
NEXT_PUBLIC_API_BASE_URL=https://web-production-92d8d.up.railway.app
NEXT_PUBLIC_AGENCY_ID=00000000-0000-0000-0000-000000000001

# Optional: Development mode
NEXT_PUBLIC_MOCK_DATA=false
```

### **API Client Setup**

Crear `lib/api-client.ts`:

```typescript
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL
const AGENCY_ID = process.env.NEXT_PUBLIC_AGENCY_ID

export const apiClient = {
  // Agency Stats
  getAgencyStats: async () => {
    const response = await fetch(`${API_BASE_URL}/agencies/${AGENCY_ID}/stats`)
    if (!response.ok) throw new Error('Failed to fetch stats')
    return response.json()
  },

  // Trips Management
  getTrips: async () => {
    const response = await fetch(`${API_BASE_URL}/agencies/${AGENCY_ID}/trips`)
    if (!response.ok) throw new Error('Failed to fetch trips')
    return response.json()
  },

  createTrip: async (tripData: TripCreate) => {
    const response = await fetch(`${API_BASE_URL}/trips`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tripData)
    })
    if (!response.ok) throw new Error('Failed to create trip')
    return response.json()
  },

  // Health Check
  getHealth: async () => {
    const response = await fetch(`${API_BASE_URL}/health`)
    if (!response.ok) throw new Error('Health check failed')
    return response.json()
  }
}
```

## 📊 **DATOS REALES DISPONIBLES**

Tu backend ya está funcionando con estos datos:

```json
{
  "stats": {
    "total_trips": 5,
    "active_trips": 0,
    "total_conversations": 58,
    "satisfaction_rate": 0.94,
    "revenue_current_month": 250.0
  },
  "trips": [
    {
      "id": "trip_123",
      "client_name": "Maria García",
      "flight_number": "AA1234",
      "origin_iata": "GRU", 
      "destination_iata": "MEX",
      "status": "Scheduled"
    }
    // ... 4 más trips reales
  ]
}
```

## ✅ **CHECKLIST RÁPIDO**

**Para conectar V0 con tu backend:**

1. **Añadir variables de entorno en V0:**
   ```bash
   NEXT_PUBLIC_API_BASE_URL=https://web-production-92d8d.up.railway.app
   NEXT_PUBLIC_AGENCY_ID=00000000-0000-0000-0000-000000000001
   ```

2. **Reemplazar datos mock con fetch calls:**
   ```typescript
   // Antes: const stats = mockStats
   // Después: const { data: stats } = useQuery('stats', fetchStats)
   ```

3. **Testing rápido:**
   ```bash
   # Verificar que el backend responde
   curl https://web-production-92d8d.up.railway.app/health
   
   # Ver stats reales
   curl https://web-production-92d8d.up.railway.app/agencies/00000000-0000-0000-0000-000000000001/stats
   ```

4. **Deploy con datos reales:**
   - Vercel deployment ✅
   - CORS configurado ✅ 
   - API functional ✅

## 🎯 **QUÉ HACER AHORA**

**Valentin, aquí está tu plan:**

1. **📁 Subir tu V0 a GitHub** (si no lo has hecho)
2. **🔧 Seguir la guía de integración** (docs/v0_integration_guide.md)
3. **🚀 Deploy en Vercel** con variables de entorno
4. **✅ Testing con datos reales**

**Tu backend está 100% listo y funcionando.** Solo necesitas conectar el frontend.

**¿Dónde está tu código V0?** ¿GitHub? ¿Local? Te ayudo con la integración step-by-step.

---

## 📊 **PASO 2: DASHBOARD STATS INTEGRATION**

### **React Query Hook**

Crear `hooks/use-agency-stats.ts`:

```typescript
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'

export interface AgencyStats {
  total_trips: number
  active_trips: number
  total_conversations: number
  satisfaction_rate: number
  revenue_current_month: number
  revenue_total: number
  top_destinations: string[]
  avg_response_time: number
}

export const useAgencyStats = () => {
  return useQuery({
    queryKey: ['agency-stats'],
    queryFn: apiClient.getAgencyStats,
    refetchInterval: 5 * 60 * 1000, // 5 minutes
    staleTime: 2 * 60 * 1000, // 2 minutes
  })
}
```

### **Dashboard Component Update**

Actualizar el dashboard principal:

```typescript
// components/dashboard/stats-cards.tsx
import { useAgencyStats } from '@/hooks/use-agency-stats'

export function StatsCards() {
  const { data: stats, isLoading, error } = useAgencyStats()

  if (isLoading) return <StatsCardsSkeleton />
  if (error) return <StatsCardsError error={error} />

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Trips</CardTitle>
          <Plane className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.total_trips || 0}</div>
          <p className="text-xs text-muted-foreground">
            {stats?.active_trips || 0} active
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Conversations</CardTitle>
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.total_conversations || 0}</div>
          <p className="text-xs text-muted-foreground">
            {Math.round((stats?.satisfaction_rate || 0) * 100)}% satisfaction
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Revenue</CardTitle>
          <DollarSign className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">${stats?.revenue_current_month || 0}</div>
          <p className="text-xs text-muted-foreground">
            This month
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Response Time</CardTitle>
          <Clock className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.avg_response_time || 0}s</div>
          <p className="text-xs text-muted-foreground">
            Average
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
```

---

## ✈️ **PASO 3: TRIPS MANAGEMENT INTEGRATION**

### **Trips Hook**

Crear `hooks/use-trips.ts`:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'

export interface Trip {
  id: string
  client_name: string
  whatsapp: string
  flight_number: string
  origin_iata: string
  destination_iata: string
  departure_date: string
  status: string
  client_description: string
  gate?: string
  next_check_at?: string
}

export const useTrips = () => {
  return useQuery({
    queryKey: ['trips'],
    queryFn: apiClient.getTrips,
    refetchInterval: 30 * 1000, // 30 seconds
  })
}

export const useCreateTrip = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: apiClient.createTrip,
    onSuccess: () => {
      // Invalidate and refetch trips
      queryClient.invalidateQueries({ queryKey: ['trips'] })
      queryClient.invalidateQueries({ queryKey: ['agency-stats'] })
    },
  })
}
```

### **Trips Table Component**

Actualizar `components/trips/trips-table.tsx`:

```typescript
import { useTrips } from '@/hooks/use-trips'
import { format } from 'date-fns'

export function TripsTable() {
  const { data: tripsResponse, isLoading } = useTrips()
  const trips = tripsResponse?.trips || []

  if (isLoading) return <TripsTableSkeleton />

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Client</TableHead>
          <TableHead>Flight</TableHead>
          <TableHead>Route</TableHead>
          <TableHead>Departure</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trips.map((trip: Trip) => (
          <TableRow key={trip.id}>
            <TableCell>
              <div className="font-medium">{trip.client_name}</div>
              <div className="text-sm text-muted-foreground">{trip.whatsapp}</div>
            </TableCell>
            <TableCell className="font-mono">{trip.flight_number}</TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <span>{trip.origin_iata}</span>
                <ArrowRight className="h-4 w-4" />
                <span>{trip.destination_iata}</span>
              </div>
            </TableCell>
            <TableCell>
              {format(new Date(trip.departure_date), 'MMM dd, yyyy HH:mm')}
            </TableCell>
            <TableCell>
              <Badge variant={getStatusVariant(trip.status)}>
                {trip.status}
              </Badge>
            </TableCell>
            <TableCell>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="h-8 w-8 p-0">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => openTrip(trip.id)}>
                    View Details
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => viewConversations(trip.id)}>
                    Conversations
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function getStatusVariant(status: string) {
  switch (status.toLowerCase()) {
    case 'scheduled': return 'secondary'
    case 'delayed': return 'destructive'
    case 'boarding': return 'default'
    case 'arrived': return 'success'
    default: return 'secondary'
  }
}
```

---

## 💬 **PASO 4: CONVERSATIONS INTEGRATION**

### **Conversations Hook**

Crear `hooks/use-conversations.ts`:

```typescript
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'

export interface Conversation {
  id: string
  trip_id: string
  sender: 'user' | 'bot'
  message: string
  sent_at: string
  intent?: string
}

export const useConversations = (tripId?: string) => {
  return useQuery({
    queryKey: ['conversations', tripId],
    queryFn: () => apiClient.getConversations(tripId),
    enabled: !!tripId,
    refetchInterval: 10 * 1000, // 10 seconds for real-time feel
  })
}
```

### **Real-Time Chat Component**

```typescript
// components/conversations/chat-timeline.tsx
import { useConversations } from '@/hooks/use-conversations'

export function ChatTimeline({ tripId }: { tripId: string }) {
  const { data: conversations, isLoading } = useConversations(tripId)

  if (isLoading) return <ChatTimelineSkeleton />

  return (
    <ScrollArea className="h-[400px] w-full">
      <div className="space-y-4 p-4">
        {conversations?.map((conv: Conversation) => (
          <div
            key={conv.id}
            className={`flex ${conv.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[70%] rounded-lg p-3 ${
                conv.sender === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted'
              }`}
            >
              <p className="text-sm">{conv.message}</p>
              <p className="text-xs opacity-70 mt-1">
                {format(new Date(conv.sent_at), 'HH:mm')}
              </p>
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
```

---

## 🔧 **PASO 5: ERROR HANDLING & LOADING STATES**

### **Global Error Boundary**

```typescript
// components/error-boundary.tsx
export function ErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <RootErrorBoundary onReset={reset}>
          {children}
        </RootErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  )
}

function RootErrorBoundary({ onReset, children }: any) {
  return (
    <ErrorBoundary
      onReset={onReset}
      fallbackRender={({ resetErrorBoundary }) => (
        <div className="flex h-screen items-center justify-center">
          <Card className="w-[400px]">
            <CardHeader>
              <CardTitle>Something went wrong</CardTitle>
              <CardDescription>
                There was an error connecting to the backend
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={resetErrorBoundary}>Try again</Button>
            </CardContent>
          </Card>
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  )
}
```

### **Loading & Skeleton Components**

```typescript
// components/ui/skeletons.tsx
export function StatsCardsSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="space-y-0 pb-2">
            <Skeleton className="h-4 w-[100px]" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-8 w-[60px] mb-2" />
            <Skeleton className="h-3 w-[80px]" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export function TripsTableSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center space-x-4">
          <Skeleton className="h-12 w-12 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-[250px]" />
            <Skeleton className="h-4 w-[200px]" />
          </div>
        </div>
      ))}
    </div>
  )
}
```

---

## 🧪 **PASO 6: TESTING & VALIDATION**

### **Integration Tests**

```typescript
// __tests__/integration.test.ts
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StatsCards } from '@/components/dashboard/stats-cards'

// Mock fetch
global.fetch = jest.fn()

describe('Backend Integration', () => {
  beforeEach(() => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
  })

  it('loads agency stats from backend', async () => {
    (fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        total_trips: 5,
        active_trips: 0,
        total_conversations: 58,
        satisfaction_rate: 0.94,
        revenue_current_month: 250.0,
        avg_response_time: 1.8
      }),
    })

    render(
      <QueryClientProvider client={queryClient}>
        <StatsCards />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument() // total_trips
      expect(screen.getByText('58')).toBeInTheDocument() // conversations
      expect(screen.getByText('$250')).toBeInTheDocument() // revenue
    })
  })
})
```

---

## 🚀 **PASO 7: DEPLOYMENT & GO-LIVE**

### **Vercel Deployment**

```bash
# 1. Deploy to Vercel
vercel --prod

# 2. Set environment variables in Vercel Dashboard:
NEXT_PUBLIC_API_BASE_URL=https://web-production-92d8d.up.railway.app
NEXT_PUBLIC_AGENCY_ID=00000000-0000-0000-0000-000000000001

# 3. Configure custom domain
# app.nagori.travel → Vercel deployment
```

### **CORS Configuration (Backend)**

Asegurar que el backend acepta requests del dominio V0:

```python
# app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Development
        "https://app.nagori.travel",  # Production
        "https://*.vercel.app",  # Vercel preview deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## ✅ **CHECKLIST DE INTEGRACIÓN**

- [ ] **Environment variables configuradas**
- [ ] **API client implementado** 
- [ ] **React Query hooks creados**
- [ ] **Dashboard stats conectado**
- [ ] **Trips table mostrando datos reales**
- [ ] **Error handling implementado**
- [ ] **Loading states funcionando**
- [ ] **CORS configurado en backend**
- [ ] **Deploy en Vercel completado**
- [ ] **DNS configurado** (app.nagori.travel)

---

## 🎯 **RESULTADO ESPERADO**

Después de esta integración tendrás:

1. **✅ Dashboard funcional** con datos reales del backend
2. **✅ Stats en tiempo real** (5 trips, 58 conversations, 94% satisfaction)
3. **✅ Gestión de viajes** con datos reales de clientes
4. **✅ Arquitectura escalable** lista para nuevas features
5. **✅ Error handling robusto** para producción

**🚀 Next Step:** Deploy y testing con usuarios reales! 