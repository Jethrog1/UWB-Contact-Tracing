import { _ as __awaiter, a as __generator, b as __vitePreload, p as pascalCase, I as IconSize } from "./index-DwZNOUDo.js";
var splitPathsBySizeLoader = function(name, size) {
  return __awaiter(void 0, void 0, void 0, function() {
    var key, pathsRecord;
    return __generator(this, function(_a) {
      switch (_a.label) {
        case 0:
          key = pascalCase(name);
          if (!(size === IconSize.STANDARD)) return [3, 2];
          return [4, __vitePreload(() => import(
            /* webpackChunkName: "blueprint-icons-16px-paths" */
            "./index-XVC9tR5A.js"
          ).then((n) => n.I), true ? [] : void 0, import.meta.url)];
        case 1:
          pathsRecord = _a.sent();
          return [3, 4];
        case 2:
          return [4, __vitePreload(() => import(
            /* webpackChunkName: "blueprint-icons-20px-paths" */
            "./index-Dm2w9vDA.js"
          ).then((n) => n.I), true ? [] : void 0, import.meta.url)];
        case 3:
          pathsRecord = _a.sent();
          _a.label = 4;
        case 4:
          return [2, pathsRecord[key]];
      }
    });
  });
};
export {
  splitPathsBySizeLoader
};
