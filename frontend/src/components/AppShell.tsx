import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { BottomTabBar } from './BottomTabBar'
import { MobileHeader } from './MobileHeader'
import { TooltipProvider } from './ui/tooltip'

export function AppShell() {
  return (
    <TooltipProvider>
      <div className="flex h-screen bg-background">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden lg:pl-64">
          <MobileHeader />
          <main className="flex-1 overflow-y-auto">
            <Outlet />
          </main>
          <BottomTabBar />
        </div>
      </div>
    </TooltipProvider>
  )
}
