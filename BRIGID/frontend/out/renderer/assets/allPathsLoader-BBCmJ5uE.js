const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["./allPaths-UuiG1-o7.js","./index-XVC9tR5A.js","./index-Dm2w9vDA.js","./index-DeVXooV8.js","./index-CwuBWziT.css"])))=>i.map(i=>d[i]);
import { _ as __awaiter, a as __generator, b as __vitePreload } from "./index-DeVXooV8.js";
var allPathsLoader = function(name, size) {
  return __awaiter(void 0, void 0, void 0, function() {
    var getIconPaths;
    return __generator(this, function(_a) {
      switch (_a.label) {
        case 0:
          return [4, __vitePreload(() => import(
            /* webpackChunkName: "blueprint-icons-all-paths" */
            "./allPaths-UuiG1-o7.js"
          ), true ? __vite__mapDeps([0,1,2,3,4]) : void 0, import.meta.url)];
        case 1:
          getIconPaths = _a.sent().getIconPaths;
          return [2, getIconPaths(name, size)];
      }
    });
  });
};
export {
  allPathsLoader
};
