import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { AppLayout, AdminRoute } from "@/components/AppLayout";
import Login from "@/pages/Login";
import DailyLog from "@/pages/DailyLog";
import PeopleHub from "@/pages/PeopleHub";
import PayrollEngine from "@/pages/PayrollEngine";
import ReceiptVault from "@/pages/ReceiptVault";
import Settings from "@/pages/Settings";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<AppLayout />}>
              <Route path="/" element={<DailyLog />} />
              <Route path="/people" element={<AdminRoute><PeopleHub /></AdminRoute>} />
              <Route path="/payroll" element={<AdminRoute><PayrollEngine /></AdminRoute>} />
              <Route path="/receipts" element={<AdminRoute><ReceiptVault /></AdminRoute>} />
              <Route path="/settings" element={<AdminRoute><Settings /></AdminRoute>} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
