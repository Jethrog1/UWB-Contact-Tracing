from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sympy as sp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class EquationRequest(BaseModel):
    equation: str
    x_min: float = -10.0
    x_max: float = 10.0
    points: int = 200

@app.post("/plot")
def plot_equation(req: EquationRequest):
    try:
        x = sp.Symbol('x')
        expr = sp.sympify(req.equation)
        
        f = sp.lambdify(x, expr, 'math')
        
        results = []
        step = (req.x_max - req.x_min) / max(req.points - 1, 1)
        
        for i in range(req.points):
            val_x = req.x_min + i * step
            try:
                val_y = f(val_x)
                # Lambdify sometimes wraps in complex, or we get purely imaginary
                if isinstance(val_y, complex):
                    if abs(val_y.imag) > 1e-9:
                        continue
                    val_y = val_y.real
                results.append({"x": val_x, "y": val_y})
            except Exception:
                pass
                
        return {"data": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid equation: {str(e)}")
