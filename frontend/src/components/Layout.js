import React, { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
  LayoutDashboard,
  Car,
  Users,
  ClipboardList,
  CalendarDays,
  BarChart3,
  LogOut,
  Menu,
  KeyRound,
} from "lucide-react";

const navItems = [
  { to: "/", label: "Beranda", icon: LayoutDashboard, testid: "nav-beranda" },
  { to: "/kendaraan", label: "Kendaraan", icon: Car, testid: "nav-kendaraan" },
  { to: "/pelanggan", label: "Pelanggan", icon: Users, testid: "nav-pelanggan" },
  { to: "/rental", label: "Rental", icon: ClipboardList, testid: "nav-rental" },
  { to: "/kalender", label: "Kalender", icon: CalendarDays, testid: "nav-kalender" },
  { to: "/laporan", label: "Laporan", icon: BarChart3, testid: "nav-laporan" },
];

const Brand = () => (
  <div className="flex items-center gap-2.5 px-2">
    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm">
      <KeyRound className="h-5 w-5" />
    </div>
    <div className="leading-tight">
      <div className="font-heading text-lg font-extrabold tracking-tight text-slate-900">ARMI</div>
      <div className="text-[11px] font-medium uppercase tracking-[0.15em] text-slate-400">Rental</div>
    </div>
  </div>
);

const NavContent = ({ onNavigate }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col">
      <div className="py-6">
        <Brand />
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            data-testid={item.testid}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-200 ${
                isActive
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`
            }
          >
            <item.icon className="h-[18px] w-[18px]" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-slate-200 p-3">
        <div className="mb-2 px-3 py-1">
          <div className="truncate text-sm font-semibold text-slate-800">{user?.name || "Admin"}</div>
          <div className="truncate text-xs text-slate-400">{user?.email}</div>
        </div>
        <Button
          data-testid="logout-button"
          variant="ghost"
          className="w-full justify-start gap-3 text-slate-600 hover:bg-red-50 hover:text-red-600"
          onClick={async () => {
            await logout();
            navigate("/login");
          }}
        >
          <LogOut className="h-[18px] w-[18px]" /> Keluar
        </Button>
      </div>
    </div>
  );
};

export default function Layout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-slate-50">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-slate-200 bg-white lg:block">
        <NavContent />
      </aside>

      {/* Mobile header */}
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 lg:hidden">
        <Brand />
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button data-testid="mobile-menu-button" variant="outline" size="icon">
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 p-0">
            <SheetTitle className="sr-only">Menu Navigasi</SheetTitle>
            <NavContent onNavigate={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
      </header>

      <main className="lg:pl-64">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
