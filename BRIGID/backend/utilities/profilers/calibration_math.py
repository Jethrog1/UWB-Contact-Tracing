
from __future__ import annotations
import math
from typing import Callable, Tuple

import numpy as np

FIT_MODES = ["Linear", "Polynomial", "Logarithmic", "Power Series", "Exponential", "Moving Average"]

def build_eval_func(
    mode: str,
    X: list[float],
    Y: list[float],
    poly_deg: int = 4,
    ma_period: int = 4,
    ma_type: str = "Trailing",
) -> Tuple[Callable, str]:
    Xa = np.array(X, dtype=float)
    Ya = np.array(Y, dtype=float)
    n = len(Xa)

    if n == 0:
        return lambda x: float(x), "Raw (no data)"

    try:
        if mode == "Linear":
            m, b = np.polyfit(Xa, Ya, 1)
            return (lambda x, m=m, b=b: m * x + b), f"({m:.5f}*Raw)+{b:.5f}"

        if mode == "Exponential":
            v = Ya > 0
            if v.sum() > 1:
                b, la = np.polyfit(Xa[v], np.log(Ya[v]), 1)
                a = np.exp(la)
                return (lambda x, a=a, b=b: a * np.exp(b * x)), f"{a:.5f}*e^({b:.5f}*Raw)"

        if mode == "Polynomial":
            d = max(1, min(poly_deg, n - 1))
            coeffs = np.polyfit(Xa, Ya, d)

            def poly_func(x, c=coeffs, deg=d):
                return sum(c[i] * (x ** (deg - i)) for i in range(deg + 1))

            terms = []
            for i, coeff in enumerate(coeffs):
                power = d - i
                if power > 1:
                    terms.append(f"{coeff:.4f}*Raw^{power}")
                elif power == 1:
                    terms.append(f"{coeff:.4f}*Raw")
                else:
                    terms.append(f"{coeff:.4f}")
            return poly_func, " + ".join(terms)

        if mode == "Logarithmic":
            v = Xa > 0
            if v.sum() > 1:
                a, b = np.polyfit(np.log(Xa[v]), Ya[v], 1)
                return (lambda x, a=a, b=b: a * np.log(x) + b if x > 0 else 0.0), f"{a:.5f}*ln(Raw)+{b:.5f}"

        if mode == "Power Series":
            v = (Xa > 0) & (Ya > 0)
            if v.sum() > 1:
                b, la = np.polyfit(np.log(Xa[v]), np.log(Ya[v]), 1)
                a = np.exp(la)
                return (lambda x, a=a, b=b: a * (x ** b) if x > 0 else 0.0), f"{a:.5f}*Raw^{b:.5f}"

        if mode == "Moving Average":
            width = min(ma_period, n)
            pts = sorted(zip(Xa.tolist(), Ya.tolist()))
            sX = np.array([p[0] for p in pts])
            sY = np.array([p[1] for p in pts])
            mX, mY = [], []
            for i in range(len(sX)):
                if ma_type == "Trailing":
                    start, end = max(0, i - width + 1), i + 1
                else:
                    half = width // 2
                    start, end = max(0, i - half), min(len(sX), i + half + 1)
                mX.append(sX[i])
                mY.append(sY[start:end].mean())
            if len(mX) > 1:
                return (lambda x, mx=mX, my=mY: float(np.interp(x, mx, my))), f"{ma_type} MA(period={width})"

    except Exception:
        pass

    if n >= 2:
        m, b = np.polyfit(Xa, Ya, 1)
        return (lambda x, m=m, b=b: m * x + b), f"({m:.5f}*Raw)+{b:.5f}"
    return lambda x: float(x), "Raw"

def compile_manual_equation(expression: str) -> Callable:
    expr = (expression or "").strip()
    if not expr or expr in {"Raw", "Raw (no data)"}:
        return lambda x: float(x)

    if expr.startswith("[Auto:"):
        closing = expr.find("]")
        if closing != -1:
            expr = expr[closing + 1:].strip()

    safe = expr.replace("^", "**")
    math_env = {
        "ln":   math.log,
        "log":  math.log10,
        "e":    math.e,
        "pi":   math.pi,
        "sin":  math.sin,
        "cos":  math.cos,
        "sqrt": math.sqrt,
        "abs":  abs,
    }
    code = compile(safe, "<calibration>", "eval")

    eval(code, {"__builtins__": {}}, dict(math_env, Raw=1.0))

    def func(x: float, compiled=code, env=math_env) -> float:
        return float(eval(compiled, {"__builtins__": {}}, dict(env, Raw=float(x))))

    return func
