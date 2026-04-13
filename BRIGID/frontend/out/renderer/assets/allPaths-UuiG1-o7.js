import { I as IconSvgPaths16 } from "./index-XVC9tR5A.js";
import { I as IconSvgPaths20 } from "./index-Dm2w9vDA.js";
import { p as pascalCase, I as IconSize } from "./index-DeVXooV8.js";
function getIconPaths(name, size) {
  var key = pascalCase(name);
  return size === IconSize.STANDARD ? IconSvgPaths16[key] : IconSvgPaths20[key];
}
function iconNameToPathsRecordKey(name) {
  return pascalCase(name);
}
export {
  IconSvgPaths16,
  IconSvgPaths20,
  getIconPaths,
  iconNameToPathsRecordKey
};
