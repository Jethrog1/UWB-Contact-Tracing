from __future__ import annotations

import math

import numpy as np


FIT_MODES = ["Linear", "Polynomial", "Logarithmic", "Power Series", "Exponential", "Moving Average"]


def build_eval_func(mode, X, Y, poly_deg=4, ma_period=4, ma_type="Trailing"):
    n = len(X)
    if n == 0:
        return lambda x: x, "Raw (no data)"
    try:
        if mode == "Linear":
            m, b = np.polyfit(X, Y, 1)
            return (lambda x, m=m, b=b: m * x + b), f"({m:.5f}*Raw)+{b:.5f}"
        if mode == "Exponential":
            v = Y > 0
            if v.sum() > 1:
                b, la = np.polyfit(X[v], np.log(Y[v]), 1)
                a = np.exp(la)
                return (lambda x, a=a, b=b: a * np.exp(b * x)), f"{a:.5f}*e^({b:.5f}*Raw)"
        if mode == "Polynomial":
            d = min(poly_deg, n - 1)
            d = max(d, 1)
            coeffs = np.polyfit(X, Y, d)

            def poly_func(x, c=coeffs, degree=d):
                return sum(c[i] * (x ** (degree - i)) for i in range(degree + 1))

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
            v = X > 0
            if v.sum() > 1:
                a, b = np.polyfit(np.log(X[v]), Y[v], 1)
                return (lambda x, a=a, b=b: a * np.log(x) + b if x > 0 else 0), f"{a:.5f}*ln(Raw)+{b:.5f}"
        if mode == "Power Series":
            v = (X > 0) & (Y > 0)
            if v.sum() > 1:
                b, la = np.polyfit(np.log(X[v]), np.log(Y[v]), 1)
                a = np.exp(la)
                return (lambda x, a=a, b=b: a * (x ** b) if x > 0 else 0), f"{a:.5f}*Raw^{b:.5f}"
        if mode == "Moving Average":
            width = min(ma_period, n)
            pts = sorted(zip(X, Y))
            sX = np.array([p[0] for p in pts])
            sY = np.array([p[1] for p in pts])
            mX, mY = [], []
            for i in range(len(sX)):
                if ma_type == "Trailing":
                    start, end = max(0, i - width + 1), i + 1
                else:
                    half = width // 2
                    start, end = max(0, i - half), min(len(sX), i + half + 1)
                seg = sY[start:end]
                mX.append(sX[i])
                mY.append(seg.mean())
            if len(mX) > 1:
                return (lambda x, mx=mX, my=mY: float(np.interp(x, mx, my))), f"{ma_type} MA(period={width})"
    except Exception:
        pass

    if n >= 2:
        m, b = np.polyfit(X, Y, 1)
        return (lambda x, m=m, b=b: m * x + b), f"({m:.5f}*Raw)+{b:.5f}"
    return lambda x: x, "Raw"


def compile_manual_equation(expression: str):
    expr = (expression or "").strip()
    if not expr or expr in {"Raw", "Raw (no data)"}:
        return lambda x: float(x)
    if expr.startswith("[Auto:"):
        closing = expr.find("]")
        if closing != -1:
            expr = expr[closing + 1 :].strip()
    safe = expr.replace("^", "**")
    math_env = {
        "ln": math.log,
        "log": math.log10,
        "e": math.e,
        "pi": math.pi,
        "sin": math.sin,
        "cos": math.cos,
        "sqrt": math.sqrt,
        "abs": abs,
    }
    code = compile(safe, "<string>", "eval")
    eval(code, {"__builtins__": {}}, dict(math_env, Raw=1.0))

    def func(x, compiled=code, env=math_env):
        return float(eval(compiled, {"__builtins__": {}}, dict(env, Raw=float(x))))

    return func
