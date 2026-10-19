import { CustomerProductProvider } from './context/CustomerProductContext.jsx';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import HomeHero from './components/layout/HomeHero.jsx';
import ServicePage from './pages/ServicePage.jsx';
import './styles.css';
import './components/layout/HomeHero.css';
import './components/layout/Consultation.css';
import './team-design-bridge.css';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={<HomeHero />}
        />
        <Route
          path="/purchase"
          element={<Navigate to="/existing" replace />}
        />
        <Route
          path="/existing"
          element={<ServicePage key="existing" serviceType="existing" />}
        />
        <Route path="/subscription" element={<Navigate to="/existing" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

createRoot(document.getElementById('root')).render(
  <CustomerProductProvider>
    <App />
  </CustomerProductProvider>
);
