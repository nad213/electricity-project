/**
 * Home Page Component
 */
import { Link } from 'react-router-dom';

export default function HomePage() {
  const features = [
    {
      title: 'Consommation',
      description: 'Visualisez les données de consommation électrique nationale',
      icon: '⚡',
      href: '/consumption',
      color: 'bg-blue-500',
    },
    {
      title: 'Production',
      description: 'Explorez la production électrique par filière énergétique',
      icon: '🏭',
      href: '/production',
      color: 'bg-green-500',
    },
    {
      title: 'Échanges',
      description: 'Analysez les échanges commerciaux avec les pays voisins',
      icon: '🌍',
      href: '/exchanges',
      color: 'bg-purple-500',
    },
  ];

  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <div className="text-center space-y-6">
        <h1 className="text-5xl font-bold text-navy-900">
          Bienvenue sur ElecFlow
        </h1>
        <p className="text-xl text-gray-600 max-w-3xl mx-auto">
          Plateforme de visualisation et d'analyse des données électriques françaises.
          Explorez la consommation, la production et les échanges d'électricité en temps réel.
        </p>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-12">
        {features.map((feature) => (
          <Link
            key={feature.title}
            to={feature.href}
            className="group"
          >
            <div className="bg-white rounded-lg shadow-md hover:shadow-xl transition-shadow duration-300 p-8 h-full">
              <div className="flex flex-col items-center text-center space-y-4">
                <div className={`${feature.color} w-16 h-16 rounded-full flex items-center justify-center text-3xl`}>
                  {feature.icon}
                </div>
                <h2 className="text-2xl font-bold text-navy-900 group-hover:text-navy-700 transition-colors">
                  {feature.title}
                </h2>
                <p className="text-gray-600">
                  {feature.description}
                </p>
                <div className="pt-4">
                  <span className="inline-flex items-center text-navy-600 font-medium group-hover:text-navy-800 transition-colors">
                    Explorer
                    <svg className="ml-2 w-5 h-5 transform group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </span>
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* About Section */}
      <div className="bg-white rounded-lg shadow-md p-8 mt-12">
        <h2 className="text-3xl font-bold text-navy-900 mb-4">À propos</h2>
        <div className="prose prose-lg max-w-none text-gray-600">
          <p>
            ElecFlow est une plateforme moderne de visualisation des données électriques françaises.
            Nos outils permettent d'analyser et de comprendre les tendances de consommation, de production
            et d'échanges d'électricité en France.
          </p>
          <p className="mt-4">
            Les données sont actualisées régulièrement et proviennent de sources officielles,
            vous permettant d'accéder à des informations fiables et à jour pour vos analyses.
          </p>
        </div>
      </div>
    </div>
  );
}
