import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'
import { AppShell } from './components/AppShell'
import { Skeleton } from './components/ui'
import './index.css'
import { I18nProvider } from './lib/i18n'
import { ThemeProvider } from './lib/theme'
import Landing from './pages/Landing'
import Start from './pages/Start'

const WorkerToday = lazy(() => import('./pages/worker/Today'))
const WorkerReport = lazy(() => import('./pages/worker/Report'))
const WorkerAsk = lazy(() => import('./pages/worker/Ask'))
const WorkerHealth = lazy(() => import('./pages/worker/Health'))
const WorkerData = lazy(() => import('./pages/worker/Data'))
const SiteOverview = lazy(() => import('./pages/site/Overview'))
const SitePlan = lazy(() => import('./pages/site/Plan'))
const SiteTasks = lazy(() => import('./pages/site/Tasks'))
const SiteCapacity = lazy(() => import('./pages/site/Capacity'))
const HseCompliance = lazy(() => import('./pages/hse/Compliance'))
const HseCopilot = lazy(() => import('./pages/hse/Copilot'))
const HsePolicy = lazy(() => import('./pages/hse/Policy'))
const HseWatch = lazy(() => import('./pages/hse/Watch'))
const HseAudit = lazy(() => import('./pages/hse/Audit'))
const ClinicQueue = lazy(() => import('./pages/clinic/Queue'))
const ClinicPatient = lazy(() => import('./pages/clinic/Patient'))
const ClinicDocuments = lazy(() => import('./pages/clinic/Documents'))
const ClinicHydration = lazy(() => import('./pages/clinic/Hydration'))
const Trust = lazy(() => import('./pages/trust/TrustCentre'))
const DrillConsole = lazy(() => import('./pages/trust/Drill'))
const Passport = lazy(() => import('./pages/Passport'))
const Credits = lazy(() => import('./pages/Credits'))
const Lab = lazy(() => import('./pages/lab/Lab'))

registerSW({ immediate: true })

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: true } } })

function Loading() {
  return <div className="space-y-4"><Skeleton className="h-10 w-64" /><Skeleton className="h-40" /><Skeleton className="h-64" /></div>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <I18nProvider>
        <QueryClientProvider client={qc}>
          <BrowserRouter>
            <Suspense fallback={<div className="p-6"><Loading /></div>}>
              <Routes>
                <Route path="/" element={<Landing />} />
                <Route path="/start" element={<Start />} />
                <Route path="/passport/:token" element={<Passport />} />
                <Route path="/credits" element={<Credits />} />
                <Route path="/app" element={<AppShell />}>
                  <Route index element={<Loading />} />
                  <Route path="worker" element={<Suspense fallback={<Loading />}><WorkerToday /></Suspense>} />
                  <Route path="worker/report" element={<Suspense fallback={<Loading />}><WorkerReport /></Suspense>} />
                  <Route path="worker/ask" element={<Suspense fallback={<Loading />}><WorkerAsk /></Suspense>} />
                  <Route path="worker/health" element={<Suspense fallback={<Loading />}><WorkerHealth /></Suspense>} />
                  <Route path="worker/data" element={<Suspense fallback={<Loading />}><WorkerData /></Suspense>} />
                  <Route path="site" element={<Suspense fallback={<Loading />}><SiteOverview /></Suspense>} />
                  <Route path="site/plan" element={<Suspense fallback={<Loading />}><SitePlan /></Suspense>} />
                  <Route path="site/tasks" element={<Suspense fallback={<Loading />}><SiteTasks /></Suspense>} />
                  <Route path="site/capacity" element={<Suspense fallback={<Loading />}><SiteCapacity /></Suspense>} />
                  <Route path="hse" element={<Suspense fallback={<Loading />}><HseCompliance /></Suspense>} />
                  <Route path="hse/copilot" element={<Suspense fallback={<Loading />}><HseCopilot /></Suspense>} />
                  <Route path="hse/policy" element={<Suspense fallback={<Loading />}><HsePolicy /></Suspense>} />
                  <Route path="hse/watch" element={<Suspense fallback={<Loading />}><HseWatch /></Suspense>} />
                  <Route path="hse/audit" element={<Suspense fallback={<Loading />}><HseAudit /></Suspense>} />
                  <Route path="clinic" element={<Suspense fallback={<Loading />}><ClinicQueue /></Suspense>} />
                  <Route path="clinic/patient/:id" element={<Suspense fallback={<Loading />}><ClinicPatient /></Suspense>} />
                  <Route path="clinic/documents" element={<Suspense fallback={<Loading />}><ClinicDocuments /></Suspense>} />
                  <Route path="clinic/hydration" element={<Suspense fallback={<Loading />}><ClinicHydration /></Suspense>} />
                  <Route path="trust" element={<Suspense fallback={<Loading />}><Trust /></Suspense>} />
                  <Route path="drill" element={<Suspense fallback={<Loading />}><DrillConsole /></Suspense>} />
                  <Route path="lab" element={<Suspense fallback={<Loading />}><Lab /></Suspense>} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </BrowserRouter>
        </QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  </StrictMode>,
)
