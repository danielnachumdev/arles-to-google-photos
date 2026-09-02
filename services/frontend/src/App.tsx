import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import './App.css'
import { AppNav } from './components/AppNav.tsx'
import { RunToaster } from './components/RunToaster.tsx'
import { ToastHost } from './components/ToastHost.tsx'
import { t, useLanguage } from './lib/language.ts'
import { AlbumLibrary } from './pages/AlbumLibrary.tsx'
import { AlbumWorkbench } from './pages/AlbumWorkbench.tsx'
import { JobDetail } from './pages/JobDetail.tsx'
import { JobList } from './pages/JobList.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { SettingsPage } from './pages/SettingsPage.tsx'
import { AppProviders } from './providers/AppProviders.tsx'

function HomePage() {
  const navigate = useNavigate()
  return (
    <>
      <p className="app__lede">{t.lede}</p>
      <p className="app__home-link">
        <Link to="/albums">{t.openAlbumLibrary}</Link>
      </p>
      <AlbumWorkbench
        onJobCreated={(id, type) =>
          navigate(type === 'scrape' ? `/jobs/${id}` : `/albums/${id}`)
        }
      />
    </>
  )
}

function AlbumPage() {
  const { jobId } = useParams()
  if (!jobId) {
    return <Navigate to="/albums" replace />
  }
  return (
    <>
      <p className="app__crumb">
        <Link to="/albums">{t.backToAlbums}</Link>
      </p>
      <AlbumWorkbench jobId={jobId} />
    </>
  )
}

function JobPage() {
  const { jobId } = useParams()
  if (!jobId) {
    return <Navigate to="/jobs" replace />
  }
  return (
    <>
      <p className="app__crumb">
        <Link to="/jobs">{t.backToJobs}</Link>
      </p>
      <JobDetail jobId={jobId} />
    </>
  )
}

function App() {
  useLanguage()
  return (
    <AppProviders>
      <div className="app-room">
        <AppNav />
        <div className="app">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/albums" element={<AlbumLibrary />} />
            <Route path="/albums/:jobId" element={<AlbumPage />} />
            <Route path="/jobs" element={<JobList />} />
            <Route path="/jobs/:jobId" element={<JobPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>
        <ToastHost />
        <RunToaster />
      </div>
    </AppProviders>
  )
}

export default App
