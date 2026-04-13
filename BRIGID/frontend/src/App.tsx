import { useState, useRef, useEffect, MouseEvent } from 'react';
import { motion, useMotionValue, useSpring, animate } from 'framer-motion';
import { RotateCcw, ZoomIn, ZoomOut, Play } from 'lucide-react';

export default function App() {
  const [equation, setEquation] = useState("sin(x) * x");
  const [points, setPoints] = useState<{x: number, y: number}[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Animation values
  const panX = useMotionValue(0);
  const panY = useMotionValue(0);
  const scale = useSpring(1, { stiffness: 200, damping: 25 });
  
  const fetchPlot = async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("http://127.0.0.1:8000/plot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ equation, x_min: -30, x_max: 30, points: 500 })
      });
      const data = await resp.json();
      if (!resp.ok) {
        setError(data.detail || "Error evaluating equation");
      } else {
        setPoints(data.data);
      }
    } catch (e) {
      setError("Cannot connect to server. Is FastAPI running?");
    }
    setLoading(false);
  };

  const handleReset = () => {
    animate(panX, 0, { type: "spring", stiffness: 150, damping: 20 });
    animate(panY, 0, { type: "spring", stiffness: 150, damping: 20 });
    scale.set(1);
  };

  const handleZoomIn = () => scale.set(scale.get() * 1.5);
  const handleZoomOut = () => scale.set(scale.get() / 1.5);

  // Compute SVG Path
  // 1 unit = 40 pixels
  const buildPath = () => {
    if (points.length === 0) return "";
    const p0 = points[0];
    let d = `M ${p0.x * 40} ${-p0.y * 40}`;
    for (let i = 1; i < points.length; i++) {
        d += ` L ${points[i].x * 40} ${-points[i].y * 40}`;
    }
    return d;
  };

  // Build grid lines
  const gridLines = [];
  for (let i = -30; i <= 30; i++) {
    // Vertical lines
    gridLines.push(<line key={`vx${i}`} x1={i*40} y1={-1200} x2={i*40} y2={1200} stroke="#333" strokeWidth={i===0?2:0.5} opacity={i===0?1:0.3}/>);
    // Horizontal lines
    gridLines.push(<line key={`hy${i}`} x1={-1200} y1={-i*40} x2={1200} y2={-i*40} stroke="#333" strokeWidth={i===0?2:0.5} opacity={i===0?1:0.3}/>);
  }

  return (
    <div style={{ width: '100vw', height: '100vh', backgroundColor: '#111', overflow: 'hidden', fontFamily: 'sans-serif', color: 'white', position: 'relative' }}>
        
        {/* Interactive Graph Surface */}
        <div style={{ position: 'absolute', inset: 0, cursor: 'grab' }}>
            <motion.div 
               style={{ width: '100%', height: '100%', x: panX, y: panY }}
               drag
               dragMomentum={true}
               whileDrag={{ cursor: 'grabbing' }}
            >
                <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <motion.svg style={{ scale, width: 2400, height: 2400, overflow: 'visible' }}>
                        <g transform="translate(1200 1200)">
                            {gridLines}
                            {points.length > 0 && (
                                <motion.path
                                    d={buildPath()}
                                    fill="none"
                                    stroke="cyan"
                                    strokeWidth={3}
                                    style={{ filter: "drop-shadow(0px 0px 8px cyan)" }}
                                    initial={{ pathLength: 0, opacity: 0 }}
                                    animate={{ pathLength: 1, opacity: 1 }}
                                    transition={{ duration: 2, ease: "easeInOut" }}
                                />
                            )}
                        </g>
                    </motion.svg>
                </div>
            </motion.div>
        </div>

        {/* UI Overlay */}
        <div style={{ position: 'absolute', bottom: '40px', left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: '15px', alignItems: 'center', backgroundColor: 'rgba(30, 30, 30, 0.8)', padding: '20px 30px', borderRadius: '15px', backdropFilter: 'blur(10px)', border: '1px solid #333' }}>
            <motion.input
                value={equation}
                onChange={e => setEquation(e.target.value)}
                placeholder="Type equation, e.g. sin(x)"
                whileFocus={{ scale: 1.05, boxShadow: '0px 0px 20px rgba(0, 255, 255, 0.5)' }}
                style={{
                   padding: '10px 15px',
                   borderRadius: '8px',
                   border: '1px solid #444',
                   backgroundColor: '#222',
                   color: 'cyan',
                   fontSize: '16px',
                   outline: 'none',
                   width: '250px',
                   transition: 'width 0.3s'
                }}
            />
            <motion.button
                onClick={fetchPlot}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '10px 20px', borderRadius: '8px', border: 'none', backgroundColor: '#00ccaa', color: 'black', fontWeight: 'bold', cursor: 'pointer' }}
            >
                {loading ? 'Plotting...' : <><Play size={18} /> Plot</>}
            </motion.button>

            <div style={{ width: '1px', height: '30px', backgroundColor: '#444' }} />

            {/* View Controls */}
            <motion.button onClick={handleReset} whileHover={{ scale: 1.1, boxShadow: '0px 0px 10px rgba(255,255,255,0.3)' }} animate={{ scale: [1, 1.02, 1] }} transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }} style={controlBtnStyle}>
                <RotateCcw size={18} />
            </motion.button>
            <motion.button onClick={handleZoomOut} whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} style={controlBtnStyle}>
                <ZoomOut size={18} />
            </motion.button>
            <motion.button onClick={handleZoomIn} whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} style={controlBtnStyle}>
                <ZoomIn size={18} />
            </motion.button>
        </div>

        {error && (
            <div style={{ position: 'absolute', top: '20px', left: '50%', transform: 'translateX(-50%)', backgroundColor: 'rgba(255,0,0,0.2)', color: '#ff6666', padding: '10px 20px', borderRadius: '8px', border: '1px solid #ff4444' }}>
                {error}
            </div>
        )}
    </div>
  );
}

const controlBtnStyle = {
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '10px', borderRadius: '8px', border: '1px solid #555', backgroundColor: '#333', color: 'white', cursor: 'pointer'
};
