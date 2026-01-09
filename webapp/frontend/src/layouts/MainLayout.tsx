/**
 * Main Layout Component
 */
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth0 } from '@auth0/auth0-react';

export default function MainLayout() {
  const location = useLocation();
  const { user, logout, isAuthenticated, isLoading } = useAuth0();

  const navigation = [
    { name: 'Accueil', href: '/' },
    { name: 'Consommation', href: '/consumption' },
    { name: 'Production', href: '/production' },
    { name: 'Échanges', href: '/exchanges' },
  ];

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-navy-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Chargement...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-navy-800 shadow-lg sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              {/* Logo */}
              <div className="flex-shrink-0 flex items-center">
                <Link to="/" className="text-2xl font-bold text-white">
                  ElecFlow
                </Link>
              </div>

              {/* Navigation Links */}
              <div className="hidden sm:ml-8 sm:flex sm:space-x-4">
                {navigation.map((item) => (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={`inline-flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                      isActive(item.href)
                        ? 'bg-navy-700 text-white'
                        : 'text-gray-200 hover:bg-navy-700 hover:text-white'
                    }`}
                  >
                    {item.name}
                  </Link>
                ))}
              </div>
            </div>

            {/* User Menu */}
            <div className="flex items-center">
              {isAuthenticated && user ? (
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    {user.picture && (
                      <img
                        src={user.picture}
                        alt={user.name || 'User'}
                        className="h-8 w-8 rounded-full"
                      />
                    )}
                    <span className="text-sm text-gray-200">{user.name}</span>
                  </div>
                  <button
                    onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
                    className="px-4 py-2 text-sm font-medium text-white bg-navy-600 hover:bg-navy-500 rounded-md transition-colors"
                  >
                    Déconnexion
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {/* Mobile Navigation */}
        <div className="sm:hidden">
          <div className="pt-2 pb-3 space-y-1">
            {navigation.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                className={`block pl-3 pr-4 py-2 text-base font-medium ${
                  isActive(item.href)
                    ? 'bg-navy-700 text-white'
                    : 'text-gray-200 hover:bg-navy-700 hover:text-white'
                }`}
              >
                {item.name}
              </Link>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-gray-500">
            © 2026 ElecFlow - Données électriques françaises
          </p>
        </div>
      </footer>
    </div>
  );
}
