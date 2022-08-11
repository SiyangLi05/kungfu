const path = require('path');
const fse = require('fs-extra');
const kungfuCore = require('@kungfu-trader/kungfu-core/package.json');
const {
  getAppDir,
  getKfcDir,
  getCoreDir,
  getExtensionDirs,
  findPackageRoot,
} = require('@kungfu-trader/kungfu-js-api/toolkit/utils');

const appDir = getAppDir();

const kfcDir = getKfcDir();
const coreDir = getCoreDir();
const extensionDirs = getExtensionDirs(true);
const root = findPackageRoot();
console.log(`-- Package root ${root}`);
const languageDir = path.join(root, 'language');
const languageFile = path.join(languageDir, 'locale.json');
const languageCNMergeFile = path.join(languageDir, 'zh-CN-merge.json');
const languageENMergeFile = path.join(languageDir, 'en-US-merge.json');

const extensions = extensionDirs.map((fullpath) => {
  const extensionDir = path.resolve(fullpath, 'dist');
  console.log(
    `-- Found kungfu extension: [${fse.readdirSync(extensionDir).join(', ')}]`,
  );
  return {
    from: extensionDir,
    to: 'app/kungfu-extensions',
  };
});

if (fse.existsSync(languageFile)) {
  console.log(`-- Found language file ${languageFile}`);
}

if (fse.existsSync(languageCNMergeFile)) {
  console.log(`-- Found language cn merge file ${languageCNMergeFile}`);
}

if (fse.existsSync(languageENMergeFile)) {
  console.log(`-- Found language en merge file ${languageENMergeFile}`);
}

module.exports = {
  generateUpdatesFilesForAllChannels: true,
  appId: 'Kungfu.Origin.KungFu.Trader',
  electronVersion:
    kungfuCore.devDependencies.electron || kungfuCore.dependencies.electron,
  publish: [
    {
      provider: 'generic',
      url: 'https://www.kungfu-trader.com',
    },
  ],
  npmRebuild: false,
  files: [
    'dist/app/**/*',
    'dist/cli/**/*',
    'dist/kfs/**/*',
    '!**/@kungfu-trader/kfx-*/**/*',
    '!**/@kungfu-trader/kungfu-sdk/**/*',
    '**/@kungfu-trader/kungfu-sdk/templates/**/*',
    '!**/@kungfu-trader/kungfu-core/*',
    '!**/@kungfu-trader/kungfu-core/**/*',
    '**/@kungfu-trader/kungfu-core/lib/*',
    '**/@kungfu-trader/kungfu-core/*.json',
    '!**/@kungfu-trader/kungfu-app/*',
    '!**/@kungfu-trader/kungfu-app/**/*',
    '**/@kungfu-trader/kungfu-app/lib/*',
    '**/@kungfu-trader/kungfu-app/package.json',
    '!**/@kungfu-trader/kungfu-cli/*',
    '!**/@kungfu-trader/kungfu-cli/**/*',
    '!**/@kungfu-trader/kungfu-js-api/*',
    '!**/@kungfu-trader/kungfu-js-api/**/*',
  ],
  extraResources: [
    {
      from: kfcDir,
      to: 'kfc',
      filter: ['!**/btdata'],
    },
    {
      from: `${coreDir}/build/python/dist`,
      to: 'app/dist/public/python',
      filter: ['*.whl'],
    },
    {
      from: appDir,
      to: 'app/dist',
      filter: [
        'public/config',
        'public/key',
        'public/logo',
        'public/keywords',
        'public/music',
        'public/language',
      ],
    },
    {
      from: appDir,
      to: 'app',
      filter: ['lib/*'],
    },
    {
      from: `${appDir}/lib/electron`,
      to: 'app',
      filter: ['package.json'],
    },
    ...(fse.existsSync(languageDir)
      ? [
          {
            from: languageDir,
            to: 'app/dist/public/language',
            filter: ['locale.json', 'zh-CN-merge.json', 'en-US-merge.json'],
          },
        ]
      : []),
    ...extensions,
  ],
  asar: false,
  dmg: {
    contents: [
      {
        x: 410,
        y: 150,
        type: 'link',
        path: '/Applications',
      },
      {
        x: 130,
        y: 150,
        type: 'file',
      },
    ],
  },
  mac: {
    icon: `${appDir}/public/logo/icon.icns`,
    type: 'distribution',
    target: ['dmg'],
  },
  win: {
    icon: `${appDir}/public/logo/icon.ico`,
    target: [
      {
        target: 'nsis',
        arch: ['x64'],
      },
    ],
  },
  linux: {
    icon: `${appDir}/public/logo/icon.icns`,
    target: ['rpm', 'appimage'],
    executableName: 'Kungfu.app',
  },
  nsis: {
    oneClick: false,
    allowElevation: true,
    allowToChangeInstallationDirectory: true,
    installerIcon: `${appDir}/public/logo/icon.ico`,
    uninstallerIcon: `${appDir}/public/logo/icon.ico`,
    installerHeaderIcon: `${appDir}/public/logo/icon.ico`,
    createDesktopShortcut: true,
    createStartMenuShortcut: true,
  },

  afterAllArtifactBuild: (result) => {
    if (process.env.CI && process.platform === 'win32') {
      fse.removeSync(path.join(result.outDir, 'win-unpacked'));
    }
  },
};
