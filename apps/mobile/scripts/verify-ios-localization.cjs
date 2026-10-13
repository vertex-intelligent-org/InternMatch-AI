const fs = require('fs');
const path = require('path');

const appPath = path.resolve(__dirname, '..', 'app.json');
const app = JSON.parse(fs.readFileSync(appPath, 'utf8'));

const infoPlist = app?.expo?.ios?.infoPlist;

if (!infoPlist) {
  throw new Error('FAIL: expo.ios.infoPlist is missing.');
}

if (infoPlist.CFBundleDevelopmentRegion !== 'en') {
  throw new Error(
    `FAIL: CFBundleDevelopmentRegion expected "en", got ${JSON.stringify(
      infoPlist.CFBundleDevelopmentRegion
    )}`
  );
}

const expected = ['en', 'tr', 'ar'];

if (
  !Array.isArray(infoPlist.CFBundleLocalizations) ||
  JSON.stringify(infoPlist.CFBundleLocalizations) !==
    JSON.stringify(expected)
) {
  throw new Error(
    `FAIL: CFBundleLocalizations expected ${JSON.stringify(
      expected
    )}, got ${JSON.stringify(
      infoPlist.CFBundleLocalizations
    )}`
  );
}

console.log('IOS_LOCALIZATION_CONTRACT=PASS');
console.log(
  `CFBundleDevelopmentRegion=${infoPlist.CFBundleDevelopmentRegion}`
);
console.log(
  `CFBundleLocalizations=${JSON.stringify(
    infoPlist.CFBundleLocalizations
  )}`
);