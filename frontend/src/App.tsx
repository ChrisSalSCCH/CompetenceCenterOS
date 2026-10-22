import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './app.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen" />
    </QueryClientProvider>
  )
}
