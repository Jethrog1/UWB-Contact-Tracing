# Testing

An analysis of local testing capabilities, strategies, and continuous integration paths.

## Testing Strategy Profile

### Automated Test Coverage
- **Python (2DLCAD & BRIGID Backend):**
  - No explicit comprehensive `pytest` or `unittest` directories were broadly found in root tree scans. Most testing relies on manual run routines. File names like `dumb stuff 3.py` and various `*test*.svg` assets indicate an exploratory, ad-hoc developer testing approach over rigorous automated TDD patterns.
  
### Manual / Visual Test Assets
- **SVG Vectors & Test Rooms:** 
  - Handled via `demotest.svg`, `roomtest.svg`, `RTLSroomtest3.svg`. Tests are run by pulling these specific vectors into the CAD layout system and manually verifying anchor/UWB positions.
- **Hardware Test:**
  - Connecting physical serial UWB tags and anchoring software logic to physical testing is an apparent dependency since `serial_reader.py` directly ingests hardware output.

### Web/UI Testing
- **Frontend Validation:** 
  - Mostly utilizes `electron-vite preview` or `dev` hot-reloading for UI adjustments. There is no specific setup detected yet for React Testing Library or Cypress suite testing.

## Future Improvement Area
- For modernization, moving towards a `pytest` suite for the Python Core and a `vitest` / `@testing-library/react` layer for the React components would massively secure the overall system stability.
