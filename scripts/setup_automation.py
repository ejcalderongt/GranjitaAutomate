"""Instalar herramientas locales de Appium desde las fuentes oficiales."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

from granjita.core import ROOT

TOOLS = ROOT / '.tools'
NODE = shutil.which('node') or str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')


def download(url, target):
    if not target.exists():
        print('Descargando', target.name, flush=True)
        urllib.request.urlretrieve(url, target)


def setup():
    TOOLS.mkdir(exist_ok=True)
    npm_meta = json.load(urllib.request.urlopen('https://registry.npmjs.org/npm/12.2.1', timeout=30))
    archive = TOOLS / 'npm.tgz'
    download(npm_meta['dist']['tarball'], archive)
    if hashlib.sha1(archive.read_bytes()).hexdigest() != npm_meta['dist']['shasum']:
        raise RuntimeError('Integridad de npm incorrecta.')
    npm_root = TOOLS / 'npm'
    if not (npm_root / 'package/bin/npm-cli.js').exists():
        npm_root.mkdir(exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(npm_root, filter='data')
    bin_dir = TOOLS / 'bin'
    bin_dir.mkdir(exist_ok=True)
    npm_cli = npm_root / 'package/bin/npm-cli.js'
    (bin_dir / 'npm.cmd').write_text(f'@"{NODE}" "{npm_cli}" %*\r\n')
    env = os.environ.copy()
    env['PATH'] = str(bin_dir) + os.pathsep + str(Path(NODE).parent) + os.pathsep + env.get('PATH','')
    env['APPIUM_HOME'] = str(TOOLS / 'appium-home')
    server = TOOLS / 'server'
    server.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'automation/package.json', server / 'package.json')
    subprocess.run([NODE,str(npm_cli),'install','--prefix',str(server),'--no-audit','--no-fund'],env=env,check=True)
    cli = server / 'node_modules/appium/index.js'
    driver = TOOLS / 'appium-home/node_modules/appium-uiautomator2-driver/package.json'
    if not driver.exists():
        subprocess.run([NODE,str(cli),'driver','install','--source=npm','appium-uiautomator2-driver@8.7.0'],env=env,check=True)
    # SDK aislado: el ejecutable ADB es exactamente el distribuido por Panda.
    sdk = TOOLS / 'android-sdk'
    platform_tools = sdk / 'platform-tools'
    platform_tools.mkdir(parents=True,exist_ok=True)
    panda = Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)')) / 'panda_android/tools'
    for name in ['adb.exe','AdbWinApi.dll','AdbWinUsbApi.dll']:
        shutil.copy2(panda / name,platform_tools / name)
    build_tools = sdk / 'build-tools'
    if not build_tools.exists():
        junction_env = env.copy()
        junction_env['GRANJITA_BUILD_TOOLS'] = str(build_tools)
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
            "New-Item -ItemType Junction -Path $env:GRANJITA_BUILD_TOOLS -Target 'C:/AndroidSDK/build-tools' | Out-Null"],env=junction_env,check=True)
    platforms = sdk / 'platforms'
    platforms.mkdir(exist_ok=True)
    platform = TOOLS / 'platform-35_r02.zip'
    download('https://dl.google.com/android/repository/platform-35_r02.zip',platform)
    if hashlib.sha1(platform.read_bytes()).hexdigest() != '0bb560a90a7a2cbd0dd8348224d518b638fe7949':
        raise RuntimeError('Integridad de Android Platform 35 incorrecta.')
    if not list(platforms.glob('*/android.jar')):
        with zipfile.ZipFile(platform) as zipped:
            zipped.extractall(platforms)
    config = dict(node=NODE, appium=str(cli),sdk=str(sdk),java_home=str(Path(shutil.which('javac')).parent.parent),appium_home=env['APPIUM_HOME'])
    from granjita.core import DATA
    DATA.mkdir(exist_ok=True)
    (DATA / 'automation-runtime.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    print('Herramientas configuradas.',flush=True)


if __name__ == '__main__':
    setup()
