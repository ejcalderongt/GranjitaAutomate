"""Compilar APK de laboratorio con JDK y Android Build Tools, sin Gradle."""
import json
import os
from pathlib import Path
import subprocess
import zipfile
from granjita.core import ROOT, DATA


def build():
    config = json.loads((DATA / 'automation-runtime.json').read_text(encoding='utf-8'))
    sdk, java = Path(config['sdk']), Path(config['java_home']) / 'bin'
    tools = sdk / 'build-tools/35.0.0'
    android = next((sdk / 'platforms').glob('*/android.jar'))
    out = DATA / 'lab-build'
    classes, dex = out / 'classes', out / 'dex'
    classes.mkdir(parents=True,exist_ok=True)
    dex.mkdir(exist_ok=True)
    def run(args):
        subprocess.run(list(map(str,args)),check=True,creationflags=0x08000000)
    run([java/'javac.exe','-encoding','UTF-8','-source','8','-target','8','-classpath',android,'-d',classes,ROOT/'android-lab/src/gt/granjita/lab/MainActivity.java'])
    run([java/'jar.exe','cf',out/'classes.jar','-C',classes,'.'])
    run([java/'java.exe','-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--lib',android,'--min-api','26','--output',dex,out/'classes.jar'])
    unsigned = out/'unsigned.apk'
    run([tools/'aapt2.exe','link','--manifest',ROOT/'android-lab/AndroidManifest.xml','-I',android,'-o',unsigned])
    with zipfile.ZipFile(unsigned,'a') as apk:
        apk.write(dex/'classes.dex','classes.dex')
    aligned=out/'aligned.apk'
    run([tools/'zipalign.exe','-f','4',unsigned,aligned])
    key=DATA/'lab-debug.keystore'
    if not key.exists():
        run([java/'keytool.exe','-genkeypair','-keystore',key,'-storepass','android','-keypass','android','-alias','androiddebugkey','-keyalg','RSA','-keysize','2048','-validity','10000','-dname','CN=Granjita Local Lab,O=Lab,C=GT'])
    apk=DATA/'granjita-lab.apk'
    run([java/'java.exe','-jar',tools/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:android','--key-pass','pass:android','--out',apk,aligned])
    run([java/'java.exe','-jar',tools/'lib/apksigner.jar','verify',apk])
    print('APK de laboratorio creado y verificado:',apk)


if __name__=='__main__':
    build()
