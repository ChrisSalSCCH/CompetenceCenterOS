import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { toast } from 'sonner'
import './app.css'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { SessionProvider, useSession } from '@/contexts/SessionContext'
import { setApiErrorReporter } from '@/lib/api'
import { AppShell } from '@/components/AppShell'
import { LoadingBlock } from '@/components/kit'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import Organization from '@/pages/Organization'
import CircleDetail from '@/pages/CircleDetail'
import RoleDetail from '@/pages/RoleDetail'
import MyRoles from '@/pages/MyRoles'
import People from '@/pages/People'
import PersonDetail from '@/pages/PersonDetail'
import Governance from '@/pages/Governance'
import ProposalDetail from '@/pages/ProposalDetail'
import ProposalNew from '@/pages/ProposalNew'
import Meetings from '@/pages/Meetings'
import MeetingDetail from '@/pages/MeetingDetail'
import Work from '@/pages/Work'
import Goals from '@/pages/Goals'
import Assistant from '@/pages/Assistant'
import Admin from '@/pages/Admin'
import SearchPage from '@/pages/SearchPage'
import Portfolio from '@/pages/Portfolio'
import ProjectDetail from '@/pages/ProjectDetail'
import ProjectKnowledge from '@/pages/ProjectKnowledge'
import Catalog from '@/pages/Catalog'
import References from '@/pages/References'
import CrmDashboard from '@/pages/crm/CrmDashboard'
import CrmOrganizations from '@/pages/crm/CrmOrganizations'
import CrmOrganizationDetail from '@/pages/crm/CrmOrganizationDetail'
import CrmContacts from '@/pages/crm/CrmContacts'
import CrmRelationships from '@/pages/crm/CrmRelationships'
import CrmPlanned from '@/pages/crm/CrmPlanned'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20 * 1000, retry: 0, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
})

function Gate() {
  const { user, loading } = useAuth()
  const { loading: sessionLoading } = useSession()

  if (loading || (user && sessionLoading)) {
    return (
      <div className="mx-auto max-w-md p-12">
        <LoadingBlock rows={3} />
      </div>
    )
  }
  if (!user) return <Login />
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="organization" element={<Organization />} />
        <Route path="organization/circles/:id" element={<CircleDetail />} />
        <Route path="organization/roles/:id" element={<RoleDetail />} />
        <Route path="my-roles" element={<MyRoles />} />
        <Route path="people" element={<People />} />
        <Route path="people/:id" element={<PersonDetail />} />
        <Route path="governance" element={<Governance />} />
        <Route path="governance/proposals/new" element={<ProposalNew />} />
        <Route path="governance/proposals/:id" element={<ProposalDetail />} />
        <Route path="meetings" element={<Meetings />} />
        <Route path="meetings/:id" element={<MeetingDetail />} />
        <Route path="work" element={<Work />} />
        <Route path="projects" element={<Portfolio />} />
        <Route path="projects/customer" element={<Portfolio fixed="customer" />} />
        <Route path="projects/internal" element={<Portfolio fixed="internal" />} />
        <Route path="projects/knowledge" element={<ProjectKnowledge />} />
        <Route path="projects/catalog" element={<Catalog />} />
        <Route path="projects/references" element={<References />} />
        <Route path="projects/:id" element={<ProjectDetail />} />
        <Route path="crm" element={<CrmDashboard />} />
        <Route path="crm/organizations" element={<CrmOrganizations />} />
        <Route path="crm/organizations/:id" element={<CrmOrganizationDetail />} />
        <Route path="crm/contacts" element={<CrmContacts />} />
        <Route path="crm/relationships" element={<CrmRelationships />} />
        <Route path="crm/opportunities" element={<CrmPlanned module="opportunities" />} />
        <Route path="crm/quotes" element={<CrmPlanned module="quotes" />} />
        <Route path="crm/contracts" element={<CrmPlanned module="contracts" />} />
        <Route path="goals" element={<Goals />} />
        <Route path="assistant" element={<Assistant />} />
        <Route path="admin" element={<Admin />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  useEffect(() => {
    setApiErrorReporter((err) => {
      if (err.status !== 401) toast.error(err.message)
    })
    return () => setApiErrorReporter(null)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <SessionProvider>
          <BrowserRouter>
            <Gate />
          </BrowserRouter>
          <Toaster richColors position="bottom-right" />
        </SessionProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
