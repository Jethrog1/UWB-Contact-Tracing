import React, { useState } from 'react'
import { FocusStyleManager } from '@blueprintjs/core'
import { motion } from 'motion/react'
import TopBar, { AppModule } from './components/TopBar/TopBar'
import LeftRail from './components/LeftRail/LeftRail'
import CentralCanvas from './components/CentralCanvas/CentralCanvas'
import RightPanel from './components/RightPanel/RightPanel'
import './App.css'

FocusStyleManager.onlyShowFocusOnTabs()

const App: React.FC = () => {
  const [activeModule, setActiveModule] = useState<AppModule>('rtls')

  return (
    <div className="bp5-dark app-root">
      <motion.div
        className="app-shell"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        <TopBar activeModule={activeModule} onModuleChange={setActiveModule} />
        <LeftRail />
        <CentralCanvas activeModule={activeModule} />
        <RightPanel activeModule={activeModule} />
      </motion.div>
    </div>
  )
}

export default App
