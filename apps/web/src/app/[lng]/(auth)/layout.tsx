import { AppCosmos } from '@/components/landing/cosmic/AppCosmos';

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    // No background on this root: the landing's cosmos paints the page
    // ground (AppCosmos, fixed layers on a negative z-index that an in-flow
    // background here would cover); the card below stays solid.
    <div className="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <AppCosmos />

      <div className="max-w-md w-full space-y-8 bg-card p-8 rounded-2xl shadow-lg border border-border/50">
        {children}
      </div>
    </div>
  );
}
